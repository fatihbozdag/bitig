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
from typing import Any, Literal

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

    Order of guards: signed → chain-of-custody → study.yaml integrity →
    verify inputs → run. The corpus is built from the registered evidence
    only (:meth:`Case.build_corpus`), never by globbing ``evidence/``. A run
    is recorded (``register_run``) only when at least one method produced a
    result, so an all-failed run never becomes ``latest_run`` and never
    unlocks Findings.
    """
    if case.record.signed:
        return RunOutcome("blocked", "Case is signed; cannot re-run. Fork it for further work.")

    mismatches = case.verify_custody()
    if mismatches:
        return RunOutcome(
            "blocked",
            f"Chain-of-custody mismatch on {len(mismatches)} file(s); aborting run. "
            "Re-acknowledge legitimately changed files on the Evidence step (or "
            "`bitig case reacknowledge`), or fork the case if a file is missing or "
            "should not have changed.",
        )

    # A study.yaml edited outside bitig must not be run (audit 2026-09-26 N-P1.1).
    if case.study_yaml_path.is_file() and not case.study_yaml_intact():
        return RunOutcome(
            "blocked",
            "study.yaml was modified outside bitig (hash differs from the one recorded "
            "in case.json); aborting run. Re-apply the method settings to regenerate it.",
        )

    try:
        study = case.resolved_study()
    except Exception as exc:
        return RunOutcome("blocked", f"Invalid study configuration: {exc}")
    for method in study.methods:
        if method.kind != "verify":
            continue
        problem = _verify_inputs_problem(case, method.params, method.group_by)
        if problem:
            return RunOutcome("blocked", problem)

    run_id = unique_run_id(case)
    try:
        # Rewrite study.yaml from the recipe (translating pre-0.3.2 parameter
        # names) so the file that is run and hashed is the resolved study.
        case.regenerate_study_yaml()
        case.save()
        corpus = case.build_corpus(language=study.preprocess.language)
        # The state this run is computed on; signing refuses it once the case
        # changes (audit 2026-09-26 N-P1.2).
        state_hash = case._case_state_hash()
        run_dir = run_study(
            case.study_yaml_path, output_dir=case.runs_dir, run_name=run_id, corpus=corpus
        )
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
    case.register_run(run_id, case_state_hash=state_hash)
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


def _verify_inputs_problem(case: Case, params: dict[str, Any], group_by: str | None) -> str | None:
    """Why a verify method cannot run on this Case's evidence, or None if it can."""
    evidence = case.record.evidence
    if not evidence.questioned:
        return "Authorship verification needs at least one questioned document."
    if (group_by or "author") != "author":
        return f"Case verification groups known documents by author, not {group_by!r}."
    if any(e.author is None for e in evidence.known):
        return "Every known document needs an author label for verification."
    candidate = str(params.get("candidate") or "").strip()
    if not candidate:
        return "Set the 'Candidate author' parameter (the author label of the suspect's texts)."
    authors = sorted({str(e.author) for e in evidence.known})
    if candidate not in authors:
        return f"Candidate {candidate!r} does not match any known-document author {authors}."
    if len(authors) < 2:
        return (
            "Verification needs known documents from the candidate AND at least one other "
            "author (the impostors)."
        )
    return None


__all__ = ["MethodOutcome", "RunOutcome", "RunStatus", "perform_run", "unique_run_id"]
