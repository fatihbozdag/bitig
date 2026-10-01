"""Tests for embedding-based feature extractors — requires bitig[embeddings]."""

from __future__ import annotations

import pytest

from bitig.corpus import Corpus, Document

# bitig.features.embeddings imports without the extra (the heavy deps load lazily), so
# guard on the optional dependency itself (audit 2026-09-26: the old guard never skipped).
pytest.importorskip("sentence_transformers", reason="requires bitig[embeddings]")

from bitig.features.embeddings import (
    ContextualEmbeddingExtractor,
    SentenceEmbeddingExtractor,
)

pytestmark = pytest.mark.slow  # Model loading is slow.

_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _corpus(*texts: str) -> Corpus:
    return Corpus(documents=[Document(id=f"d{i}", text=t) for i, t in enumerate(texts)])


def test_sentence_embedding_extractor_produces_fixed_dim() -> None:
    from bitig.features.embeddings import SentenceEmbeddingExtractor

    ex = SentenceEmbeddingExtractor(model=_MODEL, pool="mean")
    fm = ex.fit_transform(_corpus("Hello world.", "The quick brown fox jumped."))
    # all-MiniLM-L6-v2 is 384-dim.
    assert fm.X.shape == (2, 384)
    assert fm.feature_names[:3] == ["emb_0", "emb_1", "emb_2"]


def test_sentence_embedding_similar_texts_have_high_cosine_sim() -> None:
    from bitig.features.embeddings import SentenceEmbeddingExtractor

    ex = SentenceEmbeddingExtractor(model=_MODEL, pool="mean")
    fm = ex.fit_transform(
        _corpus(
            "The cat sat on the mat.",
            "A cat was sitting on the mat.",
            "Quantum chromodynamics governs strong interactions.",
        )
    )
    from sklearn.metrics.pairwise import cosine_similarity

    sims = cosine_similarity(fm.X)
    # First two are near-paraphrases; third is unrelated physics.
    assert sims[0, 1] > sims[0, 2]
    assert sims[0, 1] > sims[1, 2]


def test_sentence_embedding_handles_empty_text() -> None:
    from bitig.features.embeddings import SentenceEmbeddingExtractor

    ex = SentenceEmbeddingExtractor(model=_MODEL, pool="mean")
    fm = ex.fit_transform(_corpus("", "hello"))
    assert fm.X.shape == (2, 384)


def test_embeddings_raises_clear_error_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """If sentence-transformers is absent, import/construction raises an informative error."""
    from bitig.features import embeddings

    # Simulate missing dep by breaking the import path temporarily.
    monkeypatch.setattr(embeddings, "_sentence_transformers_available", False)
    with pytest.raises(ImportError, match=r"bitig\[embeddings\]"):
        embeddings.SentenceEmbeddingExtractor(model=_MODEL, pool="mean")


def test_sentence_embedding_resolves_english_default_model() -> None:
    ex = SentenceEmbeddingExtractor()  # no model= specified
    # Resolution is lazy — happens at _fit. We inspect the stored model after construction.
    # The extractor should remember the language (default 'en') and resolve later.
    # Simulate: pretend _fit was called with an English corpus.
    c = Corpus(documents=[Document(id="d0", text="x")], language="en")
    ex._resolve_model(c)
    assert ex.model == "sentence-transformers/all-mpnet-base-v2"


def test_sentence_embedding_resolves_turkish_default_model() -> None:
    ex = SentenceEmbeddingExtractor()
    c = Corpus(documents=[Document(id="d0", text="x")], language="tr")
    ex._resolve_model(c)
    assert ex.model == "emrecan/bert-base-turkish-cased-mean-nli-stsb-tr"


def test_contextual_embedding_resolves_default_from_language() -> None:
    ex = ContextualEmbeddingExtractor()
    c = Corpus(documents=[Document(id="d0", text="x")], language="tr")
    ex._resolve_model(c)
    assert ex.model == "dbmdz/bert-base-turkish-cased"


def test_explicit_model_overrides_language_default() -> None:
    ex = SentenceEmbeddingExtractor(model="custom/model-name")
    c = Corpus(documents=[Document(id="d0", text="x")], language="tr")
    ex._resolve_model(c)
    assert ex.model == "custom/model-name"
