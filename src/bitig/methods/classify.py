"""sklearn classifier wrappers + CV helper with stylometry-aware splits."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import (
    GroupKFold,
    LeaveOneGroupOut,
    LeaveOneOut,
    StratifiedKFold,
)
from sklearn.svm import SVC

from bitig.corpus import Corpus
from bitig.features import FeatureMatrix
from bitig.features.base import BaseFeatureExtractor

_ESTIMATORS = {
    "logreg": lambda **kw: LogisticRegression(**{"max_iter": 2000, **kw}),
    "svm_linear": lambda **kw: SVC(kernel="linear", probability=True, **kw),
    "svm_rbf": lambda **kw: SVC(kernel="rbf", probability=True, **kw),
    "rf": lambda **kw: RandomForestClassifier(**kw),
    "hgbm": lambda **kw: HistGradientBoostingClassifier(**kw),
}


def build_classifier(name: str, **kwargs: Any) -> BaseEstimator:
    if name not in _ESTIMATORS:
        raise ValueError(f"unknown classifier {name!r}; known: {sorted(_ESTIMATORS)}")
    return _ESTIMATORS[name](**kwargs)


def cross_validate_bitig(
    estimator: BaseEstimator,
    fm: FeatureMatrix | Corpus,
    y: np.ndarray,
    *,
    extractor: BaseFeatureExtractor | None = None,
    cv_kind: str = "stratified",
    groups_from: np.ndarray | None = None,
    folds: int | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Evaluate once per fold, fitting learned features on training documents only.

    Pass a Corpus and an unfitted extractor for end-to-end evaluation. Precomputed
    FeatureMatrix input is retained for explicitly fixed, externally defined features;
    its output is labelled conditional on that representation, not leakage-free CV.
    """
    y = np.asarray(y)
    if y.ndim != 1 or len(y) != len(fm) or any(v is None for v in y):
        raise ValueError("y must contain one non-missing label per document")
    classes, counts = np.unique(y, return_counts=True)
    if len(classes) < 2:
        raise ValueError("classification requires at least two classes")
    if isinstance(fm, Corpus) and extractor is None:
        raise ValueError("Corpus cross-validation requires an unfitted extractor")
    if isinstance(fm, FeatureMatrix) and extractor is not None:
        raise ValueError("pass raw Corpus when fitting an extractor inside folds")
    groups = None
    if cv_kind == "stratified":
        effective_folds = folds if folds is not None else min(5, int(counts.min()))
        if effective_folds < 2 or effective_folds > counts.min():
            raise ValueError("stratified folds must be between 2 and the smallest class size")
        cv = StratifiedKFold(n_splits=effective_folds, shuffle=True, random_state=seed)
    elif cv_kind in ("loao", "group_kfold"):
        if groups_from is None or len(groups_from) != len(y):
            raise ValueError(f"cv_kind={cv_kind!r} requires one group per document")
        groups = np.asarray(groups_from)
        if any(v is None for v in groups):
            raise ValueError("CV groups must not be missing")
        if cv_kind == "loao":
            cv = LeaveOneGroupOut()
        else:
            effective_folds = folds if folds is not None else min(5, len(np.unique(groups)))
            if effective_folds < 2:
                raise ValueError("group_kfold requires at least two groups")
            cv = GroupKFold(n_splits=effective_folds)
    elif cv_kind == "leave_one_text_out":
        cv = LeaveOneOut()
    else:
        raise ValueError(f"unknown cv_kind {cv_kind!r}")

    splits = list(cv.split(np.zeros(len(y)), y, groups))
    # Validate all folds before fitting anything. Holding out a whole target class
    # cannot estimate closed-set attribution performance.
    for train, _ in splits:
        if set(y[train]) != set(classes):
            raise ValueError(
                "a training fold omits a target class; change grouping or collect data"
            )
    preds = np.empty_like(y)
    probabilities = (
        np.zeros((len(y), len(classes))) if hasattr(estimator, "predict_proba") else None
    )
    fold_ids = np.empty(len(y), dtype=int)
    fold_records = []
    for index, (train, test) in enumerate(splits):
        model = clone(estimator)
        if "random_state" in model.get_params() and model.get_params()["random_state"] is None:
            model.set_params(random_state=seed)
        feature_hash = None
        if isinstance(fm, Corpus):
            from copy import deepcopy

            assert extractor is not None
            features = deepcopy(extractor)
            training, testing = fm[train], fm[test]
            assert isinstance(training, Corpus) and isinstance(testing, Corpus)
            train_fm = features.fit_transform(training)
            test_fm = features.transform(testing)
            train_values, test_values = train_fm.X, test_fm.X
            feature_hash = train_fm.provenance_hash
        else:
            train_values, test_values = fm.X[train], fm.X[test]
        model.fit(train_values, y[train])
        preds[test] = model.predict(test_values)
        if probabilities is not None:
            local = model.predict_proba(test_values)
            for col, label in enumerate(model.classes_):
                probabilities[test, np.flatnonzero(classes == label)[0]] = local[:, col]
        fold_ids[test] = index
        fold_records.append(
            {
                "train_indices": train.tolist(),
                "test_indices": test.tolist(),
                "training_feature_hash": feature_hash,
            }
        )
    return {
        "accuracy": float((preds == y).mean()),
        "predictions": preds,
        "per_class": classification_report(y, preds, output_dict=True, zero_division=0),
        "proba": probabilities,
        "classes": classes if probabilities is not None else None,
        "fold_ids": fold_ids,
        "folds": fold_records,
        "evaluation": "fold-local cross-validation"
        if isinstance(fm, Corpus)
        else "cross-validation conditional on precomputed features",
    }
