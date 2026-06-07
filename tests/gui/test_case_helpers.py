"""Tests for the pure helpers in ``bitig.gui.pages.case._helpers``.

Stays clear of NiceGUI so the helpers can be exercised without spinning up
the desktop app.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("nicegui")  # _helpers imports gui.state which imports cases

from pathlib import Path

from bitig.cases import Case
from bitig.gui.pages.case._helpers import (
    LR_LADDER,
    headline_scalars,
    latest_result_path,
    load_latest_result,
    lr_verbal_rung,
    resolve_case,
    short_hash,
)
from bitig.gui.state import get_state, reset_state
from bitig.result import Result

# ---------------------------------------------------------------------------
# short_hash
# ---------------------------------------------------------------------------


def test_short_hash_trims_and_appends_ellipsis() -> None:
    assert short_hash("abcdef0123456789", n=6) == "abcdef…"


def test_short_hash_empty_string_returns_em_dash() -> None:
    assert short_hash("") == "—"


# ---------------------------------------------------------------------------
# resolve_case
# ---------------------------------------------------------------------------


def test_resolve_case_returns_loaded_case(tmp_path: Path) -> None:
    reset_state()
    cases_dir = tmp_path / "cases"
    Case.create(cases_dir, id="hit", title="t", examiner="x", recipe="exploration")
    get_state().cases_dir = cases_dir

    case = resolve_case("hit")
    assert case is not None
    assert case.record.id == "hit"


def test_resolve_case_returns_none_for_unknown(tmp_path: Path) -> None:
    reset_state()
    get_state().cases_dir = tmp_path / "empty"
    assert resolve_case("ghost") is None


def test_resolve_case_accepts_explicit_dir(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    Case.create(cases_dir, id="explicit", title="t", examiner="x", recipe="exploration")
    reset_state()  # state.cases_dir stays at default

    case = resolve_case("explicit", cases_dir=cases_dir)
    assert case is not None


# ---------------------------------------------------------------------------
# latest_result_path / load_latest_result
# ---------------------------------------------------------------------------


def test_latest_result_path_finds_first_method_dir(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    case = Case.create(cases_dir, id="r", title="t", examiner="x", recipe="exploration")

    run_id = "2026-05-17T10-00-00Z"
    method_dir = case.runs_dir / run_id / "alpha"
    method_dir.mkdir(parents=True)
    Result(method_name="alpha", values={"accuracy": 0.9}).to_json(method_dir / "result.json")
    case.register_run(run_id)

    found = latest_result_path(case)
    assert found is not None
    assert found.name == "result.json"
    assert "alpha" in str(found)


def test_latest_result_path_none_without_runs(tmp_path: Path) -> None:
    case = Case.create(tmp_path / "cases", id="r", title="t", examiner="x", recipe="exploration")
    assert latest_result_path(case) is None


def test_load_latest_result_returns_result(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    case = Case.create(cases_dir, id="r", title="t", examiner="x", recipe="exploration")
    run_id = "2026-05-17T10-00-00Z"
    method_dir = case.runs_dir / run_id / "alpha"
    method_dir.mkdir(parents=True)
    Result(method_name="alpha", values={"accuracy": 0.9}).to_json(method_dir / "result.json")
    case.register_run(run_id)

    loaded = load_latest_result(case)
    assert loaded is not None
    assert loaded.method_name == "alpha"
    assert loaded.values["accuracy"] == 0.9


# ---------------------------------------------------------------------------
# headline_scalars
# ---------------------------------------------------------------------------


def test_headline_scalars_forensic_surfaces_lr_first(tmp_path: Path) -> None:
    case = Case.create(tmp_path / "cases", id="fc", title="t", examiner="x", recipe="imposters_lr")
    result = Result(
        method_name="verify",
        values={"lr": 250.0, "auc": 0.91, "c_at_1": 0.84, "cllr": 0.22},
    )
    scalars = headline_scalars(case, result)
    labels = [label for label, _ in scalars]
    assert labels[0] == "LR"
    assert "AUC" in labels
    assert "c@1" in labels
    assert "C_llr" in labels


def test_headline_scalars_no_result_returns_placeholder(tmp_path: Path) -> None:
    case = Case.create(tmp_path / "cases", id="np", title="t", examiner="x", recipe="exploration")
    assert headline_scalars(case, None) == [("status", "no run yet")]


def test_headline_scalars_pca_surfaces_variance(tmp_path: Path) -> None:
    case = Case.create(tmp_path / "cases", id="pc", title="t", examiner="x", recipe="exploration")
    result = Result(
        method_name="pca",
        values={"explained_variance_ratio": np.array([0.6, 0.25, 0.1])},
    )
    scalars = headline_scalars(case, result)
    labels = [label for label, _ in scalars]
    assert "PC1 var" in labels
    assert "PC2 var" in labels
    assert "cum." in labels


# ---------------------------------------------------------------------------
# lr_verbal_rung
# ---------------------------------------------------------------------------


def test_lr_verbal_rung_one_is_no_support() -> None:
    assert lr_verbal_rung(1.0) == "no support"


def test_lr_verbal_rung_thresholds() -> None:
    # Two-sided ENFSI/Nordgaard bands (re-exported from bitig.forensic.verbal_scale).
    assert lr_verbal_rung(5) == "weak support"
    assert lr_verbal_rung(50) == "moderate support"
    assert lr_verbal_rung(500) == "moderately strong support"
    assert lr_verbal_rung(5000) == "strong support"
    assert lr_verbal_rung(50000) == "very strong support"
    assert lr_verbal_rung(2e6) == "extremely strong support"
    # Symmetric: a defence-favouring LR carries the same strength.
    assert lr_verbal_rung(0.02) == lr_verbal_rung(50)


def test_lr_ladder_is_continuous_and_starts_at_one() -> None:
    # Strength bands on the order of magnitude (max(LR, 1/LR)); start at 1.
    assert LR_LADDER[0][1] == 1.0
    prev_hi = 1.0
    for _label, lo, hi in LR_LADDER:
        assert lo == prev_hi
        prev_hi = hi
