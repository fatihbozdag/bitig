"""Tests for Bayesian authorship attribution — requires bitig[bayesian]."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.base import is_classifier

from bitig.corpus import Corpus, Document
from bitig.features import MFWExtractor

pytestmark = pytest.mark.slow


def _corpus() -> Corpus:
    rng = np.random.default_rng(42)
    docs = []
    for i in range(20):
        author = "A" if i < 10 else "B"
        # Author A prefers "alpha"; Author B prefers "beta".
        text = " ".join(
            rng.choice(
                ["alpha", "beta", "gamma", "delta", "epsilon"],
                size=200,
                p=[0.4, 0.1, 0.2, 0.2, 0.1] if author == "A" else [0.1, 0.4, 0.2, 0.2, 0.1],
            )
        )
        docs.append(Document(id=f"d{i}", text=text, metadata={"author": author}))
    return Corpus(documents=docs)


def test_bayesian_attributor_is_classifier() -> None:
    from bitig.methods.bayesian import BayesianAuthorshipAttributor

    assert is_classifier(BayesianAuthorshipAttributor())


def test_bayesian_attributor_separates_two_authors() -> None:
    from bitig.methods.bayesian import BayesianAuthorshipAttributor

    corpus = _corpus()
    y = np.array(corpus.metadata_column("author"))
    fm = MFWExtractor(n=5, scale="none", lowercase=True).fit_transform(corpus)
    clf = BayesianAuthorshipAttributor(prior_alpha=0.5).fit(fm, y)
    preds = clf.predict(fm)
    # On in-sample data with strong author-word associations, accuracy should be near 1.
    assert (preds == y).mean() >= 0.8


def test_bayesian_attributor_predict_proba_sums_to_one() -> None:
    from bitig.methods.bayesian import BayesianAuthorshipAttributor

    corpus = _corpus()
    y = np.array(corpus.metadata_column("author"))
    fm = MFWExtractor(n=5, scale="none", lowercase=True).fit_transform(corpus)
    clf = BayesianAuthorshipAttributor().fit(fm, y)
    probs = clf.predict_proba(fm)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-9)


def test_bayesian_raises_clear_error_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    from bitig.methods import bayesian

    monkeypatch.setattr(bayesian, "_pymc_available", False)
    with pytest.raises(ImportError, match=r"bitig\[bayesian\]"):
        bayesian.HierarchicalGroupComparison(group_by="author")


class TestAuthorToGroupIdx:
    """Regression tests for _build_author_to_group_idx.

    Previously (bayesian.py:150-157 prior to fix), the hierarchical model silently
    collapsed to a flat prior whenever len(unique_authors) != len(groups), which is
    true in every realistic corpus. These tests lock in the correct per-author
    group index so the hierarchy cannot collapse again.
    """

    def test_author_group_index_typical_corpus(self) -> None:
        from bitig.methods.bayesian import _build_author_to_group_idx

        y = np.array(["alice", "alice", "bob", "carol", "carol"])
        groups = np.array(["L1", "L1", "L1", "L2", "L2"])
        unique_authors = np.unique(y)
        unique_groups = np.unique(groups)
        idx = _build_author_to_group_idx(y, groups, unique_authors, unique_groups)
        # unique_authors = ["alice", "bob", "carol"], unique_groups = ["L1", "L2"]
        assert idx.tolist() == [0, 0, 1]

    def test_author_group_index_raises_on_conflicting_group(self) -> None:
        from bitig.methods.bayesian import _build_author_to_group_idx

        y = np.array(["alice", "alice"])
        groups = np.array(["L1", "L2"])  # same author, two groups
        unique_authors = np.unique(y)
        unique_groups = np.unique(groups)
        with pytest.raises(ValueError, match="multiple groups"):
            _build_author_to_group_idx(y, groups, unique_authors, unique_groups)

    def test_author_group_index_preserves_unique_authors_order(self) -> None:
        from bitig.methods.bayesian import _build_author_to_group_idx

        y = np.array(["bob", "alice", "bob", "alice"])
        groups = np.array(["G1", "G2", "G1", "G2"])
        unique_authors = np.unique(y)  # ["alice", "bob"]
        unique_groups = np.unique(groups)  # ["G1", "G2"]
        idx = _build_author_to_group_idx(y, groups, unique_authors, unique_groups)
        assert idx.tolist() == [1, 0]  # alice→G2(idx 1), bob→G1(idx 0)


def test_attributor_rejects_negative_or_nan_input_at_predict_time() -> None:
    """The fit-time guard (audit P1.15) now also covers predict (audit 2026-09-26)."""
    import pytest

    from bitig.methods.bayesian import BayesianAuthorshipAttributor

    clf = BayesianAuthorshipAttributor().fit(
        np.array([[3.0, 1.0], [0.0, 4.0]]), np.array(["a", "b"])
    )
    with pytest.raises(ValueError, match="non-negative"):
        clf.predict(np.array([[-0.5, 1.2]]))
    with pytest.raises(ValueError, match="NaN"):
        clf.predict_proba(np.array([[np.nan, 1.0]]))


@pytest.mark.slow
def test_hierarchical_model_uses_sigma_group_and_standardises() -> None:
    pytest.importorskip("pymc")
    from bitig.features import FeatureMatrix
    from bitig.methods.bayesian import HierarchicalGroupComparison

    rng = np.random.default_rng(0)
    values = np.r_[rng.normal(100, 5, 6), rng.normal(130, 5, 6)]  # Yule's-K-like scale
    fm = FeatureMatrix(
        X=values[:, None],
        document_ids=[f"d{i}" for i in range(12)],
        feature_names=["yules_k"],
        feature_type="lexical_diversity",
    )
    authors = np.array([f"a{i // 2}" for i in range(12)])
    groups = np.array(["L1"] * 6 + ["L2"] * 6)
    out = HierarchicalGroupComparison(
        group_by="g", chains=1, samples=200, tune=200, seed=1
    ).fit_transform(fm, authors, groups)
    res = out["results"][0]
    assert res["standardisation"]["mean"] == pytest.approx(values.mean())
    summary_rows = res["mu_group_summary"]["mean"]
    assert any(str(k).startswith("sigma_group") for k in summary_rows)
    mu = [v for k, v in summary_rows.items() if str(k).startswith("mu_group")]
    assert mu[0] < 0 < mu[1]  # L1 below the mean, L2 above, in SD units
