"""Tests for LexicalDiversityExtractor."""

import math

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

    # No factor ever completes for all-unique text: MTLD is undefined (NaN),
    # never 0.0, the minimum (audit 2026-09-26: the token-count floor made one
    # repeated token jump the score from 100 to 2800).
    assert math.isnan(_mtld(diverse))
    assert math.isnan(_mtld([*diverse[:99], "w0"]))
    assert _mtld(repetitive) > 0


def test_mtld_index_nonzero_for_diverse_document() -> None:
    """The public extractor surfaces a positive MTLD for a diverse document that
    completes at least one factor."""
    ex = LexicalDiversityExtractor(indices=["mtld"])
    text = " ".join(f"w{i % 40}" for i in range(400))  # 40 types, cycling
    fm = ex.fit_transform(_corpus(text))
    assert fm.as_dataframe().loc["d0", "mtld"] > 0.0


def test_undefined_measures_are_nan_with_a_warning() -> None:
    import pytest

    from bitig.corpus import Corpus, Document
    from bitig.features.lexical_diversity import _hdd, _yules_i

    assert math.isnan(_hdd(["a"] * 41))  # below the 42-token sample
    assert math.isnan(_yules_i(["a", "b", "c"]))  # every token a hapax
    # Canonical Yule's I = V^2 / (M2 - V): tokens a a b -> V=2, M2=4+1=5 -> 4/3.
    assert _yules_i(["a", "a", "b"]) == pytest.approx(4 / 3)
    with pytest.warns(UserWarning, match="d0:hdd"):
        LexicalDiversityExtractor(indices=["hdd"]).fit_transform(
            Corpus(documents=[Document(id="d0", text="short text")])
        )


def test_runner_refuses_nan_features(tmp_path) -> None:
    import pytest
    import yaml

    from bitig.runner import run_study

    (tmp_path / "c").mkdir()
    for i in range(3):
        (tmp_path / "c" / f"d{i}.txt").write_text("a short text", encoding="utf-8")
    study = {
        "name": "t",
        "corpus": {"path": str(tmp_path / "c")},
        "features": [{"id": "ld", "type": "lexical_diversity", "indices": ["hdd"]}],
        "methods": [{"id": "p", "kind": "reduce", "features": "ld", "n_components": 1}],
        "output": {"dir": str(tmp_path / "out")},
    }
    path = tmp_path / "s.yaml"
    path.write_text(yaml.safe_dump(study), encoding="utf-8")
    with pytest.warns(UserWarning), pytest.raises(ValueError, match="NaN"):
        run_study(path)
