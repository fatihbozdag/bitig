"""LR verbal-scale ladder — the single source of truth (audit P1.11 + judgment #1).

The verbal scale is **two-sided and order-of-magnitude based**, following
Nordgaard et al. (2012), as adopted in the ENFSI (2015) *Guideline for
Evaluative Reporting* and discussed by Marquis et al. (2016):

* The *strength* of support is a function of the order of magnitude of the LR,
  symmetric in the LR and its reciprocal — ``LR = 50`` and ``LR = 1/50`` give
  equally strong support, just for the competing propositions.
* The *direction* says which proposition the evidence supports: ``LR > 1``
  supports the prosecution / same-author proposition (Hp); ``LR < 1`` supports
  the defence / different-author proposition (Hd); ``LR = 1`` supports neither.

This replaces the earlier one-sided raw-LR ladder, which collapsed every
``LR < 1`` to "no support" and so **hid exculpatory (defence-favouring)
evidence**, and which capped "extremely strong" at 10^4 (the standard puts it
at >10^6). The bands below are the widely-used powers-of-ten equivalents; a lab
that has standardised on different verbal equivalents should edit this one
table — every consumer (report HTML, GUI preview, Findings) reads it.

The rung is always classified from the **raw LR float**, never a display-
rounded string (audit P1.11): rounding can push a value across a boundary.
"""

from __future__ import annotations

import math
from typing import Any

# Strength bands keyed on the LR's order of magnitude m = max(LR, 1/LR) >= 1.
# (label, lower-inclusive, upper-exclusive). Nordgaard 2012 / ENFSI 2015.
LR_LADDER: list[tuple[str, float, float]] = [
    ("weak support", 1.0, 10.0),
    ("moderate support", 10.0, 100.0),
    ("moderately strong support", 100.0, 1000.0),
    ("strong support", 1000.0, 10000.0),
    ("very strong support", 10000.0, 1_000_000.0),
    ("extremely strong support", 1_000_000.0, math.inf),
]

# Direction → the proposition phrase used in a verbal statement.
_PROPOSITION = {
    "prosecution": "the prosecution proposition (same author, Hp)",
    "defence": "the defence proposition (different author, Hd)",
}


def _as_lr(lr: float | None) -> float | None:
    """Coerce to a valid positive LR float, or None (invalid / NaN / <= 0)."""
    if lr is None:
        return None
    try:
        x = float(lr)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or x <= 0:
        return None
    return x


def lr_verbal_rung(lr: float | None) -> str:
    """Strength rung for a **raw** LR float, symmetric in LR vs 1/LR.

    ``LR == 1`` → ``"no support"``; an invalid / NaN / non-positive LR →
    ``"indeterminate"``. The same rung is returned for an LR and its reciprocal
    (the *direction* is given separately by :func:`lr_direction`).
    """
    x = _as_lr(lr)
    if x is None:
        return "indeterminate"
    if x == 1.0:
        return "no support"
    magnitude = x if x > 1.0 else 1.0 / x
    for label, lo, hi in LR_LADDER:
        if lo <= magnitude < hi:
            return label
    return "extremely strong support"


def lr_direction(lr: float | None) -> str:
    """Which proposition the LR supports: ``prosecution`` (LR>1), ``defence``
    (LR<1), ``inconclusive`` (LR==1), or ``indeterminate`` (invalid)."""
    x = _as_lr(lr)
    if x is None:
        return "indeterminate"
    if x == 1.0:
        return "inconclusive"
    return "prosecution" if x > 1.0 else "defence"


def lr_verbal_statement(lr: float | None) -> str:
    """Full two-sided verbal statement, e.g. 'moderate support for the defence
    proposition (different author, Hd)'."""
    direction = lr_direction(lr)
    if direction == "indeterminate":
        return "indeterminate"
    if direction == "inconclusive":
        return "no support for either proposition (LR = 1)"
    return f"{lr_verbal_rung(lr)} for {_PROPOSITION[direction]}"


def _fmt_bound(x: float) -> str:
    return "∞" if math.isinf(x) else f"{int(x)}"


def ladder_rows() -> list[tuple[str, str, str]]:
    """Display rows ``(label, lo, hi)`` of the strength ladder for the GUI /
    template (one source). The bounds are on the LR's order of magnitude
    (max(LR, 1/LR)); the direction is shown separately."""
    return [(label, _fmt_bound(lo), _fmt_bound(hi)) for label, lo, hi in LR_LADDER]


def lr_from_values(values: dict[str, Any]) -> float | None:
    """Extract a real numeric LR from a ``Result.values``, or ``None``.

    Prefers ``lr``; otherwise derives it from ``log_lr`` (``10**log_lr``).
    Returns ``None`` when no calibrated LR is present — e.g. a General
    Impostors win-fraction — so callers never present a non-LR as an LR
    (audit P1.10). NaN / non-positive is treated as absent.
    """
    if "lr" in values and _is_number(values["lr"]):
        return _as_lr(values["lr"])
    if "log_lr" in values and _is_number(values["log_lr"]):
        return _as_lr(10.0 ** float(values["log_lr"]))
    return None


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and not math.isnan(float(x))


__all__ = [
    "LR_LADDER",
    "ladder_rows",
    "lr_direction",
    "lr_from_values",
    "lr_verbal_rung",
    "lr_verbal_statement",
]
