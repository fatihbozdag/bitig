"""Recipe param drawer — side panel for editing a recipe's ParamField schema.

Spec §5.2: "Selecting a tile opens a side drawer with only the params that
recipe cares about, plus a live ``study.yaml`` preview."

Each :class:`~bitig.recipes.ParamField` declares a ``kind`` (int / float /
str / select / bool) that maps to a NiceGUI input widget. The drawer reads
the current value via :func:`bitig.recipes.read_param_target`, the user
edits it, the **Save** button writes it back via :meth:`Case.set_param`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from bitig.cases import Case, CaseError
from bitig.recipes import ParamField, Recipe, read_param_target


def open_recipe_drawer(
    case: Case,
    recipe: Recipe,
    *,
    on_save: Callable[[], None] | None = None,
) -> None:
    """Open the side drawer for ``recipe`` against ``case``.

    The drawer prefills each :class:`ParamField` from the Case's resolved
    study (so a re-opened drawer reflects prior edits). Save applies every
    field through :meth:`Case.set_param` in order; partial failures
    surface a notification and abort before subsequent writes.
    """
    resolved = case.resolved_study_dict()

    with (
        ui.dialog().props("position=right") as dialog,
        ui.card().classes("bg-slate-900 text-slate-100 w-96 h-screen overflow-y-auto"),
        ui.column().classes("w-full gap-2"),
    ):
        ui.label(recipe.title).classes("text-lg font-semibold")
        ui.label(recipe.question).classes("bitig-muted text-sm")
        ui.label(f"id={recipe.id}  mode={recipe.mode}").classes("bitig-mono bitig-muted text-xs")

        ui.separator().style("background: var(--bitig-border);")

        if not recipe.param_schema:
            ui.label("(no tunable parameters for this recipe)").classes("bitig-muted")
        inputs: list[tuple[ParamField, Any]] = []
        for field in recipe.param_schema:
            current = read_param_target(resolved, field.target)
            widget = _build_widget(field, current)
            inputs.append((field, widget))

        status = ui.label("").classes("bitig-err text-sm")

        def save() -> None:
            for field, widget in inputs:
                value = _read_widget_value(field, widget)
                try:
                    case.set_param(field.target, value)
                except (CaseError, KeyError, ValueError) as exc:
                    status.set_text(f"failed at {field.label}: {exc}")
                    return
            ui.notify("parameters saved", type="positive")
            dialog.close()
            if on_save is not None:
                on_save()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat color=white")
            ui.button("Save", on_click=save).props("color=amber")

    dialog.open()


def _build_widget(field: ParamField, current: Any) -> Any:
    """Return a NiceGUI widget appropriate for ``field.kind`` prefilled with ``current``."""
    value = current if current is not None else field.default

    if field.kind == "int":
        return (
            ui.number(label=field.label, value=value, precision=0)
            .classes("w-full")
            .tooltip(field.help or "")
        )
    if field.kind == "float":
        return (
            ui.number(label=field.label, value=value, format="%.4f")
            .classes("w-full")
            .tooltip(field.help or "")
        )
    if field.kind == "bool":
        return ui.switch(field.label, value=bool(value)).tooltip(field.help or "")
    if field.kind == "select":
        options = list(field.options or ())
        return (
            ui.select(
                options=options,
                label=field.label,
                value=value if value in options else field.default,
            )
            .classes("w-full")
            .tooltip(field.help or "")
        )
    # str (and fallback)
    return (
        ui.input(label=field.label, value=str(value) if value is not None else "")
        .classes("w-full")
        .tooltip(field.help or "")
    )


def _read_widget_value(field: ParamField, widget: Any) -> Any:
    """Coerce the widget's raw value back to ``field.kind``."""
    raw = getattr(widget, "value", None)
    if field.kind == "int":
        return int(raw) if raw is not None and raw != "" else field.default
    if field.kind == "float":
        return float(raw) if raw is not None and raw != "" else field.default
    if field.kind == "bool":
        return bool(raw)
    return raw if raw not in (None, "") else field.default
