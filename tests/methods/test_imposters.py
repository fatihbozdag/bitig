"""Unit tests for `bitig.methods.imposters.GeneralImposters`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bitig.corpus import Corpus
from bitig.corpus.document import Document
from bitig.methods.imposters import GeneralImposters


def _alice_text(seed: int, n_paragraphs: int = 200) -> str:
    rng = np.random.default_rng(seed)
    fw = ["the", "of", "and", "in", "a", "to"]
    cw = ["alice", "garden", "rabbit", "story", "tea"]
    parts: list[str] = []
    for _ in range(n_paragraphs):
        n = int(rng.integers(15, 22))
        sent = " ".join(
            rng.choice(fw, size=n // 2).tolist() + rng.choice(cw, size=n - n // 2).tolist()
        )
        parts.append(sent.capitalize() + ".")
    return " ".join(parts)


def _bob_text(seed: int, n_paragraphs: int = 200) -> str:
    rng = np.random.default_rng(seed)
    fw = ["but", "that", "with", "on", "by", "from"]
    cw = ["bob", "office", "report", "meeting", "memo"]
    parts: list[str] = []
    for _ in range(n_paragraphs):
        n = int(rng.integers(15, 22))
        sent = " ".join(
            rng.choice(fw, size=n // 2).tolist() + rng.choice(cw, size=n - n // 2).tolist()
        )
        parts.append(sent.capitalize() + ".")
    return " ".join(parts)


@pytest.fixture()
def synth_corpus() -> Corpus:
    """Two Alice + two Bob training docs + one Alice-target + one Bob-target."""
    return Corpus(
        documents=[
            Document(id="alice_train_1", text=_alice_text(0), metadata={"author": "Alice"}),
            Document(id="alice_train_2", text=_alice_text(1, 220), metadata={"author": "Alice"}),
            Document(id="bob_train_1", text=_bob_text(2), metadata={"author": "Bob"}),
            Document(id="bob_train_2", text=_bob_text(3, 220), metadata={"author": "Bob"}),
            Document(id="alice_target", text=_alice_text(4, 250), metadata={"author": "Alice"}),
            Document(id="bob_target", text=_bob_text(5, 250), metadata={"author": "Bob"}),
        ]
    )


def test_imposters_verifies_real_alice(synth_corpus: Corpus) -> None:
    """An Alice-flavoured target should score high when candidate=Alice."""
    gi = GeneralImposters(
        target_ids=["alice_target"],
        candidate="Alice",
        group_by="author",
        n_iter=40,
        feature_frac=0.5,
        mfw_n=80,
        seed=42,
    )
    result = gi.fit_transform(synth_corpus)
    assert result.method_name == "general_imposters_burrows"
    table = result.tables[0]
    score = float(table.loc[table["target_id"] == "alice_target", "score"].iloc[0])
    assert score > 0.7, f"score={score}; Alice target should verify against Alice candidate"
    assert bool(table.loc[table["target_id"] == "alice_target", "verified"].iloc[0])


def test_imposters_rejects_bob_as_alice(synth_corpus: Corpus) -> None:
    """A Bob-flavoured target should score low when the candidate is Alice."""
    gi = GeneralImposters(
        target_ids=["bob_target"],
        candidate="Alice",
        group_by="author",
        n_iter=40,
        feature_frac=0.5,
        mfw_n=80,
        seed=42,
    )
    result = gi.fit_transform(synth_corpus)
    score = float(result.tables[0]["score"].iloc[0])
    assert score < 0.3, f"score={score}; Bob target should NOT verify as Alice"
    assert not bool(result.tables[0]["verified"].iloc[0])


def test_imposters_unknown_candidate_raises(synth_corpus: Corpus) -> None:
    gi = GeneralImposters(
        target_ids=["alice_target"], candidate="Carol", group_by="author", n_iter=5, mfw_n=20
    )
    with pytest.raises(ValueError, match="not in training authors"):
        gi.fit_transform(synth_corpus)


def test_imposters_single_author_corpus_raises() -> None:
    one_author = Corpus(
        documents=[
            Document(id="a1", text="the of and in" * 200, metadata={"author": "Alice"}),
            Document(id="a2", text="the of and in" * 200, metadata={"author": "Alice"}),
            Document(id="t1", text="the of and in" * 200, metadata={"author": "Alice"}),
        ]
    )
    gi = GeneralImposters(
        target_ids=["t1"], candidate="Alice", group_by="author", n_iter=5, mfw_n=10
    )
    with pytest.raises(ValueError, match="at least 2 distinct authors"):
        gi.fit_transform(one_author)


def test_imposters_reports_chance_half_for_pairwise(synth_corpus: Corpus) -> None:
    """Default impostor_n=1 → candidate-vs-one-impostor, so chance is exactly
    0.5 and the 0.5 threshold sits at chance (audit P2 #2)."""
    gi = GeneralImposters(
        target_ids=["alice_target"],
        candidate="Alice",
        group_by="author",
        n_iter=20,
        mfw_n=40,
        impostor_n=1,
        seed=7,
    )
    result = gi.fit_transform(synth_corpus)
    assert result.values["chance"] == 0.5
    assert result.tables[0]["chance"].iloc[0] == 0.5
    assert result.tables[0]["impostors_per_iter"].iloc[0] == 1


def test_imposters_chance_scales_with_impostor_n() -> None:
    """With 2 impostors sampled per iteration, chance is 1/(1+2) = 1/3."""

    def _doc(i: int, author: str, toks: list[str]) -> Document:
        rng = np.random.default_rng(i)
        text = " ".join(rng.choice(toks, size=300).tolist())
        return Document(id=f"{author}_{i}", text=text, metadata={"author": author})

    corpus = Corpus(
        documents=[
            _doc(0, "A", ["the", "of", "and", "alice", "garden"]),
            _doc(1, "A", ["the", "of", "and", "alice", "garden"]),
            _doc(2, "B", ["but", "with", "from", "bob", "office"]),
            _doc(3, "B", ["but", "with", "from", "bob", "office"]),
            _doc(4, "C", ["yet", "upon", "into", "carol", "studio"]),
            _doc(5, "C", ["yet", "upon", "into", "carol", "studio"]),
            _doc(6, "A_t", ["the", "of", "and", "alice", "garden"]),
        ]
    )
    # target id must match a real doc; reuse A_6 as the questioned text.
    corpus.documents[6] = Document(
        id="target",
        text=corpus.documents[6].text,
        metadata={"author": "A"},
    )
    gi = GeneralImposters(
        target_ids=["target"],
        candidate="A",
        group_by="author",
        n_iter=10,
        mfw_n=12,
        impostor_n=2,
        seed=1,
    )
    result = gi.fit_transform(corpus)
    assert result.values["chance"] == pytest.approx(1 / 3)
    assert result.tables[0]["impostors_per_iter"].iloc[0] == 2


def test_imposters_invalid_impostor_n_raises() -> None:
    with pytest.raises(ValueError, match="impostor_n"):
        GeneralImposters(target_ids=["x"], candidate="A", group_by="author", impostor_n=0)


def test_imposters_invalid_feature_frac_raises() -> None:
    with pytest.raises(ValueError, match="feature_frac"):
        GeneralImposters(target_ids=["x"], candidate="Alice", group_by="author", feature_frac=0.0)
    with pytest.raises(ValueError, match="feature_frac"):
        GeneralImposters(target_ids=["x"], candidate="Alice", group_by="author", feature_frac=1.5)


def test_imposters_table_round_trips(synth_corpus: Corpus, tmp_path) -> None:
    gi = GeneralImposters(
        target_ids=["alice_target", "bob_target"],
        candidate="Alice",
        group_by="author",
        n_iter=20,
        mfw_n=40,
        seed=42,
    )
    result = gi.fit_transform(synth_corpus)
    result.save(tmp_path)
    parquet = tmp_path / "table_0.parquet"
    assert parquet.exists()
    reloaded = pd.read_parquet(parquet)
    assert list(reloaded["target_id"]) == ["alice_target", "bob_target"]
    assert reloaded["score"].between(0.0, 1.0).all()
