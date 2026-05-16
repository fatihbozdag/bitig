"""``/case/{case_id}/findings`` — Step 4 of the Forensic Lab flow (spec §5.4)."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from bitig.cases import Case
from bitig.gui.case_layout import case_shell
from bitig.gui.pages.case._helpers import (
    headline_scalars,
    load_latest_result,
    resolve_case,
    short_hash,
)
from bitig.gui.state import get_state
from bitig.result import Result


@ui.page("/case/{case_id}/findings")
def case_findings_page(case_id: str) -> None:
    case = resolve_case(case_id)
    if case is None:
        ui.label(f"Case not found: {case_id}").classes("p-6")
        return
    get_state().current_case_id = case_id

    with case_shell(case, "findings"):
        _render_body(case)


def _render_body(case: Case) -> None:
    result = load_latest_result(case)

    # Headline scalar row (spec §5.4).
    scalars = headline_scalars(case, result)
    with ui.row().classes("w-full gap-3"):
        for i, (label, value) in enumerate(scalars):
            first = i == 0 and case.record.mode == "forensic"
            klass = "bitig-panel p-4 flex-1 min-w-0"
            style = "border-left: 3px solid var(--bitig-accent);" if first else ""
            with ui.column().classes(klass).style(style):
                ui.label(label).classes("bitig-mono bitig-muted text-xs")
                cls = "text-2xl bitig-accent" if first else "text-2xl"
                ui.label(value).classes(cls)

    # Figure gallery + run summary side panel.
    with ui.row().classes("w-full gap-4 mt-4"):
        with ui.column().classes("flex-1 gap-2"):
            ui.label("Figures").classes("font-semibold")
            _figure_gallery(case)
        with ui.column().classes("w-80 bitig-panel p-4 gap-2"):
            ui.label("Run summary").classes("font-semibold")
            _run_summary(case, result)
            ui.button(
                "Generate report →",
                on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/report"),
            ).props("color=amber").set_enabled(result is not None)

    with ui.row().classes("w-full justify-between mt-4 gap-2"):
        ui.button(
            "← Back: Run",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/run"),
        ).props("flat color=white")
        ui.button(
            "Next: Report →",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/report"),
        ).props("color=amber").set_enabled(result is not None)


def _figure_gallery(case: Case) -> None:
    """Find every PNG / HTML under the latest run dir and list a thumbnail row.

    Wiring to the static/interactive plotly dispatcher (PR #37) is deferred
    to the polish pass — this commit just lists what's on disk so the
    analyst can confirm the figures landed.
    """
    if case.record.latest_run is None:
        ui.label("(no run yet)").classes("bitig-muted")
        return
    run_dir = case.runs_dir / case.record.latest_run
    if not run_dir.is_dir():
        ui.label("(run dir missing)").classes("bitig-err")
        return

    figures: list[Path] = []
    for ext in (".png", ".pdf", ".svg", ".html"):
        figures.extend(sorted(run_dir.rglob(f"*{ext}")))
    if not figures:
        ui.label("(no figures produced)").classes("bitig-muted")
        return

    with ui.row().classes("w-full gap-3 flex-wrap"):
        for fig in figures:
            with ui.column().classes("bitig-panel p-2 gap-1 w-48"):
                if fig.suffix == ".png":
                    ui.image(str(fig)).classes("w-full")
                else:
                    ui.icon("description").classes("text-3xl bitig-muted")
                ui.label(fig.relative_to(run_dir).as_posix()).classes(
                    "bitig-mono bitig-muted text-xs break-all"
                )


def _run_summary(case: Case, result: Result | None) -> None:
    r = case.record
    _kv("recipe", r.recipe)
    _kv("mode", r.mode)
    if result is not None:
        _kv("method", result.method_name)
        if result.provenance:
            _kv("spaCy", result.provenance.spacy_model)
            _kv("seed", str(result.provenance.seed))
    _kv("study hash", short_hash(r.study_hash))
    _kv("corpus hash", short_hash(r.corpus_hash))
    if r.latest_run:
        _kv("run", r.latest_run)
    with ui.row().classes("items-center gap-1 mt-2"):
        ui.label("● reproducible").classes("bitig-ok bitig-mono text-xs")


def _kv(label: str, value: str) -> None:
    with ui.row().classes("w-full justify-between"):
        ui.label(label).classes("bitig-mono bitig-muted text-xs")
        ui.label(value).classes("bitig-mono text-xs")
