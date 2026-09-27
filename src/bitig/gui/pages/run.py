"""Run page — execute ``run_study`` against the saved study.yaml."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from bitig.gui.background import io_bound
from bitig.gui.layout import page_shell
from bitig.gui.state import get_state
from bitig.runner import run_study


@ui.page("/run")
def run_page() -> None:
    state = get_state()

    with page_shell("Run"):
        study_path = state.study_path
        if study_path is None:
            ui.markdown(
                "_No study.yaml saved yet._ Go to **Study** and configure + save a study first."
            )
            ui.button("← Study", on_click=lambda: ui.navigate.to("/study")).props("flat")
            return

        ui.markdown(f"**Study:** `{study_path}`")
        log = (
            ui.textarea(
                label="Run log",
                value=(f"Ready to run study {study_path.name}\nClick 'Run study' to start.\n"),
            )
            .props("readonly rows=16")
            .classes("w-full font-mono text-xs")
        )

        status = ui.markdown("")

        with ui.row().classes("gap-2 mt-2 items-center"):
            run_button = ui.button("Run study").props("color=primary")
            ui.button(
                "Next: Results →",
                on_click=lambda: ui.navigate.to("/results"),
            ).props("flat")
            spinner = ui.spinner(size="lg").classes("hidden")

        async def do_run() -> None:
            spinner.classes(remove="hidden")
            status.set_content("**running…** this can take a while for large corpora.")
            log.value = log.value + f"\n--- running {study_path} ---\n"
            try:
                run_dir = await io_bound(run_study, study_path)
            except Exception as exc:
                spinner.classes(add="hidden")
                status.set_content(f"**failed:** {type(exc).__name__}: {exc}")
                log.value = log.value + f"\n[error] {type(exc).__name__}: {exc}\n"
                return
            spinner.classes(add="hidden")
            state.run_dir = Path(run_dir)
            status.set_content(f"**done.** Results in `{state.run_dir}`")
            log.value = log.value + f"\n[done] {state.run_dir}\n"

        run_button.on_click(do_run)
