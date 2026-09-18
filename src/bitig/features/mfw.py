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
from bitig.plumbing.textnorm import fold_lower

Scale = Literal["none", "zscore", "l1", "l2"]

_WORD_RE = re.compile(r"[^\W\d_]+", flags=re.UNICODE)


def _tokenise(text: str, lowercase: bool) -> list[str]:
    tokens = _WORD_RE.findall(text)
    return [fold_lower(t) for t in tokens] if lowercase else tokens


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
        z-scores the *relative frequencies* (per-document rates) — the classical Mosteller &
        Wallace / Burrows formulation. "l1" normalises rows to sum to 1 (relative frequencies);
        "l2" normalises rows to unit length.
    frequency_basis : {"document", "vocabulary"}
        Denominator for z-score rates. "document" (default since the September 2026
        correctness update) uses all tokens. "vocabulary" reproduces the historical
        normalization over retained MFW only. This does not change L1/L2 scaling.
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
        frequency_basis: Literal["document", "vocabulary"] = "document",
    ) -> None:
        if scale not in ("none", "zscore", "l1", "l2"):
            raise ValueError(f"unknown scale {scale!r}")
        if frequency_basis not in ("document", "vocabulary"):
            raise ValueError(f"unknown frequency_basis {frequency_basis!r}")
        if n < 1 or min_df < 1 or not 0 < max_df <= 1:
            raise ValueError("n/min_df must be positive and max_df must lie in (0, 1]")
        self.frequency_basis = frequency_basis
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
            # not raw counts. Normalising first ensures longer documents do not dominate.
            X_rel = self._relative_frequencies(corpus)  # noqa: N806 (sklearn convention)
            self._column_means = X_rel.mean(axis=0)
            # Population SD (ddof=0) to match Stylo's convention. Replace zero-stds with 1 to avoid
            # div-by-zero.
            stds = X_rel.std(axis=0, ddof=0)
            stds[stds == 0] = 1.0
            self._column_stds = stds

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        X = self._raw_counts(corpus)  # noqa: N806 (sklearn convention)
        if self.scale == "zscore":
            assert self._column_means is not None and self._column_stds is not None
            X_rel = self._relative_frequencies(corpus)  # noqa: N806
            X = (X_rel - self._column_means) / self._column_stds  # noqa: N806
        elif self.scale == "l1":
            X = self._l1_normalise(X)  # noqa: N806
        elif self.scale == "l2":
            row_norms = np.linalg.norm(X, axis=1, keepdims=True)
            row_norms[row_norms == 0] = 1.0
            X = X / row_norms  # noqa: N806
        # "none" → raw counts, no change.
        return X, list(self._vocabulary)

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
        """Rates for z-scoring; document tokens by default, selected vocabulary for legacy runs."""
        counts = self._raw_counts(corpus)
        if self.frequency_basis == "vocabulary":
            return self._l1_normalise(counts)
        lengths = np.array([len(_tokenise(d.text, self.lowercase)) for d in corpus], dtype=float)
        lengths[lengths == 0] = 1.0
        return np.asarray(counts / lengths[:, None])

    @staticmethod
    def _l1_normalise(X: np.ndarray) -> np.ndarray:  # noqa: N803
        row_sums = X.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        return X / row_sums  # type: ignore[no-any-return]
