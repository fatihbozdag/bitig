"""sklearn classifier wrappers + CV helper with stylometry-aware splits."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import (
    LeaveOneGroupOut,
    LeaveOneOut,
    StratifiedKFold,
    cross_val_predict,
)
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC

from bitig.corpus import Corpus
from bitig.features import FeatureMatrix
from bitig.features.base import BaseFeatureExtractor

_ESTIMATORS = {
    "logreg": lambda **kw: LogisticRegression(max_iter=2000, **kw),
    "svm_linear": lambda **kw: SVC(kernel="linear", probability=True, **kw),
    "svm_rbf": lambda **kw: SVC(kernel="rbf", probability=True, **kw),
    "rf": lambda **kw: RandomForestClassifier(**kw),
    "hgbm": lambda **kw: HistGradientBoostingClassifier(**kw),
}


def build_classifier(name: str, **kwargs: Any) -> BaseEstimator:
    if name not in _ESTIMATORS:
        raise ValueError(f"unknown classifier {name!r}; known: {sorted(_ESTIMATORS)}")
    return _ESTIMATORS[name](**kwargs)


class FeatureTransformer(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """Adapt a bitig extractor (documents → FeatureMatrix) to a plain sklearn step (→ X)."""

    def __init__(self, extractor: BaseFeatureExtractor, language: str = "en") -> None:
        self.extractor = extractor
        # sklearn hands each fold a plain list of Documents; re-wrap it with the
        # corpus language so language-dependent extractors (function words,
        # readability) do not fall back to English inside the folds.
        self.language = language

    def _corpus(self, documents: list[Any]) -> Corpus:
        return Corpus(documents=list(documents), language=self.language)

    def fit(self, documents: list[Any], y: Any = None) -> FeatureTransformer:
        self.extractor.fit(self._corpus(documents))
        return self

    def transform(self, documents: list[Any]) -> np.ndarray:
        return self.extractor.transform(self._corpus(documents)).X


def _is_degenerate_grouping(groups: np.ndarray, y: np.ndarray) -> bool:
    """True when the groups are a one-to-one relabelling of the target classes.

    LeaveOneGroupOut then holds out every instance of a class, which is never in
    training, so accuracy is ~0 by construction (audit P1.16).
    """
    pairs = {(g, t) for g, t in zip(groups.tolist(), y.tolist(), strict=True)}
    return len(pairs) == len(set(groups.tolist())) == len(set(y.tolist()))


def cross_validate_bitig(
    estimator: BaseEstimator,
    fm: FeatureMatrix | None,
    y: np.ndarray,
    *,
    cv_kind: str = "stratified",
    groups_from: np.ndarray | None = None,
    folds: int = 5,
    seed: int = 42,
    extractor: BaseFeatureExtractor | None = None,
    corpus: Corpus | None = None,
) -> dict[str, Any]:
    """Run cross-validation with a stylometry-aware CV strategy.

    Pass ``extractor`` and ``corpus`` (and ``fm=None``) to fit the feature
    extractor inside each training fold, so held-out documents never shape the
    vocabulary or the z-score statistics. A precomputed ``fm`` is used as-is:
    if it was fit on all documents, the CV estimate is optimistically biased
    (audit 2026-09-26 P2).

    cv_kind:
      - "stratified": StratifiedKFold(folds) — uses `seed` for the shuffle
      - "loao":       LeaveOneGroupOut (requires groups_from; deterministic).
        Refused when the groups merely relabel the target classes.
      - "leave_one_text_out": LeaveOneOut (deterministic)
    """
    y = np.asarray(y)
    if extractor is not None:
        if corpus is None:
            raise ValueError("extractor= requires corpus=")
        X: Any = list(corpus.documents)  # noqa: N806 (sklearn convention)
        model: BaseEstimator = Pipeline(
            [("features", FeatureTransformer(extractor, corpus.language)), ("clf", estimator)]
        )
    elif fm is not None:
        X = fm.X  # noqa: N806
        model = estimator
    else:
        raise ValueError("pass either fm or extractor + corpus")
    if cv_kind == "stratified":
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
        groups = None
    elif cv_kind == "loao":
        if groups_from is None:
            raise ValueError("cv_kind='loao' requires groups_from")
        cv = LeaveOneGroupOut()
        groups = np.asarray(groups_from)
        if _is_degenerate_grouping(groups, y):
            raise ValueError(
                "cv_kind='loao' groups are a one-to-one relabelling of the classification "
                "target: every held-out group is an unseen class, so accuracy is ~0 by "
                "construction. Group by a different column (e.g. topic or source) or use "
                "cv_kind='stratified'."
            )
    elif cv_kind == "leave_one_text_out":
        cv = LeaveOneOut()
        groups = None
    else:
        raise ValueError(f"unknown cv_kind {cv_kind!r}")

    preds = cross_val_predict(model, X, y, cv=cv, groups=groups)
    report = classification_report(y, preds, output_dict=True, zero_division=0)

    proba: np.ndarray | None = None
    classes: np.ndarray | None = None
    if hasattr(estimator, "predict_proba"):
        try:
            proba = cross_val_predict(model, X, y, cv=cv, groups=groups, method="predict_proba")
            # cross_val_predict reorders class columns to match np.unique(y); recover.
            classes = np.unique(y)
        except Exception:
            # Some estimators raise when predict_proba is unsupported under a given CV fold
            # configuration -- skip silently and let downstream calibration code handle the
            # missing-proba case.
            proba = None
            classes = None

    return {
        "accuracy": float((preds == y).mean()),
        "predictions": preds,
        "per_class": report,
        "proba": proba,
        "classes": classes,
    }
