"""Tests for the pure Case run orchestrator (audit P1.18).

run_study is mocked to write method dirs with/without error.txt so the
all-succeeded / partial / all-failed classification + recording rules are
exercised without a real corpus run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bitig.case_run import perform_run, unique_run_id
from bitig.cases import Case
from bitig.result import Result


def _case(tmp_path: Path, recipe: str = "exploration") -> Case:
    return Case.create(tmp_path / "cases", id="c", title="t", examiner="x", recipe=recipe)


def _fake_run_study(method_specs: list[tuple[str, bool]]):
    """Return a run_study stand-in that writes the given method dirs.

    Each (method_id, ok): ok=True writes result.json, ok=False writes error.txt.
    """

    def fake(config_path, *, output_dir, run_name):
        run_dir = Path(output_dir) / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        for method_id, ok in method_specs:
            md = run_dir / method_id
            md.mkdir()
            if ok:
                Result(method_name=method_id, values={"x": 1}).to_json(md / "result.json")
            else:
                (md / "error.txt").write_text("BoomError: kaput", encoding="utf-8")
        return run_dir

    return fake


def test_perform_run_succeeded_registers_and_unlocks(tmp_path, monkeypatch) -> None:
    case = _case(tmp_path)
    monkeypatch.setattr("bitig.case_run.run_study", _fake_run_study([("pca", True)]))
    outcome = perform_run(case)
    assert outcome.status == "succeeded"
    assert outcome.unlocks_findings
    assert case.record.runs == [outcome.run_id]
    assert case.record.latest_run == outcome.run_id


def test_perform_run_partial_unlocks_and_records(tmp_path, monkeypatch) -> None:
    case = _case(tmp_path)
    monkeypatch.setattr(
        "bitig.case_run.run_study", _fake_run_study([("pca", True), ("hier", False)])
    )
    outcome = perform_run(case)
    assert outcome.status == "partial"
    assert outcome.unlocks_findings
    assert case.record.runs == [outcome.run_id]
    assert len(outcome.methods) == 2
    assert sum(m.ok for m in outcome.methods) == 1  # exactly one succeeded


def test_perform_run_all_failed_is_not_recorded(tmp_path, monkeypatch) -> None:
    """An all-failed run must NOT unlock Findings or become the latest run."""
    case = _case(tmp_path)
    monkeypatch.setattr(
        "bitig.case_run.run_study", _fake_run_study([("pca", False), ("hier", False)])
    )
    outcome = perform_run(case)
    assert outcome.status == "failed"
    assert not outcome.unlocks_findings
    assert case.record.runs == []  # not registered
    assert case.record.latest_run is None


def test_perform_run_blocked_when_signed(tmp_path, monkeypatch) -> None:
    case = _case(tmp_path)
    case.mark_signed()  # renders + freezes its own report
    called = {"ran": False}
    monkeypatch.setattr(
        "bitig.case_run.run_study",
        lambda *a, **k: called.__setitem__("ran", True),
    )
    outcome = perform_run(case)
    assert outcome.status == "blocked"
    assert not outcome.unlocks_findings
    assert called["ran"] is False  # run_study never invoked


def test_perform_run_blocked_on_custody_mismatch(tmp_path, monkeypatch) -> None:
    case = _case(tmp_path, recipe="imposters_lr")
    src = tmp_path / "ev.txt"
    src.write_text("original evidence", encoding="utf-8")
    entry = case.add_evidence(src, role="known")
    (case.root / entry.path).write_text("tampered", encoding="utf-8")  # break custody

    monkeypatch.setattr(
        "bitig.case_run.run_study",
        lambda *a, **k: pytest.fail("run_study must not be called on a custody mismatch"),
    )
    outcome = perform_run(case)
    assert outcome.status == "blocked"
    assert "custody" in outcome.message.lower()


def test_unique_run_id_avoids_same_second_collision(tmp_path) -> None:
    case = _case(tmp_path)
    fixed = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    rid1 = unique_run_id(case, now=fixed)
    (case.runs_dir / rid1).mkdir(parents=True)
    rid2 = unique_run_id(case, now=fixed)
    assert rid1 != rid2
    assert rid2 == f"{rid1}-2"
