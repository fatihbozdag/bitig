"""MFWExtractor — the most-frequent-words feature table, the classical stylometric input.

Tokenisation is word-boundary based on whitespace + punctuation-stripping (the Stylo default when
using word MFW). For POS-based or dependency-based features, use PosNgramExtractor or
DependencyBigramExtractor, which tokenise via spaCy.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

import numpy as np

from bitig.corpus import Corpus
from bitig.features.base import BaseFeatureExtractor

Scale = Literal["none", "zscore", "l1", "l2"]

_WORD_RE = re.compile(r"[^\W\d_]+", flags=re.UNICODE)


def _tokenise(text: str, lowercase: bool) -> list[str]:
    tokens = _WORD_RE.findall(text)
    return [t.lower() for t in tokens] if lowercase else tokens


class MFWExtractor(BaseFeatureExtractor):
    """Most-Frequent-Words table.

    Parameters
    ----------
    n : int
        Retain the top `n` words by corpus frequency.
    min_df : int
        Drop words appearing in fewer than `min_df` documents.
    max_df : float
        Drop words appearing in more than `max_df` fraction of documents (1.0 disables).
    scale : {"none", "zscore", "l1", "l2"}
        Per-feature scaling applied at transform-time. Burrows Delta requires "zscore", which
        z-scores the *relative frequencies* ``count / document token count`` — the classical
        Mosteller & Wallace / Burrows formulation, as in stylo. "l1" normalises rows to sum
        to 1 over the retained vocabulary; "l2" normalises rows to unit length.
    lowercase : bool
        If True, case-fold before counting.
    """

    feature_type = "mfw"

    def __init__(
        self,
        n: int = 1000,
        *,
        min_df: int = 1,
        max_df: float = 1.0,
        scale: Scale = "zscore",
        lowercase: bool = False,
    ) -> None:
        self.n = n
        self.min_df = min_df
        self.max_df = max_df
        self.scale = scale
        self.lowercase = lowercase
        self._vocabulary: list[str] = []
        self._column_means: np.ndarray | None = None
        self._column_stds: np.ndarray | None = None

    # --- BaseFeatureExtractor API ---

    def _fit(self, corpus: Corpus) -> None:
        n_docs = len(corpus)
        token_doc_freq: Counter[str] = Counter()
        token_total: Counter[str] = Counter()
        for doc in corpus.documents:
            tokens = _tokenise(doc.text, self.lowercase)
            token_total.update(tokens)
            token_doc_freq.update(set(tokens))

        max_allowed = int(self.max_df * n_docs) if self.max_df < 1.0 else n_docs
        candidates = [
            tok
            for tok, count in token_total.items()
            if token_doc_freq[tok] >= self.min_df and token_doc_freq[tok] <= max_allowed
        ]
        # Sort by frequency desc, then alphabetical for determinism.
        candidates.sort(key=lambda t: (-token_total[t], t))
        self._vocabulary = candidates[: self.n]

        if self.scale == "zscore":
            # Burrows Delta z-scores *relative frequencies* (rel_freq = count / doc_length),
            # not raw counts, and not counts renormalised over the retained vocabulary
            # (which made the values depend on n; audit 2026-09-26 P2).
            X_rel = self._relative_frequencies(corpus)  # noqa: N806 (sklearn convention)
            self._column_means = X_rel.mean(axis=0)
            # Population SD (ddof=0) to match Stylo's convention. Replace zero-stds with 1 to avoid
            # div-by-zero.
            stds = X_rel.std(axis=0, ddof=0)
            stds[stds == 0] = 1.0
            self._column_stds = stds

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        if self.scale == "zscore":
            rows = [self.project_tokens(self.tokenise(doc.text)) for doc in corpus.documents]
            X = np.vstack(rows) if rows else np.zeros((0, len(self._vocabulary)))  # noqa: N806
            return X, list(self._vocabulary)
        X = self._raw_counts(corpus)  # noqa: N806 (sklearn convention)
        if self.scale == "l1":
            X = self._l1_normalise(X)  # noqa: N806
        elif self.scale == "l2":
            row_norms = np.linalg.norm(X, axis=1, keepdims=True)
            row_norms[row_norms == 0] = 1.0
            X = X / row_norms  # noqa: N806
        # "none" → raw counts, no change.
        return X, list(self._vocabulary)

    # --- projection helpers (shared with GeneralImposters / RollingDelta) ---

    def tokenise(self, text: str) -> list[str]:
        """Tokenise ``text`` exactly as the extractor does."""
        return _tokenise(text, self.lowercase)

    def project_tokens(self, tokens: list[str]) -> np.ndarray:
        """Z-scored relative-frequency vector for a token sequence (fitted, scale="zscore").

        ``count / len(tokens)`` for each vocabulary word, standardised with the
        fitted column means and SDs. Used for documents and for text windows.
        """
        if self.scale != "zscore" or self._column_means is None or self._column_stds is None:
            raise RuntimeError("project_tokens needs a fitted extractor with scale='zscore'")
        index = {tok: i for i, tok in enumerate(self._vocabulary)}
        counts = np.zeros(len(index), dtype=float)
        for tok in tokens:
            j = index.get(tok)
            if j is not None:
                counts[j] += 1
        rel = counts / (len(tokens) or 1)
        return (rel - self._column_means) / self._column_stds  # type: ignore[no-any-return]

    # --- internals ---

    def _raw_counts(self, corpus: Corpus) -> np.ndarray:
        index = {tok: i for i, tok in enumerate(self._vocabulary)}
        X = np.zeros((len(corpus), len(self._vocabulary)), dtype=float)  # noqa: N806
        for row, doc in enumerate(corpus.documents):
            for tok in _tokenise(doc.text, self.lowercase):
                if tok in index:
                    X[row, index[tok]] += 1
        return X

    def _relative_frequencies(self, corpus: Corpus) -> np.ndarray:
        """Raw counts divided by each document's total token count."""
        lengths = np.array(
            [len(_tokenise(doc.text, self.lowercase)) for doc in corpus.documents], dtype=float
        )
        lengths[lengths == 0] = 1.0
        return self._raw_counts(corpus) / lengths[:, None]  # type: ignore[no-any-return]

    @staticmethod
    def _l1_normalise(X: np.ndarray) -> np.ndarray:  # noqa: N803
        row_sums = X.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        return X / row_sums  # type: ignore[no-any-return]
