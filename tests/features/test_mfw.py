"""Tests for MFWExtractor — Most Frequent Words."""

import numpy as np
import pytest

from bitig.corpus import Corpus, Document
from bitig.features import FeatureMatrix
from bitig.features.mfw import MFWExtractor


def _corpus(*texts: str) -> Corpus:
    return Corpus(documents=[Document(id=f"d{i}", text=t) for i, t in enumerate(texts)])


def test_mfw_returns_feature_matrix():
    corpus = _corpus("the quick brown fox", "the lazy dog")
    mfw = MFWExtractor(n=5, scale="none")
    fm = mfw.fit_transform(corpus)
    assert isinstance(fm, FeatureMatrix)
    assert fm.X.shape[0] == 2


def test_mfw_selects_top_n_words_by_corpus_frequency():
    corpus = _corpus("the the the cat", "the dog dog")
    mfw = MFWExtractor(n=2, scale="none")
    fm = mfw.fit_transform(corpus)
    assert set(fm.feature_names) == {"the", "dog"}
    assert fm.X.shape[1] == 2


def test_mfw_raw_counts_sum_to_expected_values():
    corpus = _corpus("the cat sat", "the dog sat")
    mfw = MFWExtractor(n=3, scale="none")
    fm = mfw.fit_transform(corpus)
    # Each document has the three tokens: the, <x>, sat.
    # Column order follows fit-order (by frequency desc then alphabetical).
    df = fm.as_dataframe()
    assert df.loc["d0", "the"] == 1
    assert df.loc["d0", "sat"] == 1
    assert df.loc["d1", "the"] == 1


def test_mfw_with_min_df_filters_rare_words():
    corpus = _corpus("a rare unique snowflake", "common common common")
    mfw = MFWExtractor(n=10, min_df=2, scale="none")
    fm = mfw.fit_transform(corpus)
    # Only words appearing in ≥2 docs survive; rare/unique/snowflake filtered out.
    assert "rare" not in fm.feature_names
    assert "common" not in fm.feature_names  # only appears in 1 doc
    # Actually no words survive here — confirm the test's premise explicitly:
    assert fm.X.shape[1] == 0


def test_mfw_z_score_scaling_has_column_mean_zero():
    corpus = _corpus(
        "the the cat cat cat",
        "the dog dog",
        "the the the the dog dog",
    )
    mfw = MFWExtractor(n=3, scale="zscore")
    fm = mfw.fit_transform(corpus)
    # Each column should have mean ~0, std ~1 across the three training docs.
    col_means = fm.X.mean(axis=0)
    col_stds = fm.X.std(axis=0, ddof=0)
    np.testing.assert_allclose(col_means, 0, atol=1e-9)
    # std may be 0 if a feature is constant; where non-zero, it should be 1.
    for std in col_stds:
        assert std == pytest.approx(0.0, abs=1e-9) or std == pytest.approx(1.0, abs=1e-6)


def test_mfw_is_sklearn_compatible():
    # fit then transform on the same corpus produces a result.
    corpus = _corpus("a b c a b", "d e f d")
    mfw = MFWExtractor(n=3, scale="none")
    mfw.fit(corpus)
    fm = mfw.transform(corpus)
    assert fm.X.shape == (2, 3)


def test_mfw_transform_uses_fitted_vocabulary():
    train = _corpus("alpha beta gamma alpha", "beta beta")
    mfw = MFWExtractor(n=2, scale="none")
    mfw.fit(train)
    test = _corpus("alpha zeta zeta zeta")
    # Test doc has `alpha` once and `zeta` thrice, but vocabulary is frozen from train,
    # so we only see counts for train-time vocab.
    fm = mfw.transform(test)
    df = fm.as_dataframe()
    assert df.loc["d0", "alpha"] == 1


def test_mfw_case_folding_by_default_is_off():
    corpus = _corpus("The the THE", "the Cat cat")
    mfw = MFWExtractor(n=5, scale="none", lowercase=False)
    fm = mfw.fit_transform(corpus)
    # Without lowercasing, 'The' and 'THE' are distinct tokens.
    assert "the" in fm.feature_names
    assert "The" in fm.feature_names


def test_mfw_case_folding_when_enabled():
    corpus = _corpus("The the THE", "the Cat cat")
    mfw = MFWExtractor(n=5, scale="none", lowercase=True)
    fm = mfw.fit_transform(corpus)
    assert "the" in fm.feature_names
    assert "The" not in fm.feature_names
    assert "THE" not in fm.feature_names


def test_zscore_uses_relative_frequency_by_document_length() -> None:
    """rel_freq = count / document token count (Burrows / stylo), so a word's value does
    not depend on how many other words are retained (audit 2026-09-26 P2)."""
    from bitig.corpus import Corpus, Document

    corpus = Corpus(
        documents=[
            Document(id="a", text="the the cat sat on a mat"),
            Document(id="b", text="the dog ran far and the cat sat"),
            Document(id="c", text="a b c d e f the"),
        ]
    )
    small = MFWExtractor(n=1, scale="zscore").fit(corpus)
    large = MFWExtractor(n=5, scale="zscore").fit(corpus)
    assert small._vocabulary[0] == large._vocabulary[0] == "the"
    rel = np.array([2 / 7, 2 / 8, 1 / 7])
    expected = (rel - rel.mean()) / rel.std()
    np.testing.assert_allclose(small.transform(corpus).X[:, 0], expected)
    np.testing.assert_allclose(large.transform(corpus).X[:, 0], expected)


def test_project_tokens_matches_transform() -> None:
    from bitig.corpus import Corpus, Document

    corpus = Corpus(
        documents=[
            Document(id="a", text="one two two three three three"),
            Document(id="b", text="three two one one"),
        ]
    )
    mfw = MFWExtractor(n=3, scale="zscore").fit(corpus)
    fm = mfw.transform(corpus)
    for row, doc in enumerate(corpus.documents):
        np.testing.assert_allclose(mfw.project_tokens(mfw.tokenise(doc.text)), fm.X[row])
