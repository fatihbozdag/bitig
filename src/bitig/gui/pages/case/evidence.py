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
    # Compute the mismatch set once (verify_custody already hashed every file)
    # and thread it to the cards, instead of each card re-hashing (audit P3).
    mismatch_paths = {m.path for m in custody}
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
                case,
                role,
                title,
                subtitle,
                rerender=lambda: _rerender(case, container),
                mismatch_paths=mismatch_paths,
            )
        if case.record.mode == "forensic":
            _render_control_corpus(case, rerender=lambda: _rerender(case, container))

    # Footer nav. Block progress on a chain-of-custody mismatch (audit P1.9):
    # the spec (cases.verify_custody docstring) says a mismatch must block
    # step 4+, and an analyst must not carry tampered evidence into a report.
    with ui.row().classes("w-full justify-end mt-4 gap-2"):
        next_btn = ui.button(
            "Next: Method →",
            on_click=lambda: ui.navigate.to(f"/case/{case.record.id}/method"),
        ).props("color=amber")
        next_btn.set_enabled(
            bool(case.record.evidence.questioned or case.record.evidence.known) and not custody
        )
        if custody:
            next_btn.tooltip("Resolve the chain-of-custody mismatch above before continuing.")


def _rerender(case: Case, container: ui.column) -> None:
    """Reload the Case from disk + redraw the role panels."""
    case = Case.load(case.root)  # refresh against disk
    mismatch_paths = {m.path for m in case.verify_custody()}
    container.clear()
    refresh_roles: list[tuple[EvidenceRole, str, str]] = [
        ("questioned", "Questioned", "Files of disputed authorship"),
        ("known", "Known", "Files attributed to a candidate author"),
    ]
    with container:
        for role, title, subtitle in refresh_roles:
            _render_role_dropzone(
                case,
                role,
                title,
                subtitle,
                rerender=lambda: _rerender(case, container),
                mismatch_paths=mismatch_paths,
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
    mismatch_paths: set[str],
) -> None:
    bucket = cast(list[EvidenceEntry], getattr(case.record.evidence, role))
    with ui.column().classes("w-full bitig-panel p-4 gap-2"):
        with ui.row().classes("w-full items-baseline"):
            ui.label(title).classes("text-lg font-semibold")
            ui.label(subtitle).classes("bitig-mono bitig-muted text-xs")
            ui.space()
            ui.label(f"{len(bucket)} file(s)").classes("bitig-mono bitig-muted text-xs")

        # Known texts need an author label: verification picks the candidate
        # and the impostors by it (audit 2026-09-26 N-P0.1).
        author_input = (
            ui.input("Author label", placeholder="e.g. Alice").classes("w-64")
            if role == "known"
            else None
        )

        async def add_files() -> None:
            chosen = await pick_file(f"Select {role} file", file_types=("All files (*.*)",))
            if not chosen:
                return
            try:
                author = (author_input.value or "").strip() if author_input is not None else ""
                if role == "known" and not author:
                    ui.notify("Enter an author label for the known file first.", type="warning")
                    return
                case.add_evidence(Path(chosen), role=role, author=author or None)
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
            mismatched = entry.path in mismatch_paths
            render_evidence_card(
                title=Path(entry.path).name,
                meta=f"{entry.tokens} tokens · " + (f"{entry.author}" if entry.author else "—"),
                provenance=f"{short_hash(entry.sha256)} role={entry.role}",
                # mismatch_paths already reflects the single verify_custody pass.
                state="err" if mismatched else "default",
            )
            if mismatched and not case.record.signed:
                ui.button(
                    "Re-acknowledge…",
                    icon="fact_check",
                    on_click=lambda e=entry: _open_reacknowledge_dialog(case, e.path, rerender),
                ).props("flat color=amber")


def _open_reacknowledge_dialog(case: Case, path: str, rerender: Callable[[], None]) -> None:
    """Record why a changed evidence file is legitimate (sealed custody log)."""
    with ui.dialog() as dialog, ui.card().classes("w-[36rem]"):
        ui.label(f"Re-acknowledge {path}").classes("text-lg font-semibold")
        ui.label(
            "This file no longer matches its registered hash. If the change is legitimate, "
            "state why. The old and new hashes, your reason, name and the time are recorded "
            "in the chain-of-custody log, which is sealed and printed in the report. The "
            "analysis must be re-run before signing. If the file should not have changed, "
            "fork the case instead (`bitig case fork`)."
        ).classes("bitig-muted text-sm")
        reason = ui.textarea("Reason (required)").classes("w-full")
        by = ui.input("Acknowledged by", value=case.record.examiner).classes("w-full")

        def confirm() -> None:
            try:
                case.reacknowledge_evidence(path, reason=reason.value or "", by=by.value or None)
            except CaseError as exc:
                ui.notify(str(exc), type="negative")
                return
            dialog.close()
            ui.notify(f"re-acknowledged {path}; re-run before signing", type="warning")
            rerender()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Re-acknowledge", on_click=confirm).props("color=amber")
    dialog.open()


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
