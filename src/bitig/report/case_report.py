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
from bitig.forensic.verbal_scale import ladder_rows, lr_from_values, lr_verbal_rung
from bitig.report.context import (
    ChainOfCustodyEntry,
    HeadlineScalar,
    ProvenanceFooter,
    ReportContext,
)
from bitig.report.scalars import fmt_scalar, headline_scalars, load_latest_result
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

    if signed_html.is_file():
        # Sealed — serve the immutable snapshot verbatim, never re-render.
        html = signed_html.read_text(encoding="utf-8")
        report_path = signed_html
    else:
        context = _build_context(case)
        html = _render_html(context)
        draft_path.write_text(html, encoding="utf-8")
        report_path = draft_path

    if format == "html":
        return report_path

    # PDF path. base_url is the CASE ROOT because _list_figure_paths emits
    # figure src paths relative to the case root (runs/<ts>/.../fig.png), not
    # relative to report_dir (audit P1.8).
    out_pdf = output_path if output_path is not None else case.report_dir / "final.pdf"
    _export_pdf(html, out_pdf, base_url=case.root)
    return out_pdf


# ---------------------------------------------------------------------------
# Context construction
# ---------------------------------------------------------------------------


def _build_context(case: Case) -> ReportContext:
    result = load_latest_result(case)
    scalars = _build_headline_scalars(case, result)
    coc = _build_chain_of_custody(case)
    provenance = _build_provenance_footer(case, result)
    figures = _list_figure_paths(case)
    case_state_hash = case._case_state_hash()
    date_iso = _today_iso()

    if case.record.mode == "forensic":
        # The verbal rung is classified from the RAW LR float, never from the
        # display-rounded string (audit P1.11). lr_value/ladder are populated
        # only when a calibrated LR actually exists (audit P1.10).
        lr = lr_from_values(result.values) if result is not None else None
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
            provenance=provenance,
            signed=case.record.signed,
            signed_at=case.record.signed_at,
            signed_by=case.record.signed_by,
            hypothesis_p="The questioned text and the known texts share an author.",
            hypothesis_d="The questioned text and the known texts do not share an author.",
            lr_value=fmt_scalar(lr) if lr is not None else None,
            lr_verbal_rung=lr_verbal_rung(lr) if lr is not None else None,
            lr_ladder_rows=ladder_rows() if lr is not None else [],
            method_paragraph=_forensic_method_paragraph(result),
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
    # Emit <img src=...> paths relative to the CASE ROOT (e.g.
    # runs/<ts>/<method>/fig.png). build_case_report passes base_url=case.root
    # so WeasyPrint and a browser opening the HTML both resolve them (P1.8).
    out: list[str] = []
    for fig in figures:
        try:
            rel = fig.relative_to(case.root)
        except ValueError:
            rel = fig
        out.append(rel.as_posix() if isinstance(rel, Path) else str(rel))
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
    except ImportError as exc:
        raise ReportRendererError(
            "PDF export requires WeasyPrint. Install with: uv pip install 'bitig[reports]'"
        ) from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(base_url)).write_pdf(str(output))


def _forensic_method_paragraph(result: Result | None) -> str:
    if result is None:
        return "(no run yet — execute Step 3 to populate the LR.)"
    return (
        f"Authorship verification was performed via {result.method_name}. "
        "The likelihood ratio above expresses how much more probable the observed "
        "evidence is under H_p than under H_d, under the model's assumptions."
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
