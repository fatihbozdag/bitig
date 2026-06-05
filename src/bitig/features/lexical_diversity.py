"""Lexical-diversity indices: TTR, MATTR, MTLD, HD-D, Yule's K, Yule's I, Herdan's C, Simpson's D."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

import numpy as np

from bitig.corpus import Corpus
from bitig.features.base import BaseFeatureExtractor

_WORD_RE = re.compile(r"[^\W\d_]+", flags=re.UNICODE)

_DEFAULT_INDICES = ("ttr", "yules_k")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text)]


def _ttr(tokens: list[str]) -> float:
    return len(set(tokens)) / len(tokens) if tokens else 0.0


def _yules_k(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    n = len(tokens)
    freq = Counter(tokens)
    freq_of_freq = Counter(freq.values())
    s2 = sum(r * r * f for r, f in freq_of_freq.items())
    return 1e4 * (s2 - n) / (n * n) if n > 0 else 0.0


def _yules_i(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    n = len(tokens)
    freq = Counter(tokens)
    freq_of_freq = Counter(freq.values())
    s2 = sum(r * r * f for r, f in freq_of_freq.items())
    v = len(freq)
    return (v * v) / (s2 - n) if (s2 - n) > 0 else 0.0


def _herdans_c(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    v = len(set(tokens))
    n = len(tokens)
    return float(np.log(v) / np.log(n)) if n > 1 else 0.0


def _simpsons_d(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    freq = Counter(tokens)
    n = len(tokens)
    if n < 2:
        return 0.0
    return sum(f * (f - 1) for f in freq.values()) / (n * (n - 1))


def _mattr(tokens: list[str], window: int = 100) -> float:
    """Moving-Average Type-Token Ratio."""
    if len(tokens) < window:
        return _ttr(tokens)
    ratios = [len(set(tokens[i : i + window])) / window for i in range(len(tokens) - window + 1)]
    return float(np.mean(ratios))


def _mtld(tokens: list[str], ttr_threshold: float = 0.72) -> float:
    """Measure of Textual Lexical Diversity (McCarthy 2005)."""
    if not tokens:
        return 0.0

    def _one_direction(toks: list[str]) -> float:
        factor_count = 0.0
        seen: set[str] = set()
        count = 0
        for tok in toks:
            seen.add(tok)
            count += 1
            ttr = len(seen) / count
            if ttr <= ttr_threshold:
                factor_count += 1
                seen = set()
                count = 0
        if count > 0:
            # Partial factor: scale by how close to the threshold it got.
            partial = (1 - (len(seen) / count)) / (1 - ttr_threshold) if ttr_threshold < 1 else 0
            factor_count += partial
        if factor_count > 0:
            return len(toks) / factor_count
        # factor_count == 0 means TTR never fell to the threshold — the text is
        # maximally diverse over its whole length. MTLD is the token count by
        # the McCarthy & Jarvis (2010) floor, NOT 0.0 (returning 0 inverts the
        # measure, scoring maximal diversity as minimal).
        return float(len(toks))

    forward = _one_direction(tokens)
    backward = _one_direction(list(reversed(tokens)))
    return (forward + backward) / 2


def _hdd(tokens: list[str], sample_size: int = 42) -> float:
    """Hypergeometric Distribution Diversity (McCarthy & Jarvis 2010).

    For each unique word, sum the contribution of that word to a sample of `sample_size`;
    each contribution is the probability of at least one occurrence in the sample.
    """
    from math import comb

    if len(tokens) < sample_size:
        return 0.0
    n = len(tokens)
    freq = Counter(tokens)
    total = 0.0
    for f in freq.values():
        # P(at least one) = 1 - P(none) = 1 - C(n-f, sample) / C(n, sample)
        p_none = comb(n - f, sample_size) / comb(n, sample_size) if sample_size <= n - f else 0.0
        total += (1 - p_none) / sample_size
    return total


_INDEX_FN: dict[str, Callable[[list[str]], float]] = {
    "ttr": _ttr,
    "mattr": _mattr,
    "mtld": _mtld,
    "hdd": _hdd,
    "yules_k": _yules_k,
    "yules_i": _yules_i,
    "herdans_c": _herdans_c,
    "simpsons_d": _simpsons_d,
}


class LexicalDiversityExtractor(BaseFeatureExtractor):
    feature_type = "lexical_diversity"

    def __init__(self, indices: list[str] | tuple[str, ...] = _DEFAULT_INDICES) -> None:
        self.indices = list(indices)

    def _fit(self, corpus: Corpus) -> None:
        del corpus
        unknown = [i for i in self.indices if i not in _INDEX_FN]
        if unknown:
            raise ValueError(f"LexicalDiversityExtractor: unknown indices {unknown}")

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        X = np.zeros((len(corpus), len(self.indices)), dtype=float)  # noqa: N806
        for row, doc in enumerate(corpus.documents):
            tokens = _tokens(doc.text)
            for col, index in enumerate(self.indices):
                X[row, col] = _INDEX_FN[index](tokens)
        return X, list(self.indices)
