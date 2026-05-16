"""``/case/{case_id}/method`` — Step 2 of the Forensic Lab flow (spec §5.2)."""

from __future__ import annotations

import yaml
from nicegui import ui

from bitig.cases import Case, CaseError
from bitig.gui.case_layout import case_shell
from bitig.gui.pages.case._helpers import resolve_case
from bitig.gui.state import get_state
from bitig.recipes import CUSTOM_RECIPE_ID, RECIPES, Recipe


@ui.page("/case/{case_id}/method")
def case_method_page(case_id: str) -> None:
    case = resolve_case(case_id)
    if case is None:
        ui.label(f"Case not found: {case_id}").classes("p-6")
        return
    get_state().current_case_id = case_id

    with case_shell(case, "method"):
        _render_body(case)


def _render_body(case: Case) -> None:
    container = ui.column().classes("w-full gap-4")
    with container:
        ui.label("Choose a recipe").classes("text-lg font-semibold")
        ui.label(
            "Each recipe answers a different question — pick the one matching your goal."
        ).classes("bitig-muted text-sm")

        with ui.row().classes("w-full gap-3 flex-wrap"):
            for recipe in RECIPES.values():
                _recipe_tile(case, recipe)
            _custom_tile(case)

        ui.separator().style("background: var(--bitig-border);")
        _yaml_preview(case)

    with ui.row().classes("w-full justify-between mt-4 gap-2"):
        ui.button(
            "← Back: Evidence",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/evidence"),
        ).props("flat color=white")
        ui.button(
            "Next: Run →",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/run"),
        ).props("color=amber").set_enabled(case.study_yaml_path.is_file())


def _recipe_tile(case: Case, recipe: Recipe) -> None:
    selected = case.record.recipe == recipe.id
    klass = "bitig-tile w-72" + (" selected" if selected else "")

    def select() -> None:
        try:
            case.change_recipe(recipe.id)
        except CaseError as exc:
            ui.notify(str(exc), type="negative")
            return
        ui.notify(f"recipe → {recipe.id}", type="positive")
        ui.navigate.to(f"/case/{case.record.id}/method")  # rerender

    with ui.column().classes(klass).on("click", select):
        mode_klass = "bitig-warn" if recipe.mode == "forensic" else "bitig-info"
        with ui.row().classes("w-full items-baseline gap-2"):
            ui.label(recipe.title).classes("font-semibold")
            ui.space()
            ui.label(recipe.mode.upper()).classes(f"bitig-mono text-xs {mode_klass}")
        ui.label(recipe.question).classes("bitig-muted text-sm")
        ui.label(f"id={recipe.id}").classes("bitig-mono bitig-muted text-xs")


def _custom_tile(case: Case) -> None:
    selected = case.record.recipe == CUSTOM_RECIPE_ID
    klass = "bitig-tile w-72" + (" selected" if selected else "")
    with ui.column().classes(klass).on("click", lambda: _open_custom_editor(case)):
        ui.label("Custom").classes("font-semibold")
        ui.label("Edit study.yaml directly (escape hatch).").classes("bitig-muted text-sm")
        ui.label("id=custom").classes("bitig-mono bitig-muted text-xs")


def _open_custom_editor(case: Case) -> None:
    """Slide-over for hand-editing study.yaml (spec §5.2)."""
    current_text = (
        case.study_yaml_path.read_text(encoding="utf-8") if case.study_yaml_path.is_file() else ""
    )

    with (
        ui.dialog().props("maximized") as dialog,
        ui.card().classes("bg-slate-900 text-slate-100 w-full h-full"),
    ):
        ui.label("Custom study.yaml").classes("text-lg font-semibold")
        ui.label(
            "Save the edits below and the Case will switch to recipe=custom; "
            "mode is re-derived (forensic iff any method.kind == 'verify')."
        ).classes("bitig-muted text-sm")

        editor = ui.codemirror(value=current_text, language="YAML").classes("w-full flex-1")

        status = ui.label("").classes("bitig-err text-sm")

        def save() -> None:
            text = editor.value or ""
            try:
                parsed = yaml.safe_load(text) or {}
                if not isinstance(parsed, dict):
                    raise ValueError("study.yaml must be a mapping at the top level.")
                # Strip the bits Case manages so change_recipe() can refill them
                # (corpus.path and seed are derived from the Case).
                parsed.pop("corpus", None)
                case.change_recipe(CUSTOM_RECIPE_ID, overrides=parsed)
            except (yaml.YAMLError, ValueError, CaseError) as exc:
                status.set_text(str(exc))
                return
            dialog.close()
            ui.navigate.to(f"/case/{case.record.id}/method")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat color=white")
            ui.button("Save", on_click=save).props("color=amber")

    dialog.open()


def _yaml_preview(case: Case) -> None:
    """Live preview of the resolved study.yaml (read-only)."""
    text = (
        case.study_yaml_path.read_text(encoding="utf-8")
        if case.study_yaml_path.is_file()
        else "# study.yaml not generated yet"
    )
    with ui.column().classes("w-full bitig-panel p-3 gap-1"):
        with ui.row().classes("w-full items-baseline"):
            ui.label("resolved study.yaml").classes("bitig-mono bitig-muted text-xs")
            ui.space()
            ui.label(case.record.recipe).classes("bitig-mono bitig-accent text-xs")
        ui.html(
            f"<pre style='color: var(--bitig-text-2); white-space: pre-wrap; "
            f"font-family: var(--bitig-font-mono); font-size: 12px; margin: 0;'>"
            f"{_escape(text)}</pre>"
        )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
