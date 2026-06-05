"""Tests for LexicalDiversityExtractor."""

import numpy as np

from bitig.corpus import Corpus, Document
from bitig.features.lexical_diversity import LexicalDiversityExtractor


def _corpus(*texts: str) -> Corpus:
    return Corpus(documents=[Document(id=f"d{i}", text=t) for i, t in enumerate(texts)])


def test_ttr_is_one_for_all_unique_words() -> None:
    ex = LexicalDiversityExtractor(indices=["ttr"])
    fm = ex.fit_transform(_corpus("the quick brown fox"))
    assert fm.as_dataframe().loc["d0", "ttr"] == 1.0


def test_ttr_is_low_for_repetitive_text() -> None:
    ex = LexicalDiversityExtractor(indices=["ttr"])
    fm = ex.fit_transform(_corpus("the the the the the the"))
    # 1 unique / 6 total = 0.1667
    assert fm.as_dataframe().loc["d0", "ttr"] < 0.2


def test_multiple_indices_produce_multiple_columns() -> None:
    ex = LexicalDiversityExtractor(indices=["ttr", "yules_k"])
    fm = ex.fit_transform(_corpus("the quick brown fox jumped over the lazy dog"))
    assert set(fm.feature_names) == {"ttr", "yules_k"}


def test_ldiv_feature_matrix_is_2d_numeric() -> None:
    ex = LexicalDiversityExtractor(indices=["ttr"])
    fm = ex.fit_transform(_corpus("a b c", "a a a"))
    assert fm.X.shape == (2, 1)
    assert np.issubdtype(fm.X.dtype, np.floating)


def test_mtld_diverse_text_scores_above_repetitive() -> None:
    """Regression (audit P1.13): maximally diverse text must score ABOVE
    repetitive text. The old code returned 0.0 for all-unique input, inverting
    the measure."""
    from bitig.features.lexical_diversity import _mtld

    diverse = [f"w{i}" for i in range(100)]  # all unique → TTR never decays
    repetitive = ["the"] * 100  # TTR collapses immediately

    assert _mtld(diverse) > _mtld(repetitive)
    # All-unique floors at the token count (McCarthy & Jarvis 2010), not 0.0.
    assert _mtld(diverse) == 100.0
    assert _mtld(repetitive) < _mtld(diverse)


def test_mtld_index_nonzero_for_diverse_document() -> None:
    """The public extractor must surface the corrected MTLD (not 0) for a
    high-diversity document."""
    ex = LexicalDiversityExtractor(indices=["mtld"])
    fm = ex.fit_transform(_corpus(" ".join(f"w{i}" for i in range(60))))
    assert fm.as_dataframe().loc["d0", "mtld"] > 0.0
