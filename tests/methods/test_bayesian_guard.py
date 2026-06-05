"""Regression: BayesianAuthorshipAttributor input validation (audit P1.15).

Kept separate from test_bayesian.py (which is marked slow and exercises the
full PyMC-backed path) so these fast, pymc-free guard checks run in default CI.
``BayesianAuthorshipAttributor`` imports without PyMC (the import is guarded),
so this module collects and runs with only the base deps installed.
"""

from __future__ import annotations

import numpy as np
import pytest

from bitig.features import FeatureMatrix
from bitig.methods.bayesian import BayesianAuthorshipAttributor


def _fm(X: np.ndarray) -> FeatureMatrix:  # noqa: N803
    return FeatureMatrix(
        X=X,
        document_ids=[f"d{i}" for i in range(X.shape[0])],
        feature_names=[f"f{j}" for j in range(X.shape[1])],
        feature_type="counts",
    )


def test_bayesian_rejects_negative_counts() -> None:
    """z-scored / mean-centred features (which contain negatives) must be
    rejected, not silently clipped to a confident-but-invalid prediction."""
    X = np.array([[1.0, -2.0, 3.0], [0.0, 1.0, -1.0]])  # looks z-scored
    y = np.array(["A", "B"])
    with pytest.raises(ValueError, match="non-negative count"):
        BayesianAuthorshipAttributor().fit(_fm(X), y)


def test_bayesian_accepts_nonnegative_counts() -> None:
    X = np.array([[3.0, 0.0, 1.0], [0.0, 2.0, 1.0]])
    y = np.array(["A", "B"])
    clf = BayesianAuthorshipAttributor().fit(_fm(X), y)
    assert set(clf.classes_) == {"A", "B"}
    # Sanity: each row attributes to some known class.
    assert set(clf.predict(_fm(X))).issubset({"A", "B"})


def test_bayesian_zero_prior_empty_class_raises() -> None:
    """With prior_alpha=0 and an all-zero class, the rate vector is undefined."""
    X = np.array([[0.0, 0.0], [2.0, 3.0]])
    y = np.array(["empty", "real"])
    with pytest.raises(ValueError, match="zero total smoothed count"):
        BayesianAuthorshipAttributor(prior_alpha=0.0).fit(_fm(X), y)
