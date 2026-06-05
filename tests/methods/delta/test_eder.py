"""Tests for EderDelta and EderSimpleDelta."""

import numpy as np
from sklearn.base import is_classifier

from bitig.features import FeatureMatrix
from bitig.methods.delta.eder import EderDelta, EderSimpleDelta


def _fm(X: np.ndarray) -> FeatureMatrix:  # noqa: N803
    return FeatureMatrix(
        X=X,
        document_ids=[f"d{i}" for i in range(X.shape[0])],
        feature_names=[f"f{j}" for j in range(X.shape[1])],
        feature_type="zscored-mfw",
    )


def test_eder_attributes_to_nearest_centroid() -> None:
    X = np.array([[0.0, 0.0], [0.1, 0.2], [5.0, 5.0], [5.1, 5.2]])
    y = np.array(["A", "A", "B", "B"])
    preds = EderDelta().fit(_fm(X), y).predict(_fm(np.array([[0.05, 0.1], [5.05, 5.1]])))
    assert list(preds) == ["A", "B"]


def test_eder_weights_are_assigned_at_fit_time() -> None:
    X = np.array([[1.0, 2.0], [3.0, 4.0]])
    y = np.array(["A", "B"])
    clf = EderDelta().fit(_fm(X), y)
    assert clf._weights is not None
    assert clf._weights.shape == (2,)


def test_eder_weights_are_frequency_rank_not_data_derived() -> None:
    """Regression (audit P1.14): weights must be a pure function of feature
    POSITION (frequency rank), w_i = (n - i)/n — identical regardless of the
    data, never derived from the class centroids (which would be circular)."""
    y = np.array(["A", "B"])
    expected = np.array([3.0, 2.0, 1.0]) / 3.0  # column 0 = most frequent → 1.0

    w1 = EderDelta().fit(_fm(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])), y)._weights
    # Different data, same feature count → must yield identical weights.
    w2 = EderDelta().fit(_fm(np.array([[9.0, 0.0, 1.0], [0.0, 1.0, 9.0]])), y)._weights

    np.testing.assert_allclose(w1, expected)
    np.testing.assert_allclose(w2, expected)
    # Weights strictly decrease with frequency rank (most-frequent contributes most).
    assert w1[0] > w1[1] > w1[2]


def test_eder_simple_attributes_to_nearest_centroid() -> None:
    X = np.array([[0.0, 0.0], [5.0, 5.0]])
    y = np.array(["A", "B"])
    preds = EderSimpleDelta().fit(_fm(X), y).predict(_fm(np.array([[0.1, 0.1], [4.9, 5.0]])))
    assert list(preds) == ["A", "B"]


def test_eder_is_sklearn_compatible() -> None:
    assert is_classifier(EderDelta())


def test_eder_simple_is_sklearn_compatible() -> None:
    assert is_classifier(EderSimpleDelta())
