"""Dark-themed shell + 5-step stepper for the Forensic Lab Case pages.

Separate from ``bitig.gui.layout`` so the existing flat Ingest/Study/Run/
Results/Forensic pages keep their light-theme shell unchanged (spec §7
step 4: legacy pages stay reachable). Both shells share Tailwind classes
under NiceGUI and never call any UI primitive at module scope.

Visual tokens from spec §4 — most are surfaced as CSS custom properties on
the body so per-step style snippets can reference them.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from nicegui import ui

from bitig._version import __version__
from bitig.cases import Case

StepKey = Literal["evidence", "method", "run", "findings", "report"]

STEPS: list[tuple[StepKey, str]] = [
    ("evidence", "Evidence"),
    ("method", "Method"),
    ("run", "Run"),
    ("findings", "Findings"),
    ("report", "Report"),
]

# Spec §4
TOKENS = """
:root {
  --bitig-bg: #0d1117;
  --bitig-bg-panel: #161b22;
  --bitig-bg-deep: #010409;
  --bitig-bg-report: #fafaf7;
  --bitig-accent: #C9A34A;
  --bitig-ok: #3fb950;
  --bitig-warn: #d29922;
  --bitig-err: #f85149;
  --bitig-info: #1f6feb;
  --bitig-text: #e6edf3;
  --bitig-text-2: #c9d1d9;
  --bitig-text-muted: #7d8590;
  --bitig-border: #30363d;
  --bitig-font-mono: 'JetBrains Mono', 'SF Mono', ui-monospace, monospace;
  --bitig-font-sans: system-ui, -apple-system, 'Inter', sans-serif;
  --bitig-font-serif: Georgia, 'Times New Roman', serif;
}

.bitig-case-shell {
  background: var(--bitig-bg);
  color: var(--bitig-text);
  font-family: var(--bitig-font-sans);
  min-height: 100vh;
}
.bitig-case-shell .bitig-panel {
  background: var(--bitig-bg-panel);
  border: 1px solid var(--bitig-border);
  border-radius: 4px;
}
.bitig-mono { font-family: var(--bitig-font-mono); }
.bitig-muted { color: var(--bitig-text-muted); }
.bitig-accent { color: var(--bitig-accent); }
.bitig-ok { color: var(--bitig-ok); }
.bitig-warn { color: var(--bitig-warn); }
.bitig-err { color: var(--bitig-err); }

.bitig-step-pill {
  font-family: var(--bitig-font-mono);
  color: var(--bitig-text-muted);
  padding: 4px 0;
  border-bottom: 2px solid transparent;
}
.bitig-step-pill.active {
  color: var(--bitig-accent);
  border-bottom-color: var(--bitig-accent);
}
.bitig-step-pill.done {
  color: var(--bitig-ok);
}

.bitig-evidence-card {
  background: var(--bitig-bg-panel);
  border: 1px solid var(--bitig-border);
  border-left: 3px solid var(--bitig-border);
  border-radius: 3px;
  padding: 8px 12px;
}
.bitig-evidence-card.selected { border-left-color: var(--bitig-accent); }
.bitig-evidence-card.err { border-left-color: var(--bitig-err); }

.bitig-tile {
  background: var(--bitig-bg-panel);
  border: 1px solid var(--bitig-border);
  border-radius: 4px;
  padding: 16px;
  cursor: pointer;
}
.bitig-tile:hover { border-color: var(--bitig-accent); }
.bitig-tile.selected { border-color: var(--bitig-accent); }

.bitig-report-surface {
  background: var(--bitig-bg-report);
  color: #1a1a2e;
  font-family: var(--bitig-font-serif);
}
"""


def _step_status(active: StepKey, case: Case) -> dict[StepKey, str]:
    """Return ``{step: 'done'|'active'|'todo'}`` for the stepper.

    Steps before the active one are 'done' iff the Case has the expected
    artefact in place (any evidence registered → Evidence done; study.yaml
    present → Method done; at least one run → Run done; Findings is done
    when a run exists; Report is done when the Case is signed).
    """
    r = case.record
    out: dict[StepKey, str] = {}
    have_evidence = bool(r.evidence.questioned or r.evidence.known)
    have_study = case.study_yaml_path.is_file()
    have_run = bool(r.runs)
    signed = r.signed

    statuses: dict[StepKey, bool] = {
        "evidence": have_evidence,
        "method": have_evidence and have_study,
        "run": have_run,
        "findings": have_run,
        "report": signed,
    }
    for step, _label in STEPS:
        if step == active:
            out[step] = "active"
        elif statuses[step]:
            out[step] = "done"
        else:
            out[step] = "todo"
    return out


def _step_route(case_id: str, step: StepKey) -> str:
    return f"/case/{case_id}/{step}"


def _render_stepper(case: Case, active: StepKey) -> None:
    statuses = _step_status(active, case)
    with (
        ui.row()
        .classes("w-full items-center gap-6 mb-4 pb-3 border-b")
        .style("border-color: var(--bitig-border);")
    ):
        for i, (key, label) in enumerate(STEPS, start=1):
            status = statuses[key]
            marker = "✓" if status == "done" else "▎" if status == "active" else ""
            classes = "bitig-step-pill " + (
                "active" if status == "active" else "done" if status == "done" else ""
            )
            with (
                ui.row()
                .classes("items-center gap-2 cursor-pointer")
                .on("click", lambda c=case.record.id, s=key: ui.navigate.to(_step_route(c, s)))
            ):
                ui.label(f"{i} · {label}").classes(classes)
                if marker:
                    ui.label(marker).classes(classes + " text-sm")


@contextmanager
def case_shell(case: Case, step: StepKey) -> Iterator[None]:
    """Render the Forensic Lab header + stepper, then yield the page body.

    The Report step (5) uses a light surface — callers handle that inside
    their page body by wrapping their content in a div with the
    ``bitig-report-surface`` class. The shell itself stays dark so the
    toolbar / stepper / step nav all keep the forensic look.
    """
    ui.add_head_html(f"<style>{TOKENS}</style>")
    ui.dark_mode().enable()

    with ui.column().classes("w-full bitig-case-shell"):
        # Top bar
        with (
            ui.row()
            .classes("w-full items-center gap-4 px-6 py-3 border-b")
            .style("border-color: var(--bitig-border); background: var(--bitig-bg-deep);")
        ):
            ui.label("bitig").classes("text-2xl font-bold bitig-accent")
            ui.label("forensic lab").classes("bitig-mono bitig-muted text-sm")
            ui.space()
            mode_color = "bitig-warn" if case.record.mode == "forensic" else "bitig-info"
            ui.label(case.record.mode.upper()).classes(f"bitig-mono text-xs {mode_color}")
            ui.label(f"// {case.record.id}").classes("bitig-mono bitig-muted text-xs")
            ui.label(f"v{__version__}").classes("bitig-mono bitig-muted text-xs")
            ui.button(icon="folder", on_click=lambda: ui.navigate.to("/case")).props(
                "flat round dense color=white"
            ).tooltip("Back to case list")

        with ui.column().classes("w-full max-w-6xl mx-auto px-6 py-6 gap-4"):
            # Case title strip
            with ui.row().classes("w-full items-baseline gap-3"):
                ui.label(case.record.title).classes("text-xl font-semibold")
                ui.label(f"recipe={case.record.recipe}").classes("bitig-mono bitig-muted text-xs")
                if case.record.signed:
                    ui.label("● SIGNED").classes("bitig-mono bitig-ok text-xs")

            _render_stepper(case, step)
            yield


def render_evidence_card(*, title: str, meta: str, provenance: str, state: str = "default") -> None:
    """Reusable evidence-card pattern (spec §4)."""
    klass = "bitig-evidence-card"
    if state == "selected":
        klass += " selected"
    elif state == "err":
        klass += " err"
    with ui.column().classes(f"{klass} w-full"):
        with ui.row().classes("w-full items-center"):
            ui.label(f"• {title}").classes("bitig-mono")
            ui.space()
            ui.label(meta).classes("bitig-mono bitig-muted text-xs")
        ui.label(f"// {provenance}").classes("bitig-mono bitig-muted text-xs")
