"""``/case/{case_id}/run`` — Step 3 of the Forensic Lab flow (spec §5.3)."""

from __future__ import annotations

from datetime import UTC, datetime

from nicegui import run as nicegui_run
from nicegui import ui

from bitig.cases import Case
from bitig.gui.case_layout import case_shell
from bitig.gui.pages.case._helpers import resolve_case, short_hash
from bitig.gui.state import get_state
from bitig.runner import run_study


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

        async def execute() -> None:
            if case.record.signed:
                ui.notify("Case is signed; cannot re-run.", type="negative")
                return
            run_btn.set_enabled(False)
            status_label.set_text("running…")
            log_box.clear()
            log_box.push("Loading study.yaml…")

            try:
                run_id = _new_run_id()
                log_box.push(f"Run id: {run_id}")
                log_box.push(f"Writing to: {case.runs_dir / run_id}")

                # `run_study` writes one subdir per method under
                # output_dir/run_name. We pass our pre-computed run_id as
                # run_name so the resulting layout is runs/<run_id>/<method>/.
                run_dir = await nicegui_run.io_bound(
                    run_study,
                    case.study_yaml_path,
                    output_dir=case.runs_dir,
                    run_name=run_id,
                )

                case.register_run(run_id)
                method_dirs = [p.name for p in run_dir.iterdir() if p.is_dir()]
                log_box.push(f"✓ run complete: methods={method_dirs}")
                status_label.set_text("done")
            except Exception as exc:
                log_box.push(f"[red]error:[/red] {type(exc).__name__}: {exc}")
                status_label.set_text("failed")
                ui.notify(f"run failed: {exc}", type="negative")
            finally:
                run_btn.set_enabled(True)

        run_btn.on_click(execute)
        run_btn.set_enabled(not case.record.signed and case.study_yaml_path.is_file())

    with ui.row().classes("w-full justify-between mt-4 gap-2"):
        ui.button(
            "← Back: Method",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/method"),
        ).props("flat color=white")
        ui.button(
            "Next: Findings →",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/findings"),
        ).props("color=amber").set_enabled(bool(case.record.runs))


def _kv(label: str, value: str) -> None:
    with ui.column().classes("gap-0"):
        ui.label(label).classes("bitig-mono bitig-muted text-xs")
        ui.label(value).classes("bitig-mono text-xs")


def _new_run_id() -> str:
    """ISO-8601 UTC run id with filesystem-safe punctuation (spec §2)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
