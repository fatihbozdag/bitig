"""Tests for the two-sided LR verbal scale (audit P1.11 + judgment #1).

Nordgaard 2012 / ENFSI 2015: strength is symmetric in LR vs 1/LR; direction
says which proposition is supported. Always classify from the raw float.
"""

from __future__ import annotations

import pytest

from bitig.forensic.verbal_scale import (
    LR_LADDER,
    ladder_rows,
    lr_direction,
    lr_from_values,
    lr_verbal_rung,
    lr_verbal_statement,
)

# ---------------------------------------------------------------------------
# Strength rung — symmetric, order-of-magnitude, from the raw float (P1.11)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lr", "rung"),
    [
        (1.0, "no support"),
        (5.0, "weak support"),
        (9.999, "weak support"),  # raw float, not the rounded '10'
        (50.0, "moderate support"),
        (500.0, "moderately strong support"),  # the rung the old ladder lacked
        (5_000.0, "strong support"),
        (50_000.0, "very strong support"),
        (500_000.0, "very strong support"),
        (2_000_000.0, "extremely strong support"),  # >10^6, not capped at 10^4
        (1e9, "extremely strong support"),
    ],
)
def test_rung_by_order_of_magnitude(lr: float, rung: str) -> None:
    assert lr_verbal_rung(lr) == rung


@pytest.mark.parametrize("lr", [50.0, 500.0, 9.999, 3_141.0, 2_000_000.0])
def test_rung_is_symmetric_in_lr_and_reciprocal(lr: float) -> None:
    """An LR and its reciprocal carry equal strength (opposite direction)."""
    assert lr_verbal_rung(lr) == lr_verbal_rung(1.0 / lr)


def test_rung_indeterminate_for_invalid_lr() -> None:
    assert lr_verbal_rung(None) == "indeterminate"
    assert lr_verbal_rung(float("nan")) == "indeterminate"
    assert lr_verbal_rung(0.0) == "indeterminate"
    assert lr_verbal_rung(-3.0) == "indeterminate"


# ---------------------------------------------------------------------------
# Direction — the two-sided part (the old scale hid LR<1 as 'no support')
# ---------------------------------------------------------------------------


def test_direction_is_two_sided() -> None:
    assert lr_direction(50.0) == "prosecution"
    assert lr_direction(0.02) == "defence"  # exculpatory — was silently 'no support'
    assert lr_direction(1.0) == "inconclusive"
    assert lr_direction(float("nan")) == "indeterminate"


def test_statement_names_the_supported_proposition() -> None:
    assert (
        lr_verbal_statement(50.0)
        == "moderate support for the prosecution proposition (same author, Hp)"
    )
    assert (
        lr_verbal_statement(0.02)
        == "moderate support for the defence proposition (different author, Hd)"
    )
    assert lr_verbal_statement(1.0) == "no support for either proposition (LR = 1)"
    assert lr_verbal_statement(None) == "indeterminate"


# ---------------------------------------------------------------------------
# Ladder display
# ---------------------------------------------------------------------------


def test_ladder_starts_at_weak_and_reaches_extremely() -> None:
    labels = [row[0] for row in ladder_rows()]
    assert labels[0] == "weak support"
    assert "moderately strong support" in labels
    assert labels[-1] == "extremely strong support"


def test_ladder_is_continuous_from_one() -> None:
    assert LR_LADDER[0][1] == 1.0
    prev_hi = 1.0
    for _label, lo, hi in LR_LADDER:
        assert lo == prev_hi
        prev_hi = hi


# ---------------------------------------------------------------------------
# lr_from_values — real LR vs GI win-fraction (P1.10), unchanged behaviour
# ---------------------------------------------------------------------------


def test_lr_from_values_prefers_lr() -> None:
    assert lr_from_values({"lr": 250.0}) == 250.0


def test_lr_from_values_derives_from_log_lr() -> None:
    assert lr_from_values({"log_lr": 2.0}) == pytest.approx(100.0)


def test_lr_from_values_returns_none_for_gi_winfraction() -> None:
    assert lr_from_values({"candidate": "Doe", "scores": {"Doe": 0.83}}) is None


def test_lr_from_values_ignores_non_numeric_nan_and_nonpositive() -> None:
    assert lr_from_values({"lr": "not a number"}) is None
    assert lr_from_values({"lr": float("nan")}) is None
    assert lr_from_values({"lr": 0.0}) is None  # not a valid LR
