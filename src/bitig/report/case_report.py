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
from bitig.report.context import (
    ChainOfCustodyEntry,
    HeadlineScalar,
    ProvenanceFooter,
    ReportContext,
)
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

    HTML is always written to ``case.report_dir / "draft.html"`` (the
    spec's working draft file). When ``format == "pdf"``, the same HTML
    is rendered to a PDF at ``output_path`` (default
    ``case.report_dir / "final.pdf"``) via WeasyPrint.

    Raises :exc:`ReportRendererError` if WeasyPrint isn't installed when
    a PDF is requested.
    """
    context = _build_context(case)
    html = _render_html(context)

    draft_path = case.report_dir / "draft.html"
    case.report_dir.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(html, encoding="utf-8")

    if format == "html":
        return draft_path

    # PDF path
    out_pdf = output_path if output_path is not None else case.report_dir / "final.pdf"
    _export_pdf(html, out_pdf, base_url=case.report_dir)
    return out_pdf


# ---------------------------------------------------------------------------
# Context construction
# ---------------------------------------------------------------------------


def _build_context(case: Case) -> ReportContext:
    result = _load_latest_result(case)
    scalars = _build_headline_scalars(case, result)
    coc = _build_chain_of_custody(case)
    provenance = _build_provenance_footer(case, result)
    figures = _list_figure_paths(case)
    case_state_hash = case._case_state_hash()
    date_iso = _today_iso()

    if case.record.mode == "forensic":
        lr_value = scalars[0].value if scalars and scalars[0].label == "LR" else None
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
            lr_value=lr_value,
            lr_verbal_rung=_verbal_rung_for_value(lr_value),
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


def _load_latest_result(case: Case) -> Result | None:
    """Inline copy of the GUI helper so the renderer has no GUI dep."""
    if case.record.latest_run is None:
        return None
    run_dir = case.runs_dir / case.record.latest_run
    if not run_dir.is_dir():
        return None
    for method_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        candidate = method_dir / "result.json"
        if candidate.is_file():
            try:
                return Result.from_json(candidate)
            except Exception:
                return None
    return None


def _build_headline_scalars(case: Case, result: Result | None) -> list[HeadlineScalar]:
    if result is None:
        return [HeadlineScalar(label="status", value="no run yet", is_primary=True)]

    v = result.values
    if case.record.mode == "forensic":
        out: list[HeadlineScalar] = []
        if "lr" in v:
            out.append(HeadlineScalar(label="LR", value=_fmt(v["lr"]), is_primary=True))
        elif "log_lr" in v:
            out.append(HeadlineScalar(label="log LR", value=_fmt(v["log_lr"]), is_primary=True))
        for key, label in (("auc", "AUC"), ("c_at_1", "c@1"), ("cllr", "C_llr")):
            if key in v:
                out.append(HeadlineScalar(label=label, value=_fmt(v[key])))
        if not out:
            out.append(
                HeadlineScalar(
                    label="score", value=_fmt(next(iter(v.values()), "—")), is_primary=True
                )
            )
        return out

    # research
    method = result.method_name
    if method == "pca":
        evr = v.get("explained_variance_ratio")
        if evr is not None and hasattr(evr, "__len__") and len(evr) >= 1:
            scalars = [HeadlineScalar(label="PC1 var", value=_fmt(evr[0]), is_primary=True)]
            if len(evr) >= 2:
                scalars.append(HeadlineScalar(label="PC2 var", value=_fmt(evr[1])))
                scalars.append(HeadlineScalar(label="cum.", value=_fmt(sum(evr[:2]))))
            return scalars
    if method in {"classify", "classification"}:
        out = []
        for key, label in (("accuracy", "accuracy"), ("macro_f1", "macro-F1"), ("ece", "ECE")):
            if key in v:
                out.append(HeadlineScalar(label=label, value=_fmt(v[key]), is_primary=not out))
        if out:
            return out
    if method in {"bayesian", "bayes"} and "posterior_mode" in v:
        return [
            HeadlineScalar(label="posterior mode", value=str(v["posterior_mode"]), is_primary=True)
        ]
    return [HeadlineScalar(label="method", value=method, is_primary=True)]


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
    # Templates resolve <img src=...> relative to the report_dir, so we
    # output paths *relative to that directory* (which is a sibling of
    # runs/).
    out: list[str] = []
    for fig in figures:
        try:
            rel = fig.relative_to(case.report_dir.parent)
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


def _fmt(value: object) -> str:
    """Same compact numeric formatter the GUI helpers use."""
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    if x == 0:
        return "0"
    if abs(x) >= 1e4 or abs(x) < 1e-3:
        return f"{x:.2e}"
    return f"{x:.3g}"


def _verbal_rung_for_value(lr_value: str | None) -> str | None:
    if lr_value is None:
        return None
    try:
        lr = float(lr_value)
    except ValueError:
        # Scientific notation already; parse it.
        try:
            lr = float(lr_value.replace("e", "E"))
        except ValueError:
            return None
    if lr < 1:
        return "no support"
    if lr < 10:
        return "weak support"
    if lr < 100:
        return "moderate support"
    if lr < 1000:
        return "strong support"
    if lr < 10000:
        return "very strong support"
    return "extremely strong support"


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
