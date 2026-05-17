"""``/case`` — Forensic Lab landing page (case list + new-case dialog)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nicegui import ui

from bitig._version import __version__
from bitig.cases import Case, CaseError, list_cases
from bitig.gui.case_layout import TOKENS
from bitig.gui.state import get_state
from bitig.recipes import RECIPES


@ui.page("/case")
def case_landing_page() -> None:
    state = get_state()
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
            ui.label(f"v{__version__}").classes("bitig-mono bitig-muted text-xs")
            ui.button("New case", icon="add", on_click=lambda: _new_case_dialog(reload)).props(
                "color=amber"
            )

        with ui.column().classes("w-full max-w-6xl mx-auto px-6 py-6 gap-4"):
            with ui.row().classes("w-full items-baseline gap-3"):
                ui.label("Cases").classes("text-2xl font-semibold")
                ui.label(f"// {state.cases_dir}").classes("bitig-mono bitig-muted text-xs")
                ui.space()
                ui.button(
                    "Legacy →",
                    on_click=lambda: ui.navigate.to("/ingest"),
                    icon="open_in_new",
                ).props("flat color=white").tooltip(
                    "Open the legacy flat Ingest/Study/Run/Results/Forensic pages"
                )

            cases_container = ui.column().classes("w-full gap-2")

            def reload() -> None:
                cases_container.clear()
                with cases_container:
                    _render_case_list(state.cases_dir)

            reload()


def _render_case_list(cases_dir: Path) -> None:
    """Render the rows of cases under ``cases_dir``."""
    try:
        cases = list_cases(cases_dir)
    except OSError as exc:
        ui.label(f"error reading {cases_dir}: {exc}").classes("bitig-err")
        return

    if not cases:
        with ui.column().classes("w-full bitig-panel p-6 items-center gap-2"):
            ui.label(f"No cases yet under {cases_dir}").classes("bitig-muted")
            ui.label("Click 'New case' to start one.").classes("bitig-mono bitig-muted text-xs")
        return

    for case in cases:
        _case_row(case)


def _case_row(case: Case) -> None:
    r = case.record
    n_evidence = len(r.evidence.questioned) + len(r.evidence.known)
    with (
        ui.row()
        .classes("w-full bitig-panel p-3 items-center gap-3 cursor-pointer")
        .on("click", lambda c=r.id: ui.navigate.to(f"/case/{c}/evidence"))
    ):
        # Mode badge
        mode_klass = "bitig-warn" if r.mode == "forensic" else "bitig-info"
        ui.label(r.mode.upper()).classes(f"bitig-mono text-xs {mode_klass} w-24")
        ui.label(r.id).classes("bitig-mono font-bold w-40")
        ui.label(r.title).classes("flex-1")
        ui.label(r.recipe).classes("bitig-mono bitig-muted text-xs w-32")
        ui.label(f"{n_evidence} ev").classes("bitig-mono bitig-muted text-xs w-16")
        ui.label(f"{len(r.runs)} run").classes("bitig-mono bitig-muted text-xs w-16")
        if r.signed:
            ui.label("● SIGNED").classes("bitig-mono bitig-ok text-xs w-24")
        else:
            ui.label("").classes("w-24")


def _new_case_dialog(on_created: Callable[[], None]) -> None:
    """Open a modal to collect (id, title, examiner, recipe) and create a Case."""
    state = get_state()

    with ui.dialog() as dialog, ui.card().classes("bg-slate-900 text-slate-100"):
        ui.label("New case").classes("text-lg font-semibold")

        id_input = ui.input(label="Case id (slug)", placeholder="r-v-doe").classes("w-80")
        title_input = ui.input(
            label="Title", placeholder="R v. Doe — anonymous letter authorship"
        ).classes("w-80")
        examiner_input = ui.input(label="Examiner").classes("w-80")
        recipe_select = ui.select(
            options=sorted(RECIPES),
            value="imposters_lr",
            label="Recipe",
        ).classes("w-80")

        status = ui.label("").classes("bitig-err text-sm")

        def submit() -> None:
            try:
                case = Case.create(
                    state.cases_dir,
                    id=(id_input.value or "").strip(),
                    title=(title_input.value or "").strip(),
                    examiner=(examiner_input.value or "").strip(),
                    recipe=recipe_select.value,
                )
            except (CaseError, KeyError, ValueError) as exc:
                status.set_text(str(exc))
                return
            state.current_case_id = case.record.id
            dialog.close()
            on_created()
            ui.navigate.to(f"/case/{case.record.id}/evidence")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Create", on_click=submit).props("color=amber")

    dialog.open()
