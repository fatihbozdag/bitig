"""Shared helper: bring a test Case into a signable state.

``Case.mark_signed`` refuses a case without registered evidence, with a
custody mismatch, a modified study.yaml, or no run computed on the current
state (audit 2026-09-26 N-P1.2 / N-P1.7). Tests that exercise signing itself
use this to satisfy those preconditions with a minimal fake run.
"""

from __future__ import annotations

from bitig.cases import Case
from bitig.result import Result

_RUN_ID = "2026-01-01T00-00-00Z"


def make_signable(case: Case) -> Case:
    if not case.record.evidence.all_files():
        src = case.root.parent / f"_evidence_{case.record.id}.txt"
        src.write_text("alpha beta gamma delta", encoding="utf-8")
        case.add_evidence(src, role="known", author="A")
    if not case.study_yaml_intact():
        case.regenerate_study_yaml()
        case.save()
    run_id = case.record.latest_run
    if run_id is None or not (case.runs_dir / run_id).is_dir():
        run_id = _RUN_ID
        method_dir = case.runs_dir / run_id / "m"
        method_dir.mkdir(parents=True, exist_ok=True)
        Result(method_name="m", values={"x": 1}).to_json(method_dir / "result.json")
    case.register_run(run_id, case_state_hash=case._case_state_hash())
    return case
