"""Eder Delta (Eder 2015) -- rank-weighted Burrows -- and Eder's Simple Delta (Eder 2017)."""

from __future__ import annotations

import numpy as np

from bitig.features import FeatureMatrix
from bitig.methods.delta.base import _as_ndarray, _DeltaBase


class EderDelta(_DeltaBase):
    """Eder Delta (Eder 2015): like Burrows, but each feature's contribution is
    weighted by its frequency *rank*, ``w_i = (n - i) / n`` for the i-th most
    frequent feature, so the most frequent features contribute most and the
    long tail is progressively down-weighted.

    The feature matrix arrives with columns already in descending frequency
    order (``MFWExtractor`` sorts them), so the weight is a pure function of
    column position — it is NOT derived from the class centroids (deriving the
    weights from the very means the classifier then scores against would be
    circular, and an earlier implementation that ranked by across-centroid
    variance did exactly that).
    """

    def __init__(self) -> None:
        super().__init__()
        self._weights: np.ndarray | None = None

    def fit(self, X: FeatureMatrix | np.ndarray, y: np.ndarray) -> EderDelta:  # type: ignore[override]  # noqa: N803
        super().fit(X, y)
        n = _as_ndarray(X).shape[1]
        # Frequency-rank weights: column 0 (most frequent) → 1.0, decreasing to
        # 1/n for the rarest. Depends only on feature position, not the data.
        self._weights = np.arange(n, 0, -1, dtype=float) / n
        return self

    def _distance(self, X: np.ndarray, centroid: np.ndarray) -> np.ndarray:  # noqa: N803
        assert self._weights is not None
        return (self._weights * np.abs(X - centroid)).sum(axis=1) / self._weights.sum()  # type: ignore[no-any-return]


class EderSimpleDelta(_DeltaBase):
    """Eder's Simple Delta (Eder 2017): L1 distance on unweighted z-scored features.

    Differs from Burrows only in that Burrows divides by feature count; Eder Simple does not.
    In practice this only changes a monotone scaling of distances -- rankings are identical.
    """

    def _distance(self, X: np.ndarray, centroid: np.ndarray) -> np.ndarray:  # noqa: N803
        return np.abs(X - centroid).sum(axis=1)  # type: ignore[no-any-return]
