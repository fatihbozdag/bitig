"""Tests for Craig's Zeta."""

from __future__ import annotations

from collections import Counter

import pytest

from bitig.corpus import Corpus, Document
from bitig.methods.zeta import ZetaClassic, ZetaEder


def _corpus(*texts: str, groups: list[str]) -> Corpus:
    return Corpus(
        documents=[
            Document(id=f"d{i}", text=t, metadata={"group": g})
            for i, (t, g) in enumerate(zip(texts, groups, strict=True))
        ]
    )


def test_zeta_returns_two_tables() -> None:
    c = _corpus(
        "the cat sat on the mat",
        "the dog ran in the park",
        "rain falls softly on fields",
        "wind blows gently across plains",
        groups=["A", "A", "B", "B"],
    )
    res = ZetaClassic(group_by="group", top_k=3).fit_transform(c)
    # First table: top preferred in A; second: top preferred in B.
    assert len(res.tables) == 2


def test_zeta_distinguishes_preferred_vocab() -> None:
    c = _corpus(
        "alpha alpha alpha beta",
        "alpha alpha gamma",
        "zeta zeta zeta delta",
        "zeta zeta epsilon",
        groups=["A", "A", "B", "B"],
    )
    res = ZetaClassic(group_by="group", top_k=5).fit_transform(c)
    # 'alpha' should dominate group A; 'zeta' should dominate group B.
    top_a = res.tables[0]
    top_b = res.tables[1]
    assert "alpha" in top_a["word"].tolist()
    assert "zeta" in top_b["word"].tolist()


def test_zeta_eder_smooths_with_laplace() -> None:
    c = _corpus(
        "one two three",
        "four five six",
        groups=["A", "B"],
    )
    # Eder's variant applies Laplace smoothing; no division-by-zero on singleton groups.
    res = ZetaEder(group_by="group", top_k=3).fit_transform(c)
    assert len(res.tables) == 2


def test_zeta_eder_smoothing_differs_from_classic() -> None:
    """Regression (audit P1.12): add-k smoothing must actually change the score
    on a zero-count word — the old implementation cancelled to ZetaClassic."""
    # 'alpha' is in both A docs, absent from both B docs.
    count_a: Counter[str] = Counter({"alpha": 2})
    count_b: Counter[str] = Counter()
    n_a = n_b = 2
    vocab = {"alpha"}

    classic = ZetaClassic(group_by="group")._score(count_a, count_b, n_a, n_b, vocab)
    eder = ZetaEder(group_by="group")._score(count_a, count_b, n_a, n_b, vocab)

    # Classic: 2/2 - 0/2 = 1.0
    assert classic["alpha"] == pytest.approx(1.0)
    # Eder (k=0.5): (2+0.5)/(2+1) - (0+0.5)/(2+1) = 2/3
    assert eder["alpha"] == pytest.approx(2.0 / 3.0)
    assert eder["alpha"] != pytest.approx(classic["alpha"])


def test_zeta_eder_not_identical_to_classic_on_corpus() -> None:
    """End-to-end: a word present in A but absent from B must get a different
    zeta under Eder vs Classic."""
    c = _corpus(
        "alpha alpha shared",
        "alpha alpha shared",
        "shared other words",
        "shared other words",
        groups=["A", "A", "B", "B"],
    )
    classic = ZetaClassic(group_by="group", top_k=10).fit_transform(c)
    eder = ZetaEder(group_by="group", top_k=10).fit_transform(c)

    def _zeta_of(res, word: str) -> float:
        for tbl in res.tables:
            hit = tbl[tbl["word"] == word]
            if not hit.empty:
                return float(hit["zeta"].iloc[0])
        raise AssertionError(f"{word!r} not in tables")

    assert _zeta_of(classic, "alpha") != pytest.approx(_zeta_of(eder, "alpha"))


def test_zeta_rejects_fewer_than_two_groups() -> None:
    c = _corpus("hi there", "hello world", groups=["A", "A"])
    with pytest.raises(ValueError, match="at least two groups"):
        ZetaClassic(group_by="group").fit_transform(c)


def test_zeta_supports_custom_group_pair() -> None:
    c = _corpus(
        "alpha alpha",
        "beta beta",
        "gamma gamma",
        groups=["X", "Y", "Z"],
    )
    # Only compare X vs Z.
    res = ZetaClassic(group_by="group", top_k=2, group_a="X", group_b="Z").fit_transform(c)
    top_a = res.tables[0]["word"].tolist()
    assert "alpha" in top_a
    assert "gamma" not in top_a
