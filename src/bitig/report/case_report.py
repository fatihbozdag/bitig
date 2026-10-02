"""Render a :class:`~bitig.cases.Case` into a Forensic Lab report (spec §5.5).

Two Jinja templates (``forensic.html.j2`` and ``research.html.j2``) live
under ``bitig/report/templates``; this module picks one by ``case.mode``,
builds a :class:`~bitig.report.context.ReportContext` from the Case's
record + latest run, and writes the rendered HTML to
``case.report_dir / "draft.html"``.

When ``format="pdf"`` the HTML is also handed to WeasyPrint (declared as
an optional ``reports`` extra). If WeasyPrint isn't installed,
:exc:`ReportRendererError` surfaces with the install hint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Literal

from jinja2 import Environment

from bitig._version import __version__
from bitig.cases import Case
from bitig.forensic.verbal_scale import (
    ladder_rows,
    lr_from_values,
    lr_verbal_rung,
    lr_verbal_statement,
)
from bitig.report.context import (
    ChainOfCustodyEntry,
    CustodyLogEntry,
    HeadlineScalar,
    ProvenanceFooter,
    ReportContext,
)
from bitig.report.scalars import fmt_scalar, gi_scores, headline_scalars, load_latest_result
from bitig.result import Result

Format = Literal["html", "pdf"]
_TEMPLATE_PKG = "bitig.report.templates"


class ReportRendererError(RuntimeError):
    """Raised for any case-report rendering / export failure."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_case_report(
    case: Case,
    *,
    format: Format = "html",
    output_path: Path | None = None,
) -> Path:
    """Render ``case`` into a report and return the output path.

    Once a case is sealed, its report is **frozen**: an immutable
    ``signed.html`` snapshot is taken at sign time, and from then on this
    function serves that snapshot verbatim — it never re-renders or rewrites
    it, so Export-to-PDF on a signed case can never invalidate the sealed
    ``report_html_hash`` (audit P1.7). Until that snapshot exists the report
    is rendered fresh to ``draft.html`` (this is also the path
    ``Case.mark_signed`` drives, with the signed banner already set). When
    ``format == "pdf"`` the (fresh or frozen) HTML is rendered to a PDF at
    ``output_path`` (default ``case.report_dir / "final.pdf"``) via WeasyPrint.

    Raises :exc:`ReportRendererError` if WeasyPrint isn't installed when a PDF
    is requested.
    """
    case.report_dir.mkdir(parents=True, exist_ok=True)
    signed_html = case.report_dir / "signed.html"
    draft_path = case.report_dir / "draft.html"

    if case.record.signed:
        # Sealed — serve the immutable snapshot verbatim, never re-render, and
        # only while the seal still holds (audit 2026-09-26 N-P1.6). The
        # signature check is skipped here: exporting must not need the HMAC
        # key; `bitig case verify` covers it.
        if not signed_html.is_file():
            raise ReportRendererError(
                "Case is signed but report/signed.html is missing; refusing to render a "
                "replacement for a sealed report."
            )
        failed = [c for c in case.verify_seal().checks if c.name != "signature" and not c.ok]
        if failed:
            raise ReportRendererError(
                "Seal verification failed; refusing to export: "
                + "; ".join(f"{c.name}: {c.detail}" for c in failed)
            )
        html = signed_html.read_text(encoding="utf-8")
        report_path = signed_html
    else:
        # Unsigned: always render fresh. A stray signed.html (e.g. left by an
        # interrupted sign) is never served for an unsigned case (N-P1.3).
        html = render_case_report_html(case)
        draft_path.write_text(html, encoding="utf-8")
        report_path = draft_path

    if format == "html":
        return report_path

    # PDF path. Figure src paths are relative to report/ (../runs/<ts>/...),
    # where draft.html / signed.html live, so base_url is report_dir.
    out_pdf = output_path if output_path is not None else case.report_dir / "final.pdf"
    _export_pdf(html, out_pdf, base_url=case.report_dir)
    return out_pdf


def render_case_report_html(case: Case) -> str:
    """Render ``case``'s report to an HTML string without writing any file."""
    return _render_html(_build_context(case))


# ---------------------------------------------------------------------------
# Context construction
# ---------------------------------------------------------------------------


def _build_context(case: Case) -> ReportContext:
    result = load_latest_result(case)
    scalars = _build_headline_scalars(case, result)
    coc = _build_chain_of_custody(case)
    log = [CustodyLogEntry(**e) for e in case.record.custody_log]
    fork_note = _fork_note(case)
    provenance = _build_provenance_footer(case, result)
    figures = _list_figure_paths(case)
    case_state_hash = case._case_state_hash()
    date_iso = _today_iso()

    if case.record.mode == "forensic":
        # The verbal rung is classified from the RAW LR float, never from the
        # display-rounded string (audit P1.11). lr_value/ladder are populated
        # only when a calibrated LR actually exists (audit P1.10).
        lr = lr_from_values(result.values) if result is not None else None
        values = result.values if result is not None else {}
        gi_rows = [] if lr is not None else gi_scores(values)
        candidate = values.get("candidate")
        chance = values.get("chance")
        return ReportContext(
            mode="forensic",
            title=case.record.title,
            case_id=case.record.id,
            examiner=case.record.examiner,
            date_iso=date_iso,
            bitig_version=__version__,
            case_state_hash=case_state_hash,
            headline_scalars=scalars,
            figures=figures,
            chain_of_custody=coc,
            custody_log=log,
            forked_from=fork_note,
            provenance=provenance,
            signed=case.record.signed,
            signed_at=case.record.signed_at,
            signed_by=case.record.signed_by,
            # Hp/Hd framing only accompanies an actual likelihood ratio.
            hypothesis_p=(
                "The questioned text and the known texts share an author."
                if lr is not None
                else None
            ),
            hypothesis_d=(
                "The questioned text and the known texts do not share an author."
                if lr is not None
                else None
            ),
            verification_question=(
                f"Whether the questioned document(s) were written by the candidate author "
                f"{candidate!r}."
                if lr is None and candidate
                else None
            ),
            gi_rows=[(doc_id, fmt_scalar(score)) for doc_id, score in gi_rows],
            gi_chance=fmt_scalar(chance) if gi_rows and chance is not None else None,
            lr_value=fmt_scalar(lr) if lr is not None else None,
            lr_verbal_rung=lr_verbal_rung(lr) if lr is not None else None,
            lr_statement=lr_verbal_statement(lr) if lr is not None else None,
            lr_ladder_rows=ladder_rows() if lr is not None else [],
            method_paragraph=forensic_method_paragraph(result, has_lr=lr is not None),
        )

    return ReportContext(
        mode="research",
        title=case.record.title,
        case_id=case.record.id,
        examiner=case.record.examiner,
        date_iso=date_iso,
        bitig_version=__version__,
        case_state_hash=case_state_hash,
        headline_scalars=scalars,
        figures=figures,
        chain_of_custody=coc,
        custody_log=log,
        forked_from=fork_note,
        provenance=provenance,
        signed=case.record.signed,
        signed_at=case.record.signed_at,
        signed_by=case.record.signed_by,
        research_question=f"Recipe: {case.record.recipe}",
        hypothesis=None,
        methods_paragraph=_research_methods_paragraph(case, result),
        data_availability=None,
    )


def _build_headline_scalars(case: Case, result: Result | None) -> list[HeadlineScalar]:
    """Adapt the shared ``(label, value, is_primary)`` tuples into the Pydantic
    ``HeadlineScalar`` rows the templates render."""
    return [
        HeadlineScalar(label=label, value=value, is_primary=primary)
        for label, value, primary in headline_scalars(case, result)
    ]


def _build_chain_of_custody(case: Case) -> list[ChainOfCustodyEntry]:
    coc: list[ChainOfCustodyEntry] = []
    for entry in case.record.evidence.questioned:
        coc.append(
            ChainOfCustodyEntry(
                role="questioned",
                label=Path(entry.path).name,
                tokens=entry.tokens,
                sha256=entry.sha256,
            )
        )
    for entry in case.record.evidence.known:
        coc.append(
            ChainOfCustodyEntry(
                role="known",
                label=Path(entry.path).name,
                tokens=entry.tokens,
                sha256=entry.sha256,
            )
        )
    if case.record.evidence.control is not None:
        c = case.record.evidence.control
        coc.append(ChainOfCustodyEntry(role="control", label=c.corpus_id, n_docs=c.n_docs))
    return coc


def _fork_note(case: Case) -> str | None:
    parent = case.record.forked_from
    if not parent:
        return None
    note = f"Forked from case {parent.get('case_id')!r} on {parent.get('at')}."
    mismatches = parent.get("custody_mismatches") or []
    if mismatches:
        note += (
            " The source case had a chain-of-custody MISMATCH on "
            + ", ".join(str(m) for m in mismatches)
            + "; the fork was made with that mismatch explicitly acknowledged"
            + (
                f" ({parent.get('acknowledged_reason')})"
                if parent.get("acknowledged_reason")
                else ""
            )
            + "."
        )
    omitted = parent.get("omitted_missing") or []
    if omitted:
        note += " Missing from the source and not carried over: " + ", ".join(omitted) + "."
    return note


def _build_provenance_footer(case: Case, result: Result | None) -> ProvenanceFooter | None:
    if result is None or result.provenance is None:
        # No run yet — surface what the Case alone knows.
        return ProvenanceFooter(
            corpus_hash=case.record.corpus_hash,
            feature_hash=None,
            study_hash=case.record.study_hash,
            seed=0,
            bitig_version=__version__,
            spacy_model="(no run)",
        )
    p = result.provenance
    return ProvenanceFooter(
        corpus_hash=p.corpus_hash,
        feature_hash=p.feature_hash,
        study_hash=case.record.study_hash,
        seed=p.seed,
        bitig_version=p.bitig_version,
        spacy_model=p.spacy_model,
    )


def _list_figure_paths(case: Case) -> list[str]:
    if case.record.latest_run is None:
        return []
    run_dir = case.runs_dir / case.record.latest_run
    if not run_dir.is_dir():
        return []
    figures: list[Path] = []
    for ext in (".png", ".svg"):
        figures.extend(sorted(run_dir.rglob(f"*{ext}")))
    # Emit <img src=...> paths relative to report/ (../runs/<ts>/<method>/fig.png),
    # the directory draft.html / signed.html live in, so a browser opening the
    # HTML and WeasyPrint (base_url=report_dir) both resolve them (P1.8).
    # Figures must lie inside the run dir: latest_run comes from case.json.
    out: list[str] = []
    for fig in figures:
        resolved = fig.resolve()
        if not resolved.is_relative_to(run_dir.resolve()):
            continue
        out.append("../" + resolved.relative_to(case.root.resolve()).as_posix())
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_html(context: ReportContext) -> str:
    template_name = "forensic.html.j2" if context.mode == "forensic" else "research.html.j2"
    env = Environment(keep_trailing_newline=True, autoescape=True)
    source = (resources.files(_TEMPLATE_PKG) / template_name).read_text(encoding="utf-8")
    template = env.from_string(source)
    return str(template.render(**context.model_dump()))


def _export_pdf(html: str, output: Path, *, base_url: Path) -> None:
    """Render ``html`` to PDF via WeasyPrint, or surface a clear error."""
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except OSError as exc:  # native libs (pango/cairo) missing at import time
        raise ReportRendererError(f"WeasyPrint cannot load its system libraries: {exc}") from exc
    except ImportError as exc:
        raise ReportRendererError(
            "PDF export requires WeasyPrint. Install with: uv pip install 'bitig[reports]'"
        ) from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        HTML(string=html, base_url=str(base_url)).write_pdf(str(output))
    except Exception as exc:
        # errors (e.g. missing libpango/cairo system libraries) that the GUI's
        # ImportError-only handler would otherwise let escape (audit P3).
        raise ReportRendererError(f"PDF rendering failed: {exc}") from exc


def forensic_method_paragraph(result: Result | None, *, has_lr: bool) -> str:
    if result is None:
        return "(no run yet — execute the analysis to populate the findings.)"
    if has_lr:
        return (
            f"Authorship verification was performed via {result.method_name}. "
            "The likelihood ratio above expresses how much more probable the observed "
            "evidence is under H_p than under H_d, under the model's assumptions."
        )
    return (
        f"Authorship verification was performed via {result.method_name} "
        "(General Impostors; Koppel & Winter 2014). For each questioned document the "
        "score is the fraction of randomised iterations in which the candidate's known "
        "texts were closer to it than every sampled impostor author. The chance level is "
        "the score expected when style carries no authorship signal. This score is "
        "uncalibrated: it is not a likelihood ratio and no verbal (ENFSI) scale applies to it."
    )


def _research_methods_paragraph(case: Case, result: Result | None) -> str:
    method = result.method_name if result else "(no run yet)"
    return (
        f"Result derived via {method} under recipe {case.record.recipe}. "
        f"Resolved configuration is committed alongside run artefacts under "
        f"runs/{case.record.latest_run or '<run_id>'}/."
    )


def _today_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


__all__ = ["Format", "ReportRendererError", "build_case_report"]
