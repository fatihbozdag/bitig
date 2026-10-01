"""Rule-based syllable counters for German and French (vowel-nucleus counting).

Hyphenation dictionaries (pyphen) encode permissible line breaks, not syllables:
they forbid single-letter syllables at word edges, so "Abend", "Oma", "ami" and
"école" all counted as one syllable (audit 2026-09-26 P2). These counters count
vowel nuclei instead, matching the longest multi-letter vowel combination first,
the same approach as the Spanish and Turkish modules. They are approximations;
``tests/languages/test_syllables_gold.py`` records their accuracy on gold lists.
"""

from __future__ import annotations

import re

_DE_VOWELS = "aeiouäöüy"
# One nucleus each; longest first.
_DE_NUCLEI = ("äu", "ei", "ai", "au", "eu", "ie", "ay", "ey", "aa", "ee", "oo")

_FR_VOWELS = "aeiouyàâäéèêëîïôöùûüœæ"
_FR_NUCLEI = (
    "oeu", "œu", "eau", "ieu",
    "au", "ai", "ei", "ou", "oi", "eu", "œ", "ui", "ie", "io", "oû", "où",
)  # fmt: skip


def _count_nuclei(word: str, vowels: str, nuclei: tuple[str, ...]) -> int:
    count = 0
    i = 0
    n = len(word)
    while i < n:
        if word[i] not in vowels:
            i += 1
            continue
        for unit in nuclei:
            if word.startswith(unit, i):
                i += len(unit)
                break
        else:
            i += 1
        count += 1
    return count


def count_syllables_de(word: str) -> int:
    """German syllables: vowel nuclei, diphthongs and doubled vowels counting once."""
    w = word.lower()
    return _count_nuclei(w, _DE_VOWELS, _DE_NUCLEI) if w else 0


_RSQUO = chr(0x2019)  # typographic apostrophe
_FR_QU = re.compile(r"qu")
_FR_GU = re.compile(r"gu(?=[eéèêiîy])")


def count_syllables_fr(word: str) -> int:
    """French spoken syllables: vowel nuclei, with silent final -e / -es dropped.

    The *u* of *qu*, and of *gu* before e/i, spells a consonant. A final *e* or
    *es* is mute unless it is the word's only vowel (le, les). Known limits: verb
    endings in *-ent* (parlent) are counted, *ie* + vowel splits (client) are not.
    """
    w = word.lower().replace(_RSQUO, "'")
    if not w:
        return 0
    w = _FR_GU.sub("g", _FR_QU.sub("q", w))
    for ending in ("es", "e"):
        if w.endswith(ending):
            stem = w[: -len(ending)]
            if any(c in _FR_VOWELS for c in stem):
                w = stem
            break
    return max(1, _count_nuclei(w, _FR_VOWELS, _FR_NUCLEI))
