"""Tests for the shared LR verbal-scale ladder (audit P1.11, P1.10)."""

from __future__ import annotations

import math

import pytest

from bitig.forensic.verbal_scale import (
    LR_LADDER,
    ladder_rows,
    lr_from_values,
    lr_verbal_rung,
)

# ---------------------------------------------------------------------------
# lr_verbal_rung — classify from the RAW float (the P1.11 fix)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lr", "rung"),
    [
        (0.0, "no support"),
        (0.5, "no support"),
        (0.9999, "no support"),  # was misreported "weak support" from the rounded string
        (1.0, "weak support"),
        (5.0, "weak support"),
        (9.999, "weak support"),  # was misreported "moderate"
        (10.0, "moderate support"),
        (99.95, "moderate support"),  # was misreported "strong"
        (100.0, "strong support"),
        (999.6, "strong support"),  # was misreported "very strong"
        (1000.0, "very strong support"),
        (9995.0, "very strong support"),  # was misreported "extremely"
        (10000.0, "extremely strong support"),
        (1e9, "extremely strong support"),
    ],
)
def test_lr_verbal_rung_classifies_raw_float_at_boundaries(lr: float, rung: str) -> None:
    assert lr_verbal_rung(lr) == rung


def test_lr_verbal_rung_nan_and_none_are_indeterminate() -> None:
    assert lr_verbal_rung(float("nan")) == "indeterminate"
    assert lr_verbal_rung(None) == "indeterminate"


def test_ladder_is_continuous_and_covers_zero_to_inf() -> None:
    assert LR_LADDER[0][1] == 0.0
    assert math.isinf(LR_LADDER[-1][2])
    prev_hi = 0.0
    for _label, lo, hi in LR_LADDER:
        assert lo == prev_hi
        prev_hi = hi


def test_ladder_rows_include_no_support_so_defence_lr_highlights() -> None:
    labels = [row[0] for row in ladder_rows()]
    assert labels[0] == "no support"  # LR<1 highlights a row, not a blank ladder (P3)
    assert "extremely strong support" in labels


# ---------------------------------------------------------------------------
# lr_from_values — real LR vs GI win-fraction (the P1.10 fix)
# ---------------------------------------------------------------------------


def test_lr_from_values_prefers_lr() -> None:
    assert lr_from_values({"lr": 250.0}) == 250.0


def test_lr_from_values_derives_from_log_lr() -> None:
    assert lr_from_values({"log_lr": 2.0}) == pytest.approx(100.0)


def test_lr_from_values_returns_none_for_gi_winfraction() -> None:
    # A General Impostors result has no lr/log_lr — only candidate/scores.
    assert lr_from_values({"candidate": "Doe", "scores": {"Doe": 0.83}}) is None


def test_lr_from_values_ignores_non_numeric_and_nan() -> None:
    assert lr_from_values({"lr": "not a number"}) is None
    assert lr_from_values({"lr": float("nan")}) is None
