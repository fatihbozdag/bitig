"""FeatureMatrix — the shared return type for every feature extractor — plus the sklearn-compatible
base class extractors inherit from.

Every FeatureMatrix carries its provenance: what extractor produced it, what config was used, and
a hash that combines extractor config + corpus hash. That hash ends up in `Result.provenance`.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from bitig.corpus import Corpus, Document


def _ensure_corpus(obj: Corpus | list) -> Corpus:
    """Wrap a list of Documents into a Corpus (idempotent for Corpus instances).

    sklearn's cross-validation splitters slice `X` with an ndarray of indices and, when X is not
    a pandas / ndarray / sparse type, fall back to `[X[i] for i in indices]` — producing a list.
    We accept either form at the extractor boundary.
    """
    if isinstance(obj, Corpus):
        return obj
    if isinstance(obj, list) and (not obj or isinstance(obj[0], Document)):
        return Corpus(documents=obj)
    raise TypeError(f"expected Corpus or list[Document]; got {type(obj).__name__}")


@dataclass
class FeatureMatrix:
    X: np.ndarray
    document_ids: list[str]
    feature_names: list[str]
    feature_type: str
    extractor_config: dict[str, Any] = field(default_factory=dict)
    provenance_hash: str = ""

    def __post_init__(self) -> None:
        if self.X.ndim != 2:
            raise ValueError(f"FeatureMatrix.X must be 2-D; got shape {self.X.shape}")
        if self.X.shape[0] != len(self.document_ids):
            raise ValueError(
                f"FeatureMatrix: rows ({self.X.shape[0]}) != len(document_ids) "
                f"({len(self.document_ids)})"
            )
        if self.X.shape[1] != len(self.feature_names):
            raise ValueError(
                f"FeatureMatrix: cols ({self.X.shape[1]}) != len(feature_names) "
                f"({len(self.feature_names)})"
            )

    def __len__(self) -> int:
        return int(self.X.shape[0])

    @property
    def n_features(self) -> int:
        return int(self.X.shape[1])

    def as_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.X, index=self.document_ids, columns=self.feature_names)

    def concat(self, other: FeatureMatrix) -> FeatureMatrix:
        """Column-concatenate two FeatureMatrix objects with identical document_ids."""
        if self.document_ids != other.document_ids:
            raise ValueError("FeatureMatrix.concat: document_ids must match exactly")
        shared = set(self.feature_names) & set(other.feature_names)
        if shared:
            raise ValueError(f"FeatureMatrix.concat: duplicate feature names: {sorted(shared)}")
        return FeatureMatrix(
            X=np.hstack([self.X, other.X]),
            document_ids=list(self.document_ids),
            feature_names=list(self.feature_names) + list(other.feature_names),
            feature_type=f"{self.feature_type}+{other.feature_type}",
            extractor_config={"a": self.extractor_config, "b": other.extractor_config},
            provenance_hash="",
        )


class BaseFeatureExtractor(BaseEstimator, TransformerMixin):
    """Base class every feature extractor inherits from.

    Subclasses implement:
      - `_fit(corpus)` — learn vocabulary / state from a training corpus.
      - `_transform(corpus)` — produce an (n_docs, n_features) numpy array and a list of feature names.
      - `feature_type` class attribute — string tag stored on the FeatureMatrix.

    The sklearn-compatible `fit`, `transform`, and `fit_transform` methods wrap these in the
    FeatureMatrix envelope.
    """

    feature_type: str = "base"

    @abstractmethod
    def _fit(self, corpus: Corpus) -> None: ...

    @abstractmethod
    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        """Return (X, feature_names) for the given corpus."""

    def fit(self, corpus: Corpus | list, y: Any = None) -> BaseFeatureExtractor:
        corpus = _ensure_corpus(corpus)
        self._fit(corpus)
        self._training_corpus_hash = corpus.hash()
        return self

    def transform(self, corpus: Corpus | list) -> FeatureMatrix:
        corpus = _ensure_corpus(corpus)
        X, feature_names = self._transform(corpus)  # noqa: N806 (sklearn convention)
        return FeatureMatrix(
            X=X,
            document_ids=[d.id for d in corpus.documents],
            feature_names=feature_names,
            feature_type=self.feature_type,
            extractor_config=self.get_params(),
            provenance_hash=self._provenance(corpus),
        )

    def fit_transform(self, corpus: Corpus | list, y: Any = None) -> FeatureMatrix:
        return self.fit(corpus).transform(corpus)

    def _provenance(self, corpus: Corpus) -> str:
        from bitig.plumbing.hashing import hash_mapping

        payload = {
            "extractor": type(self).__name__,
            "config": self.get_params(),
            "corpus_hash": corpus.hash(),
            "feature_type": self.feature_type,
            # The same config fitted on different texts yields a different vocabulary and
            # different scaling statistics, so the hash binds the training corpus and the
            # fitted vocabulary, not only the corpus being transformed.
            "training_corpus_hash": getattr(self, "_training_corpus_hash", None),
            "fitted_state": self._fitted_state(),
        }
        return hash_mapping(payload)

    # Vocabularies and word lists only: scaling statistics follow from config + training
    # corpus (already bound) and would make the hash sensitive to float rounding across CPUs.
    _FITTED_ATTRS = ("_vocabulary", "_words", "_resolved_indices")

    def _fitted_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        for name in self._FITTED_ATTRS:
            value = getattr(self, name, None)
            if value is not None:
                state[name] = value.tolist() if isinstance(value, np.ndarray) else list(value)
        vectorizer = getattr(self, "_vectorizer", None)
        vocabulary = getattr(vectorizer, "vocabulary_", None)
        if vocabulary is not None:
            state["vectorizer_vocabulary"] = sorted((k, int(v)) for k, v in vocabulary.items())
        return state
