"""Pure, GUI-free Case run orchestration (audit P1.18).

Extracted from the GUI run page so the run logic — the signed/custody gates,
collision-safe run ids, and the all-succeeded / partial / all-failed
classification — is unit-testable without spinning up NiceGUI.

The runner (:func:`bitig.runner.run_study`) catches every per-method exception,
writes ``error.txt`` into that method's dir, and returns the run dir regardless.
That means "the run completed" is NOT the same as "the analysis succeeded": a
run where every method errored must not unlock Findings/Report or be recorded
as the latest run. :func:`perform_run` makes that distinction explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from bitig.cases import Case
from bitig.runner import run_study

RunStatus = Literal["succeeded", "partial", "failed", "blocked"]


@dataclass
class MethodOutcome:
    method_id: str
    ok: bool
    error: str | None = None


@dataclass
class RunOutcome:
    status: RunStatus
    message: str
    run_id: str | None = None
    methods: list[MethodOutcome] = field(default_factory=list)

    @property
    def unlocks_findings(self) -> bool:
        """A blocked or all-failed run must NOT unlock Findings/Report."""
        return self.status in {"succeeded", "partial"}


def unique_run_id(case: Case, *, now: datetime | None = None) -> str:
    """Collision-safe ISO-8601 UTC run id (spec §2).

    If a dir with the base id already exists — two runs within the same second
    — suffix ``-2``, ``-3``, … so a second run can't silently overwrite the
    first (audit P1.18).
    """
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H-%M-%SZ")
    candidate, n = stamp, 2
    while (case.runs_dir / candidate).exists():
        candidate = f"{stamp}-{n}"
        n += 1
    return candidate


def perform_run(case: Case) -> RunOutcome:
    """Execute the Case's study and classify the outcome. Pure (no GUI).

    Order of guards: signed → chain-of-custody → run. A run is recorded
    (``register_run``) only when at least one method produced a result, so an
    all-failed run never becomes ``latest_run`` and never unlocks Findings.
    """
    if case.record.signed:
        return RunOutcome("blocked", "Case is signed; cannot re-run. Fork it for further work.")

    mismatches = case.verify_custody()
    if mismatches:
        return RunOutcome(
            "blocked",
            f"Chain-of-custody mismatch on {len(mismatches)} file(s); aborting run. "
            "Re-acknowledge on the Evidence step.",
        )

    run_id = unique_run_id(case)
    try:
        run_dir = run_study(case.study_yaml_path, output_dir=case.runs_dir, run_name=run_id)
    except Exception as exc:
        return RunOutcome("failed", f"{type(exc).__name__}: {exc}", run_id=run_id)

    methods: list[MethodOutcome] = []
    for method_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        err = method_dir / "error.txt"
        if err.is_file():
            detail = err.read_text(encoding="utf-8").strip().splitlines()
            methods.append(
                MethodOutcome(method_dir.name, ok=False, error=detail[-1] if detail else "error")
            )
        else:
            methods.append(MethodOutcome(method_dir.name, ok=True))

    n_ok = sum(m.ok for m in methods)
    if not methods or n_ok == 0:
        return RunOutcome(
            "failed",
            "Every method failed — see error.txt in the run dir. The run was not recorded.",
            run_id=run_id,
            methods=methods,
        )

    # Only record a run that produced at least one result.
    case.register_run(run_id)
    if n_ok < len(methods):
        return RunOutcome(
            "partial",
            f"{n_ok}/{len(methods)} method(s) succeeded; the rest wrote error.txt.",
            run_id=run_id,
            methods=methods,
        )
    return RunOutcome(
        "succeeded",
        f"All {len(methods)} method(s) succeeded.",
        run_id=run_id,
        methods=methods,
    )


__all__ = ["MethodOutcome", "RunOutcome", "RunStatus", "perform_run", "unique_run_id"]
