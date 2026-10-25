"""Embedding-based feature extractors (optional — bitig[embeddings]).

Two extractors:

- `SentenceEmbeddingExtractor` — sentence-transformers model; pool the whole-document embedding by
  averaging per-sentence embeddings (default) or taking the CLS token.
- `ContextualEmbeddingExtractor` — a raw transformer (e.g. BERT); pool layer-k token embeddings
  by mean or CLS.

Both raise `ImportError` at construction if the optional `bitig[embeddings]` extra is not installed.

When `model=None`, the default model is resolved per-language from `bitig.languages.get_language`
at fit time (so `SentenceEmbeddingExtractor()` on a Turkish corpus picks the Turkish default).
"""

from __future__ import annotations

import importlib.util
from typing import Any, Literal

import numpy as np

from bitig.corpus import Corpus
from bitig.features.base import BaseFeatureExtractor

# Probe for the extra without importing it: importing sentence-transformers pulls in
# transformers and torch, and an incompatible pair (transformers >= 5.19 on the torch < 2.6
# that bitig[turkish] pins) fails with NameError rather than ImportError. A module-level
# import therefore made `import bitig` itself crash; the import now happens on first use.
_sentence_transformers_available = importlib.util.find_spec("sentence_transformers") is not None

Pool = Literal["mean", "cls", "max"]

_INSTALL_HINT = (
    "this extractor requires the optional `bitig[embeddings]` extra — "
    "install with `pip install bitig[embeddings]`"
)


class SentenceEmbeddingExtractor(BaseFeatureExtractor):
    """Sentence-transformer embeddings pooled to one vector per document."""

    feature_type = "sentence_embedding"

    def __init__(
        self,
        *,
        model: str | None = None,
        language: str | None = None,
        pool: Pool = "mean",
        device: str | None = None,
    ) -> None:
        if not _sentence_transformers_available:
            raise ImportError(_INSTALL_HINT)
        self.model = model
        self.language = language
        self.pool = pool
        self.device = device
        self._encoder: Any = None

    def _resolve_model(self, corpus: Corpus) -> None:
        if self.model is None:
            from bitig.languages import get_language

            lang = self.language or corpus.language
            self.model = get_language(lang).sentence_embedding_default

    def _load_encoder(self) -> Any:
        if self._encoder is None:
            assert self.model is not None, "call _resolve_model(corpus) before _load_encoder()"
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(self.model, device=self.device)
        return self._encoder

    def _fit(self, corpus: Corpus) -> None:
        self._resolve_model(corpus)
        self._load_encoder()

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        encoder = self._load_encoder()
        texts = [d.text for d in corpus.documents]
        embeddings = encoder.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        # For pool="mean", sentence-transformers already averages per-sentence; whole-document
        # embedding is the single vector. "cls"/"max" are left as aliases of "mean" here — the
        # model's own pooling layer decides. Users who need a different pooling strategy should
        # use the ContextualEmbeddingExtractor.
        feature_names = [f"emb_{i}" for i in range(embeddings.shape[1])]
        return embeddings.astype(float), feature_names


class ContextualEmbeddingExtractor(BaseFeatureExtractor):
    """Raw HF transformer embeddings — average of layer-k token vectors per document."""

    feature_type = "contextual_embedding"

    def __init__(
        self,
        *,
        model: str | None = None,
        language: str | None = None,
        layer: int = -1,
        pool: Pool = "mean",
        device: str | None = None,
        max_length: int = 512,
    ) -> None:
        if not _sentence_transformers_available:
            raise ImportError(_INSTALL_HINT)
        self.model = model
        self.language = language
        self.layer = layer
        self.pool = pool
        self.device = device
        self.max_length = max_length
        self._tokenizer: Any = None
        self._transformer: Any = None

    def _resolve_model(self, corpus: Corpus) -> None:
        if self.model is None:
            from bitig.languages import get_language

            lang = self.language or corpus.language
            self.model = get_language(lang).contextual_embedding_default

    def _load(self) -> None:
        if self._transformer is None:
            from transformers import AutoModel, AutoTokenizer

            assert self.model is not None, "call _resolve_model(corpus) before _load()"
            self._tokenizer = AutoTokenizer.from_pretrained(self.model)
            self._transformer = AutoModel.from_pretrained(self.model, output_hidden_states=True)
            if self.device:
                self._transformer = self._transformer.to(self.device)
            self._transformer.eval()

    def _fit(self, corpus: Corpus) -> None:
        self._resolve_model(corpus)
        self._load()

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        import torch

        self._load()
        embeddings = []
        with torch.no_grad():
            for doc in corpus.documents:
                encoded = self._tokenizer(
                    doc.text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=self.max_length,
                    padding=False,
                )
                if self.device:
                    encoded = {k: v.to(self.device) for k, v in encoded.items()}
                outputs = self._transformer(**encoded)
                hidden_states = outputs.hidden_states[self.layer]  # (1, tokens, dim)
                if self.pool == "cls":
                    vec = hidden_states[0, 0, :]
                elif self.pool == "max":
                    vec, _ = hidden_states[0].max(dim=0)
                else:  # mean
                    vec = hidden_states[0].mean(dim=0)
                embeddings.append(vec.cpu().numpy())
        X = np.vstack(embeddings).astype(float)  # noqa: N806 (sklearn convention)
        feature_names = [f"emb_{i}" for i in range(X.shape[1])]
        return X, feature_names
