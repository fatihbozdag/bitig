"""Categorized character n-grams for cross-topic authorship attribution.

Classical character n-gram features mix together stylistic signal (morphological habits,
punctuation patterns) and topical signal (content words that happen to be n-chars long).
On forensic data that crosses topics — e.g., a threat letter vs. a personal email from the
same suspect — pure character n-gram models often collapse to topic detection.

Sapkota, Bethard, Montes-y-Gomez, and Solorio (2015) showed that different *categories* of
character n-gram carry very different cross-topic robustness:

- **affix** n-grams (prefix / suffix) are morphological; they generalise across topics.
- **whole-word** and **mid-word** n-grams are often topical.
- **punct** and **space-***  n-grams capture layout / punctuation habits; robust across topics.

Selecting only affix + punct n-grams routinely beats unfiltered character n-grams on
cross-topic PAN tasks. ``CategorizedCharNgramExtractor`` exposes this filter as a first-class
forensic feature.

References
----------
Sapkota, U., Bethard, S., Montes-y-Gomez, M., & Solorio, T. (2015). Not all character
    n-grams are created equal: A study in authorship attribution. Proceedings of NAACL-HLT
    2015, 93-102.
Stamatatos, E. (2013). On the robustness of authorship attribution based on character
    n-gram features. Journal of Law and Policy, 21(2), 421-439.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

import numpy as np

from bitig.corpus import Corpus
from bitig.features.base import BaseFeatureExtractor
from bitig.plumbing.textnorm import fold_lower

Category = Literal[
    "prefix",  # word-start + char-internal ("the" in "there")
    "suffix",  # char-internal + word-end ("ing" in "running")
    "whole_word",  # exactly one word, boundaries at both ends ("the")
    "mid_word",  # entirely internal to a single word
    "multi_word",  # spans a whitespace between two words (without being whole-word)
    "punct",  # contains any punctuation character
    "space",  # contains whitespace but no punctuation (non-multi-word spacing)
]
Scale = Literal["none", "zscore", "l1", "l2"]

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_ALL_CATEGORIES: tuple[Category, ...] = (
    "prefix",
    "suffix",
    "whole_word",
    "mid_word",
    "multi_word",
    "punct",
    "space",
)


def classify_ngram(ngram: str, left: str, right: str) -> Category:
    """Classify a single n-gram occurrence.

    The n-gram string itself is insufficient — its category depends on the *context* in
    which it was extracted. ``left`` and ``right`` are the characters immediately before
    and after the n-gram occurrence (or an empty string at document boundaries).

    Priority order (following Sapkota et al. 2015 convention):

    1. ``punct`` — any punctuation character inside the n-gram wins immediately.
    2. ``whole_word`` — both the left and right neighbours are spaces (or empty) AND the
       n-gram contains no internal whitespace.
    3. ``multi_word`` — contains internal whitespace.
    4. ``prefix`` — left neighbour is space/empty and the last char is a word-internal
       letter.
    5. ``suffix`` — right neighbour is space/empty and the first char is word-internal.
    6. ``space`` — contains whitespace but not enough of a word-boundary match for the
       above categories (rare; gaps at the start or end).
    7. ``mid_word`` — otherwise.
    """
    if _PUNCT_RE.search(ngram):
        return "punct"
    left_boundary = left == "" or left.isspace()
    right_boundary = right == "" or right.isspace()
    contains_space = any(ch.isspace() for ch in ngram)
    if left_boundary and right_boundary and not contains_space:
        return "whole_word"
    if contains_space:
        # At least one internal space; classify as multi-word unless it's solely
        # leading/trailing whitespace.
        internal = ngram.strip()
        if internal and " " in internal:
            return "multi_word"
        return "space"
    if left_boundary and not right_boundary:
        return "prefix"
    if right_boundary and not left_boundary:
        return "suffix"
    return "mid_word"


def _validate_categories(categories: Iterable[Category] | None) -> tuple[Category, ...]:
    if categories is None:
        return _ALL_CATEGORIES
    validated = tuple(categories)
    for c in validated:
        if c not in _ALL_CATEGORIES:
            raise ValueError(f"unknown category {c!r}; known: {sorted(_ALL_CATEGORIES)}")
    if not validated:
        raise ValueError("categories must be non-empty")
    return validated


def _iter_ngrams_with_context(text: str, n: int) -> Iterable[tuple[str, str, str]]:
    """Yield (ngram, left_char, right_char) for every n-gram window in ``text``."""
    if len(text) < n:
        return
    for i in range(len(text) - n + 1):
        ngram = text[i : i + n]
        left = text[i - 1] if i > 0 else ""
        right = text[i + n] if i + n < len(text) else ""
        yield ngram, left, right


class CategorizedCharNgramExtractor(BaseFeatureExtractor):
    """Character n-gram extractor that filters n-gram *occurrences* by Sapkota category.

    Unlike :class:`CharNgramExtractor`, this classifier counts each OCCURRENCE of an n-gram
    separately and tags it with the category of its position in the source text. The n-gram
    string ``"the"`` can therefore contribute to multiple category channels.

    Feature columns are named ``"<ngram>|<category>"`` so the origin of each column is
    explicit and auditable.

    Parameters
    ----------
    n : int
        N-gram order (fixed int, no range — ranges are an easy extension but complicate the
        classification logic enough to be deferred).
    categories : iterable of Category, optional
        Which categories to retain. Default: all 7. Set to ``("prefix", "suffix")`` to get
        the cross-topic-robust affix-only feature set that Sapkota et al. recommend.
    scale : {"none", "zscore", "l1", "l2"}
        Per-feature scaling applied at transform-time. Same semantics as CharNgramExtractor.
    lowercase : bool
        Case-fold before extracting n-grams.

    Examples
    --------
    >>> # Cross-topic-robust forensic feature set:
    >>> extractor = CategorizedCharNgramExtractor(
    ...     n=3, categories=("prefix", "suffix", "punct"), scale="zscore", lowercase=True
    ... )
    """

    feature_type = "categorized_char_ngram"

    def __init__(
        self,
        n: int = 3,
        *,
        categories: Iterable[Category] | None = None,
        scale: Scale = "none",
        lowercase: bool = False,
    ) -> None:
        if n < 1:
            raise ValueError("n must be >= 1")
        self.n = n
        self.categories = categories
        self.scale: Scale = scale
        self.lowercase = lowercase
        self._keep_categories: tuple[Category, ...] = _validate_categories(categories)
        self._vocabulary: list[str] = []
        self._column_means: np.ndarray | None = None
        self._column_stds: np.ndarray | None = None

    def _fit(self, corpus: Corpus) -> None:
        vocab: set[str] = set()
        for doc in corpus.documents:
            text = fold_lower(doc.text) if self.lowercase else doc.text
            for ngram, left, right in _iter_ngrams_with_context(text, self.n):
                category = classify_ngram(ngram, left, right)
                if category in self._keep_categories:
                    vocab.add(f"{ngram}|{category}")
        # Sort for deterministic column order.
        self._vocabulary = sorted(vocab)

        if self.scale == "zscore":
            X = self._raw_counts(corpus)  # noqa: N806
            self._column_means = X.mean(axis=0)
            stds = X.std(axis=0, ddof=0)
            stds[stds == 0] = 1.0
            self._column_stds = stds

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        X = self._raw_counts(corpus)  # noqa: N806
        if self.scale == "zscore":
            assert self._column_means is not None and self._column_stds is not None
            X = (X - self._column_means) / self._column_stds  # noqa: N806
        elif self.scale == "l1":
            row_sums = X.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1.0
            X = X / row_sums  # noqa: N806
        elif self.scale == "l2":
            row_norms = np.linalg.norm(X, axis=1, keepdims=True)
            row_norms[row_norms == 0] = 1.0
            X = X / row_norms  # noqa: N806
        return X, list(self._vocabulary)

    def _raw_counts(self, corpus: Corpus) -> np.ndarray:
        index = {tok: i for i, tok in enumerate(self._vocabulary)}
        X = np.zeros((len(corpus), len(self._vocabulary)), dtype=float)  # noqa: N806
        for row, doc in enumerate(corpus.documents):
            text = fold_lower(doc.text) if self.lowercase else doc.text
            for ngram, left, right in _iter_ngrams_with_context(text, self.n):
                category = classify_ngram(ngram, left, right)
                if category in self._keep_categories:
                    key = f"{ngram}|{category}"
                    idx = index.get(key)
                    if idx is not None:
                        X[row, idx] += 1
        return X
