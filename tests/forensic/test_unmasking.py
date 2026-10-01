"""Tests for the Unmasking authorship-verification method (Koppel & Schler 2004)."""

from __future__ import annotations

import numpy as np
import pytest

from bitig.corpus import Corpus, Document
from bitig.features import MFWExtractor
from bitig.forensic.unmasking import Unmasking


def _make_vocab(size: int) -> list[str]:
    """Letter-only tokens (MFWExtractor's regex excludes digits)."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    vocab = []
    for i in range(size):
        a, b = divmod(i, len(letters))
        vocab.append(letters[a] + letters[b])
    return vocab


def _sample_text(
    profile: np.ndarray, vocab: list[str], n_words: int, rng: np.random.Generator
) -> str:
    toks = rng.choice(vocab, size=n_words, p=profile).tolist()
    return " ".join(toks)


def _two_profile_texts(
    seed: int = 0, n_words: int = 3000, vocab_size: int = 60
) -> tuple[str, str, str]:
    """Build three long texts: two from profile A (same-author-ish) and one from profile B.

    Profile A concentrates mass on the first half of the vocabulary; profile B on the
    second half. The split makes MFW features for Q_same vs K look similar and for Q_diff
    vs K look distinct.
    """
    rng = np.random.default_rng(seed)
    vocab = _make_vocab(vocab_size)
    half = vocab_size // 2
    profile_a = np.zeros(vocab_size)
    profile_a[:half] = rng.dirichlet(np.ones(half) * 0.5) * 0.9
    profile_a[half:] = rng.dirichlet(np.ones(vocab_size - half) * 0.5) * 0.1
    profile_a /= profile_a.sum()
    profile_b = np.zeros(vocab_size)
    profile_b[half:] = rng.dirichlet(np.ones(vocab_size - half) * 0.5) * 0.9
    profile_b[:half] = rng.dirichlet(np.ones(half) * 0.5) * 0.1
    profile_b /= profile_b.sum()
    q_same = _sample_text(profile_a, vocab, n_words, rng)
    q_diff = _sample_text(profile_b, vocab, n_words, rng)
    k = _sample_text(profile_a, vocab, n_words, rng)
    return q_same, q_diff, k


class TestUnmaskingDiscrimination:
    def test_different_author_initial_accuracy_higher_than_same_author(self) -> None:
        """On disjoint-profile synthetic data, the round-0 classifier easily separates Q
        from K when they come from different profiles (initial accuracy near 1.0), and
        struggles when Q and K come from the same profile (initial accuracy near 0.5).
        This is a robust invariant across seeds."""
        q_same, q_diff, k = _two_profile_texts(seed=0, n_words=4000, vocab_size=50)
        unmasking = Unmasking(chunk_size=400, n_rounds=4, n_eliminate=2, n_folds=4, seed=42)
        extractor = MFWExtractor(n=30, scale="zscore", lowercase=True)

        r_same = unmasking.verify(questioned=q_same, known=k, extractor=extractor)
        r_diff = unmasking.verify(questioned=q_diff, known=k, extractor=extractor)

        assert r_diff.values["accuracy_initial"] > r_same.values["accuracy_initial"] + 0.2

    def test_feature_elimination_reduces_discriminative_signal(self) -> None:
        """The core Koppel & Schler claim specific to the per-class-elimination procedure:
        when the classifier starts with strong discrimination (different-author case), the
        per-class feature elimination should drive accuracy DOWN across rounds (not
        stay flat). Tests that the procedure actually eliminates discriminative features."""
        _, q_diff, k = _two_profile_texts(seed=0, n_words=4000, vocab_size=50)
        unmasking = Unmasking(chunk_size=400, n_rounds=8, n_eliminate=3, n_folds=4, seed=42)
        extractor = MFWExtractor(n=30, scale="zscore", lowercase=True)
        result = unmasking.verify(questioned=q_diff, known=k, extractor=extractor)
        curve = result.values["accuracy_curve"]
        # Final accuracy must be meaningfully below initial: features were removed and the
        # classifier cannot recover its initial discrimination.
        assert curve[0] - curve[-1] > 0.1

    def test_accuracy_curve_has_correct_length(self) -> None:
        q, _, k = _two_profile_texts(seed=1)
        unmasking = Unmasking(chunk_size=400, n_rounds=5, n_eliminate=2, n_folds=3, seed=0)
        result = unmasking.verify(
            questioned=q, known=k, extractor=MFWExtractor(n=30, lowercase=True, scale="zscore")
        )
        assert len(result.values["accuracy_curve"]) == 5


class TestUnmaskingReproducibility:
    def test_same_seed_produces_identical_curve(self) -> None:
        q, _, k = _two_profile_texts(seed=2)
        extractor = MFWExtractor(n=20, scale="zscore", lowercase=True)
        params = {"chunk_size": 400, "n_rounds": 4, "n_eliminate": 2, "n_folds": 3}
        a = Unmasking(seed=7, **params).verify(questioned=q, known=k, extractor=extractor)
        b = Unmasking(seed=7, **params).verify(questioned=q, known=k, extractor=extractor)
        assert a.values["accuracy_curve"] == b.values["accuracy_curve"]


class TestUnmaskingResultContract:
    def test_result_carries_full_provenance(self) -> None:
        q, _, k = _two_profile_texts(seed=3)
        unmasking = Unmasking(chunk_size=400, n_rounds=3, n_eliminate=2, n_folds=3, seed=1)
        extractor = MFWExtractor(n=15, scale="zscore", lowercase=True)
        result = unmasking.verify(questioned=q, known=k, extractor=extractor)
        assert result.method_name == "unmasking"
        for key in (
            "chunk_size",
            "n_rounds",
            "n_eliminate",
            "n_folds",
            "seed",
            "extractor",
            "n_features_initial",
        ):
            assert key in result.params
        for key in (
            "accuracy_curve",
            "accuracy_drop",
            "accuracy_initial",
            "accuracy_final",
            "n_q_chunks",
            "n_k_chunks",
            "eliminated_per_round",
        ):
            assert key in result.values
        # Basic invariants.
        curve = result.values["accuracy_curve"]
        assert all(0.0 <= x <= 1.0 for x in curve)
        assert result.values["accuracy_initial"] == curve[0]
        assert result.values["accuracy_final"] == curve[-1]
        assert result.values["accuracy_drop"] == curve[0] - curve[-1]


class TestUnmaskingInputValidation:
    def test_too_few_chunks_raises(self) -> None:
        short_text = "a b c d e"  # 5 words → 1 chunk at chunk_size=500
        unmasking = Unmasking(chunk_size=500, min_chunks_per_class=3)
        extractor = MFWExtractor(n=5, scale="zscore", lowercase=True)
        with pytest.raises(ValueError, match="at least"):
            unmasking.verify(questioned=short_text, known="x y z " * 1000, extractor=extractor)

    def test_rejects_non_text_input(self) -> None:
        unmasking = Unmasking()
        extractor = MFWExtractor(n=5, scale="zscore", lowercase=True)
        with pytest.raises(TypeError, match="Corpus, Document, or str"):
            unmasking.verify(questioned=42, known="a b c", extractor=extractor)  # type: ignore[arg-type]

    def test_invalid_constructor_args(self) -> None:
        with pytest.raises(ValueError, match="chunk_size"):
            Unmasking(chunk_size=0)
        with pytest.raises(ValueError, match="n_rounds"):
            Unmasking(n_rounds=0)
        with pytest.raises(ValueError, match="n_eliminate"):
            Unmasking(n_eliminate=0)
        with pytest.raises(ValueError, match="n_folds"):
            Unmasking(n_folds=1)
        with pytest.raises(ValueError, match="min_chunks_per_class"):
            Unmasking(min_chunks_per_class=1)


class TestUnmaskingInputFormats:
    """verify() should accept raw str, Document, or Corpus inputs symmetrically."""

    def test_corpus_input_chunks_each_document_separately(self) -> None:
        # Two 2000-word documents → ~8 chunks at chunk_size=500.
        rng = np.random.default_rng(0)
        vocab = _make_vocab(40)
        profile = rng.dirichlet(np.ones(40) * 0.5)
        text_a = " ".join(rng.choice(vocab, size=2000, p=profile).tolist())
        text_b = " ".join(rng.choice(vocab, size=2000, p=profile).tolist())
        corpus = Corpus(
            documents=[
                Document(id="a", text=text_a),
                Document(id="b", text=text_b),
            ]
        )
        unmasking = Unmasking(chunk_size=500, n_rounds=3, n_eliminate=2, n_folds=3, seed=0)
        extractor = MFWExtractor(n=15, scale="zscore", lowercase=True)
        long_known = " ".join(rng.choice(vocab, size=2000, p=profile).tolist())
        result = unmasking.verify(questioned=corpus, known=long_known, extractor=extractor)
        # Each 2000-word doc yields 4 chunks -> 8 total.
        assert result.values["n_q_chunks"] == 8


def test_short_tail_is_merged_not_a_sample() -> None:
    """1001 words / chunk 500 gave chunks [500, 500, 1]; the 1-word tail counted
    toward min_chunks_per_class (audit 2026-09-26 P2)."""
    from bitig.forensic.unmasking import _chunk_text

    text = " ".join(f"w{i}" for i in range(1001))
    assert [len(d.text.split()) for d in _chunk_text(text, chunk_size=500, id_prefix="Q")] == [
        500,
        501,
    ]
    text = " ".join(f"w{i}" for i in range(1300))  # tail of 300 >= half a chunk: kept
    assert [len(d.text.split()) for d in _chunk_text(text, chunk_size=500, id_prefix="Q")] == [
        500,
        500,
        300,
    ]
