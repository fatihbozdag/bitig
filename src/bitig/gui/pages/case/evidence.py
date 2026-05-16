"""``/case/{case_id}/evidence`` — Step 1 of the Forensic Lab flow (spec §5.1)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from nicegui import ui

from bitig.cases import Case, CaseError, EvidenceEntry, EvidenceRole
from bitig.gui.case_layout import case_shell, render_evidence_card
from bitig.gui.filepicker import is_native_available, pick_file
from bitig.gui.pages.case._helpers import resolve_case, short_hash
from bitig.gui.state import get_state


@ui.page("/case/{case_id}/evidence")
def case_evidence_page(case_id: str) -> None:
    case = resolve_case(case_id)
    if case is None:
        ui.label(f"Case not found: {case_id}").classes("p-6")
        ui.button("Back to case list", on_click=lambda: ui.navigate.to("/case"))
        return
    get_state().current_case_id = case_id

    with case_shell(case, "evidence"):
        _render_body(case)


def _render_body(case: Case) -> None:
    custody = case.verify_custody()
    if custody:
        with (
            ui.row()
            .classes("w-full p-3 mb-2")
            .style(
                "background: rgba(248, 81, 73, 0.12); border: 1px solid var(--bitig-err); border-radius: 3px;"
            )
        ):
            ui.icon("warning").classes("bitig-err")
            ui.label(
                f"Chain-of-custody mismatch on {len(custody)} file(s) — verify before continuing"
            ).classes("bitig-err")

    roles: list[tuple[EvidenceRole, str, str]] = [
        ("questioned", "Questioned", "Files of disputed authorship"),
        ("known", "Known", "Files attributed to a candidate author"),
    ]
    # Control corpus is a reference, not files dropped here — rendered separately below.

    container = ui.column().classes("w-full gap-4")
    with container:
        for role, title, subtitle in roles:
            _render_role_dropzone(
                case, role, title, subtitle, rerender=lambda: _rerender(case, container)
            )
        if case.record.mode == "forensic":
            _render_control_corpus(case, rerender=lambda: _rerender(case, container))

    # Footer nav
    with ui.row().classes("w-full justify-end mt-4 gap-2"):
        ui.button(
            "Next: Method →",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/method"),
        ).props("color=amber").set_enabled(
            bool(case.record.evidence.questioned or case.record.evidence.known)
        )


def _rerender(case: Case, container: ui.column) -> None:
    """Reload the Case from disk + redraw the role panels."""
    case = Case.load(case.root)  # refresh against disk
    container.clear()
    refresh_roles: list[tuple[EvidenceRole, str, str]] = [
        ("questioned", "Questioned", "Files of disputed authorship"),
        ("known", "Known", "Files attributed to a candidate author"),
    ]
    with container:
        for role, title, subtitle in refresh_roles:
            _render_role_dropzone(
                case, role, title, subtitle, rerender=lambda: _rerender(case, container)
            )
        if case.record.mode == "forensic":
            _render_control_corpus(case, rerender=lambda: _rerender(case, container))


def _render_role_dropzone(
    case: Case,
    role: EvidenceRole,
    title: str,
    subtitle: str,
    *,
    rerender: Callable[[], None],
) -> None:
    bucket = cast(list[EvidenceEntry], getattr(case.record.evidence, role))
    with ui.column().classes("w-full bitig-panel p-4 gap-2"):
        with ui.row().classes("w-full items-baseline"):
            ui.label(title).classes("text-lg font-semibold")
            ui.label(subtitle).classes("bitig-mono bitig-muted text-xs")
            ui.space()
            ui.label(f"{len(bucket)} file(s)").classes("bitig-mono bitig-muted text-xs")

        async def add_files() -> None:
            chosen = await pick_file(f"Select {role} file", file_types=("All files (*.*)",))
            if not chosen:
                return
            try:
                case.add_evidence(Path(chosen), role=role)
            except (CaseError, FileNotFoundError) as exc:
                ui.notify(str(exc), type="negative")
                return
            ui.notify(f"registered {Path(chosen).name}", type="positive")
            rerender()

        native = is_native_available()
        with ui.row().classes("w-full gap-2"):
            btn = ui.button("+ Add file", icon="upload_file", on_click=add_files).props(
                "outline color=amber"
            )
            btn.set_enabled(native and not case.record.signed)
            if not native:
                btn.tooltip("Native file picker required (run without --no-native).")

        for entry in bucket:
            render_evidence_card(
                title=Path(entry.path).name,
                meta=f"{entry.tokens} tokens · " + (f"{entry.author}" if entry.author else "—"),
                provenance=f"{short_hash(entry.sha256)} role={entry.role}",
                state=(
                    "err"
                    if (case.root / entry.path).is_file() is False or _hash_mismatch(case, entry)
                    else "default"
                ),
            )


def _hash_mismatch(case: Case, entry: EvidenceEntry) -> bool:
    from bitig.cases import hash_file

    abs_path = case.root / entry.path
    if not abs_path.is_file():
        return True
    return hash_file(abs_path) != entry.sha256


def _render_control_corpus(case: Case, *, rerender: Callable[[], None]) -> None:
    with ui.column().classes("w-full bitig-panel p-4 gap-2"):
        with ui.row().classes("w-full items-baseline"):
            ui.label("Control (impostor pool)").classes("text-lg font-semibold")
            ui.label("External corpus referenced by id").classes("bitig-mono bitig-muted text-xs")

        ref = case.record.evidence.control
        corpus_id_input = ui.input(
            label="Corpus id",
            value=ref.corpus_id if ref else "",
            placeholder="BUMR-AT-2024",
        ).classes("w-80")
        n_docs_input = ui.number(
            label="n_docs",
            value=ref.n_docs if ref else 0,
            min=0,
        ).classes("w-40")

        def save_control() -> None:
            try:
                case.set_control_corpus(
                    (corpus_id_input.value or "").strip(),
                    n_docs=int(n_docs_input.value or 0),
                )
            except CaseError as exc:
                ui.notify(str(exc), type="negative")
                return
            ui.notify("control corpus set", type="positive")
            rerender()

        ui.button("Save control", on_click=save_control).props("outline color=amber").set_enabled(
            not case.record.signed
        )
