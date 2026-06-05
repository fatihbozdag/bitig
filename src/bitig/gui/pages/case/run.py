"""``/case/{case_id}/run`` — Step 3 of the Forensic Lab flow (spec §5.3)."""

from __future__ import annotations

from nicegui import run as nicegui_run
from nicegui import ui

from bitig.case_run import perform_run
from bitig.cases import Case
from bitig.gui.case_layout import case_shell
from bitig.gui.pages.case._helpers import resolve_case, short_hash
from bitig.gui.state import get_state


@ui.page("/case/{case_id}/run")
def case_run_page(case_id: str) -> None:
    case = resolve_case(case_id)
    if case is None:
        ui.label(f"Case not found: {case_id}").classes("p-6")
        return
    get_state().current_case_id = case_id

    with case_shell(case, "run"):
        _render_body(case)


def _render_body(case: Case) -> None:
    with ui.column().classes("w-full gap-4"):
        with ui.column().classes("w-full bitig-panel p-4 gap-2"):
            ui.label("Resolved configuration").classes("font-semibold")
            with ui.row().classes("gap-4 flex-wrap"):
                _kv("recipe", case.record.recipe)
                _kv("mode", case.record.mode)
                _kv("study.yaml", str(case.study_yaml_path))
                _kv("study hash", short_hash(case.record.study_hash))
                _kv("corpus hash", short_hash(case.record.corpus_hash))

        with ui.row().classes("w-full bitig-panel p-4 gap-3 items-center"):
            ui.label("Runs:").classes("bitig-mono bitig-muted text-xs")
            ui.label(str(len(case.record.runs))).classes("bitig-mono")
            ui.space()
            if case.record.latest_run:
                ui.label(f"latest: {case.record.latest_run}").classes(
                    "bitig-mono bitig-muted text-xs"
                )

        log_box = (
            ui.log(max_lines=400)
            .classes("w-full h-72 bitig-mono text-xs")
            .style("background: var(--bitig-bg-deep); color: var(--bitig-text-2);")
        )
        status_label = ui.label("ready").classes("bitig-mono bitig-muted text-xs")
        run_btn = ui.button("Run analysis", icon="play_arrow").props("color=amber")

    # Footer nav created before the run handler so execute() can re-enable the
    # Findings button after a successful run (audit P2: it used to stay disabled
    # because it was evaluated once at render time).
    with ui.row().classes("w-full justify-between mt-4 gap-2"):
        ui.button(
            "← Back: Method",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/method"),
        ).props("flat color=white")
        next_btn = ui.button(
            "Next: Findings →",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/findings"),
        ).props("color=amber")
        next_btn.set_enabled(bool(case.record.runs))

    async def execute() -> None:
        run_btn.set_enabled(False)
        status_label.set_text("running…")
        log_box.clear()
        log_box.push("Running study (this can take a while)…")

        outcome = await nicegui_run.io_bound(perform_run, case)

        for m in outcome.methods:
            mark = "✓" if m.ok else "✗"
            line = f"{mark} {m.method_id}" + ("" if m.ok else f" — {m.error}")
            log_box.push(line)
        log_box.push(outcome.message)
        status_label.set_text(outcome.status)

        ui.notify(
            outcome.message,
            type="positive" if outcome.unlocks_findings else "negative",
            multi_line=True,
        )
        # Only unlock Findings when the run actually produced a result.
        next_btn.set_enabled(outcome.unlocks_findings or bool(case.record.runs))
        run_btn.set_enabled(not case.record.signed)

    run_btn.on_click(execute)
    run_btn.set_enabled(not case.record.signed and case.study_yaml_path.is_file())


def _kv(label: str, value: str) -> None:
    with ui.column().classes("gap-0"):
        ui.label(label).classes("bitig-mono bitig-muted text-xs")
        ui.label(value).classes("bitig-mono text-xs")
