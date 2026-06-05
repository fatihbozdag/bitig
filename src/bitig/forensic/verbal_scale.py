"""LR verbal-scale ladder — the single source of truth (audit P1.11 + ladder dup).

Before this module the ENFSI verbal ladder was copy-pasted in four places
(the GUI Findings helper, the GUI report preview, the report-context builder,
and the forensic HTML template) with divergent boundaries, and the verbal rung
was classified from a *display-rounded* LR string — so e.g. ``LR=0.9999``
rounded to ``"1"`` and was reported as "weak support" when the truth is "no
support", reversing the direction of the evidence. Everything now routes
through :func:`lr_verbal_rung`, which classifies the **raw float**.

DEFERRED — forensic-domain pass (audit judgment #1): the bands below are the
raw-LR five-rung scale (Marquis et al., ENFSI 2016). Whether the canonical
scale should instead be the log10 six-band scale (Nordgaard 2012 / ENFSI 2015),
and how to express two-sided (defence-favouring, ``LR < 1``) support, is a
standards decision for the maintainer. This module preserves the existing
raw-LR semantics but in ONE place, so the report HTML, the GUI preview and the
Findings scalars can no longer disagree.
"""

from __future__ import annotations

import math
from typing import Any

# (label, lower-inclusive, upper-exclusive) on the raw LR.
LR_LADDER: list[tuple[str, float, float]] = [
    ("no support", 0.0, 1.0),
    ("weak support", 1.0, 10.0),
    ("moderate support", 10.0, 100.0),
    ("strong support", 100.0, 1000.0),
    ("very strong support", 1000.0, 10000.0),
    ("extremely strong support", 10000.0, math.inf),
]


def lr_verbal_rung(lr: float | None) -> str:
    """Map a **raw** LR float to its verbal rung.

    Always classify from the float, never from a display-rounded string —
    rounding can push a value across a category boundary (audit P1.11).
    ``None`` / NaN yield ``"indeterminate"``; ``LR <= 0`` yields ``"no
    support"`` (and ``LR < 1`` is defence-favouring under the deferred
    symmetry decision — see module docstring).
    """
    if lr is None:
        return "indeterminate"
    try:
        x = float(lr)
    except (TypeError, ValueError):
        return "indeterminate"
    if math.isnan(x):
        return "indeterminate"
    if x <= 0:
        return "no support"
    for label, lo, hi in LR_LADDER:
        if lo <= x < hi:
            return label
    return "extremely strong support"


def _fmt_bound(x: float) -> str:
    return "∞" if math.isinf(x) else f"{int(x)}"


def ladder_rows() -> list[tuple[str, str, str]]:
    """Display rows ``(label, lo, hi)`` for the GUI/template ladder — one source.

    Includes the ``"no support"`` (LR < 1) rung so a defence-favouring LR
    highlights a row instead of rendering a blank ladder (audit P3).
    """
    return [(label, _fmt_bound(lo), _fmt_bound(hi)) for label, lo, hi in LR_LADDER]


def lr_from_values(values: dict[str, Any]) -> float | None:
    """Extract a real numeric LR from a ``Result.values``, or ``None``.

    Prefers ``lr``; otherwise derives it from ``log_lr`` (``10**log_lr``).
    Returns ``None`` when no calibrated LR is present — e.g. a General
    Impostors win-fraction — so callers never present a non-LR as an LR
    (audit P1.10). NaN is treated as absent.
    """
    if "lr" in values and _is_number(values["lr"]):
        return float(values["lr"])
    if "log_lr" in values and _is_number(values["log_lr"]):
        return float(10.0 ** float(values["log_lr"]))
    return None


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and not math.isnan(float(x))


__all__ = [
    "LR_LADDER",
    "ladder_rows",
    "lr_from_values",
    "lr_verbal_rung",
]
