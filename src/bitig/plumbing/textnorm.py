"""Unicode-aware lowercasing that keeps Turkish İ from fragmenting tokens."""

import unicodedata

__all__ = ["fold_lower"]


def fold_lower(text: str) -> str:
    """Lowercase ``text`` and drop combining marks that casing introduces.

    Python maps ``'İ'`` (U+0130) to ``'i'`` + U+0307 (combining dot above), so a
    naive ``.lower()`` makes ``'İçin'`` a different token type than ``'için'`` and,
    under a ``[^\\W\\d_]+`` split, fragments ``'İstanbul'`` into ``'i'`` + ``'stanbul'``.
    Normalising to NFC and removing combining marks folds these to the plain form.
    Precomposed letters (ç ş ğ ı ö ü, ä é ñ …) carry no combining marks after NFC
    and pass through unchanged.

    This is deliberately not full Turkish casing: ASCII ``'I'`` still folds to
    ``'i'`` rather than the dotless ``'ı'``, because the tokeniser is
    language-neutral and must not corrupt English ``'I'``.
    """
    folded = unicodedata.normalize("NFC", text.lower())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))
