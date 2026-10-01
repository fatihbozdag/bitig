"""French readability formulas.

Kandel, L., & Moles, A. (1958). Application de l'indice de Flesch à la langue française.
Cahiers d'études de radio-télévision, 19, 253-274.
Björnsson, C. H. (1968). Läsbarhet. Stockholm: Liber.

Syllables are counted as spoken vowel nuclei (``bitig.languages._syllables``); hyphenation
dictionaries undercount them.
"""

from __future__ import annotations

import re

from bitig.languages._syllables import count_syllables_fr

_WORD_RE = re.compile(r"[^\W\d_]+", flags=re.UNICODE)
_SENTENCE_RE = re.compile(r"[.!?…]+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _sentence_count(text: str) -> int:
    parts = [p for p in _SENTENCE_RE.split(text) if p.strip()]
    return max(1, len(parts))


def kandel_moles(text: str) -> float:
    """Kandel-Moles (1958): 207 - 1.015 * (word/sent) - 73.6 * (syll/word)."""
    words = _words(text)
    if not words:
        return 0.0
    n_words = len(words)
    n_syllables = sum(count_syllables_fr(w) for w in words)
    n_sentences = _sentence_count(text)
    return 207.0 - 1.015 * (n_words / n_sentences) - 73.6 * (n_syllables / n_words)


def lix(text: str) -> float:
    """LIX (Björnsson 1968): (word/sent) + 100 * (long/word). long = >6 letters."""
    words = _words(text)
    if not words:
        return 0.0
    n_words = len(words)
    n_sentences = _sentence_count(text)
    n_long = sum(1 for w in words if len(w) > 6)
    return (n_words / n_sentences) + 100.0 * (n_long / n_words)
