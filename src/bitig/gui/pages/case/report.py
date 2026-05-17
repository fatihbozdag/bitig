"""``/case/{case_id}/report`` — Step 5 of the Forensic Lab flow (spec §5.5).

Two layouts, picked by ``case.mode``: forensic (LR + verbal scale +
hypotheses + chain of custody) or research (research question + headline
result + methods + data availability). Both share the toolbar with
**Export PDF** and **Sign & lock**.

This commit lands the page structure end-to-end (toolbar wiring, mode
dispatch, signed-state freeze). Polishing the report body to mockup parity
(brass-bordered LR card, verbal-scale ladder rungs, full chain-of-custody
table) is deferred to the report-renderer split in spec §7 step 6.
"""

from __future__ import annotations

from datetime import UTC, datetime

from nicegui import ui

from bitig.cases import Case, CaseError
from bitig.gui.case_layout import case_shell
from bitig.gui.pages.case._helpers import (
    headline_scalars,
    load_latest_result,
    lr_verbal_rung,
    resolve_case,
    short_hash,
)
from bitig.gui.state import get_state
from bitig.report.case_report import (
    ReportRendererError,
    build_case_report,
)


@ui.page("/case/{case_id}/report")
def case_report_page(case_id: str) -> None:
    case = resolve_case(case_id)
    if case is None:
        ui.label(f"Case not found: {case_id}").classes("p-6")
        return
    get_state().current_case_id = case_id

    with case_shell(case, "report"):
        _render_toolbar(case)
        with (
            ui.column().classes("w-full bitig-report-surface p-8 gap-4").style("min-height: 600px;")
        ):
            if case.record.mode == "forensic":
                _render_forensic_body(case)
            else:
                _render_research_body(case)


def _render_toolbar(case: Case) -> None:
    with ui.row().classes("w-full bitig-panel px-4 py-2 items-center gap-3"):
        if case.record.signed:
            ui.label("● SIGNED").classes("bitig-ok bitig-mono text-sm")
            ui.label(f"@ {case.record.signed_at} by {case.record.signed_by}").classes(
                "bitig-mono bitig-muted text-xs"
            )
        else:
            ui.label("▎ draft · not signed").classes("bitig-mono bitig-muted text-sm")

        ui.space()

        ui.button("Export PDF", icon="picture_as_pdf", on_click=lambda: _export_pdf(case)).props(
            "outline color=white"
        )
        sign_btn = ui.button("Sign & lock", icon="lock", on_click=lambda: _sign(case)).props(
            "color=amber"
        )
        sign_btn.set_enabled(not case.record.signed)


def _sign(case: Case) -> None:
    state = get_state()
    try:
        payload = case.mark_signed(signed_by=state.current_case_id and case.record.examiner)
    except CaseError as exc:
        ui.notify(str(exc), type="negative")
        return
    ui.notify(f"signed at {payload['signed_at']}", type="positive")
    ui.navigate.to(f"/case/{case.record.id}/report")


def _export_pdf(case: Case) -> None:
    """Render the Case → HTML draft → WeasyPrint PDF (spec §7 step 6)."""
    # Always write the draft HTML first so it stays the canonical
    # working file even if PDF export fails (missing WeasyPrint, etc.).
    draft = build_case_report(case, format="html")
    try:
        pdf_path = build_case_report(case, format="pdf")
    except ReportRendererError as exc:
        ui.notify(
            f"PDF export unavailable: {exc}. Draft HTML at: {draft}",
            type="warning",
            multi_line=True,
        )
        return
    ui.notify(f"PDF exported to {pdf_path}", type="positive")


# ---------------------------------------------------------------------------
# Body layouts
# ---------------------------------------------------------------------------


def _render_forensic_body(case: Case) -> None:
    result = load_latest_result(case)
    scalars = headline_scalars(case, result)

    # Title block
    ui.label(case.record.title).classes("text-2xl font-semibold")
    ui.label(
        f"Examiner: {case.record.examiner}  ·  Date: {_now_iso()}  ·  case={case.record.id}"
    ).style("color: #555; font-family: var(--bitig-font-mono); font-size: 12px;")

    ui.html("<hr style='border-color: #ddd;'>")

    # Hypotheses
    ui.label("Hypotheses").classes("text-lg font-semibold")
    ui.label("H_p (prosecution): the questioned text and the known texts share an author.")
    ui.label("H_d (defence):   the questioned text and the known texts do not share an author.")

    # LR block + verbal scale
    lr_label, lr_value = scalars[0] if scalars else ("LR", "—")
    lr_float = _maybe_float(lr_value)
    with ui.row().classes("w-full items-center gap-4 mt-2"):
        with (
            ui.column()
            .classes("p-4")
            .style(
                "border-left: 4px solid var(--bitig-accent); background: #fff; min-width: 200px;"
            )
        ):
            ui.label(lr_label).classes("bitig-mono").style("color: #555; font-size: 12px;")
            ui.label(lr_value).style(
                "font-family: var(--bitig-font-serif); font-size: 34px; color: #1a1a2e;"
            )
        if lr_float is not None and case.record.mode == "forensic":
            rung = lr_verbal_rung(lr_float)
            with ui.column().classes("gap-1"):
                ui.label("Verbal scale (ENFSI):").style("font-size: 12px; color: #555;")
                for label_, lo, hi in _LADDER_DISPLAY:
                    active = label_ == rung
                    style = (
                        "font-weight: 600; color: var(--bitig-accent);"
                        if active
                        else "color: #555;"
                    )
                    ui.label(f"  {label_}  ({lo}-{hi})").style(style)

    # Method paragraph + chain of custody
    with ui.row().classes("w-full gap-6 mt-2"):
        with ui.column().classes("flex-1 gap-1"):
            ui.label("Method").classes("text-lg font-semibold")
            method_text = result.method_name if result else "(no run yet)"
            ui.label(
                f"Authorship verification was performed via {method_text}. The likelihood "
                "ratio above expresses how much more probable the observed evidence is "
                "under H_p than under H_d."
            )
        with ui.column().classes("w-96 gap-1"):
            ui.label("Chain of custody").classes("text-lg font-semibold")
            for e in case.record.evidence.questioned + case.record.evidence.known:
                ui.label(
                    f"{e.role}: {e.path} — {e.tokens} tokens — sha256={short_hash(e.sha256)}"
                ).style("font-family: var(--bitig-font-mono); font-size: 12px;")
            if case.record.evidence.control:
                c = case.record.evidence.control
                ui.label(f"control: {c.corpus_id} (n_docs={c.n_docs})").style(
                    "font-family: var(--bitig-font-mono); font-size: 12px;"
                )

    # Provenance footer
    ui.html("<hr style='border-color: #ddd;'>")
    if result and result.provenance:
        p = result.provenance
        ui.label(
            f"corpus={short_hash(p.corpus_hash)} · feature={short_hash(p.feature_hash or '')} · "
            f"study={short_hash(case.record.study_hash)} · seed={p.seed} · "
            f"bitig {p.bitig_version} · spaCy {p.spacy_model}"
        ).style("font-family: var(--bitig-font-mono); font-size: 11px; color: #777;")


def _render_research_body(case: Case) -> None:
    result = load_latest_result(case)
    scalars = headline_scalars(case, result)

    ui.label(case.record.title).classes("text-2xl font-semibold")
    ui.label(
        f"Examiner: {case.record.examiner}  ·  Date: {_now_iso()}  ·  case={case.record.id}"
    ).style("color: #555; font-family: var(--bitig-font-mono); font-size: 12px;")
    ui.html("<hr style='border-color: #ddd;'>")

    ui.label("Research question").classes("text-lg font-semibold")
    ui.label(f"Recipe: {case.record.recipe}")

    # Headline result card
    with ui.row().classes("w-full gap-4 mt-2"):
        with (
            ui.column()
            .classes("p-4")
            .style(
                "border-left: 4px solid var(--bitig-accent); background: #fff; min-width: 200px;"
            )
        ):
            head_label, head_value = scalars[0] if scalars else ("result", "—")
            ui.label(head_label).classes("bitig-mono").style("color: #555; font-size: 12px;")
            ui.label(head_value).style(
                "font-family: var(--bitig-font-serif); font-size: 34px; color: #1a1a2e;"
            )
        with ui.column().classes("flex-1 gap-1"):
            ui.label("Method context").classes("text-lg font-semibold")
            method_text = result.method_name if result else "(no run yet)"
            ui.label(
                f"Result derived via {method_text} over the registered corpus. See the "
                "Findings step for figures and additional scalars."
            )

    ui.label("Methods").classes("text-lg font-semibold mt-2")
    ui.label(
        f"Recipe: {case.record.recipe}. Resolved configuration is committed alongside "
        f"the run artefacts under {case.runs_dir}/{case.record.latest_run or '<run_id>'}/."
    )

    ui.label("Data availability & citations").classes("text-lg font-semibold mt-2")
    ui.label(
        "Data availability and citations land via the report-renderer split (spec §7 "
        "step 6), which wires this section to CITATION.cff and per-corpus provenance."
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


_LADDER_DISPLAY: list[tuple[str, str, str]] = [
    ("weak support", "1", "10"),
    ("moderate support", "10", "100"),
    ("strong support", "100", "1000"),
    ("very strong support", "1000", "10000"),
    ("extremely strong support", "10000", "∞"),
]


def _maybe_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")
