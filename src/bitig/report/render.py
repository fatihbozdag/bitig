"""Build an HTML or Markdown report from a directory containing saved Result artefacts."""

from __future__ import annotations

import json
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment

from bitig._version import __version__
from bitig.forensic.verbal_scale import ladder_rows, lr_from_values, lr_verbal_statement

Format = Literal["html", "md"]

_TEMPLATE_PKG = "bitig.report.templates"


def build_report(
    result_dir: str | Path,
    *,
    output: str | Path,
    format: Format = "html",
    title: str = "bitig study",
    corpus_summary: dict[str, Any] | None = None,
) -> Path:
    """Assemble `result.json` + figures in `result_dir` into a single HTML/MD file at `output`.

    `result_dir` may be either a single Result directory (one method) or a parent directory
    containing per-method subdirectories (produced by `bitig run`).
    """
    result_dir = Path(result_dir)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    results = list(_collect_results(result_dir))
    provenance = _first_provenance(results) or {}

    template_name = f"report.{format}.j2"
    env = Environment(
        keep_trailing_newline=True,
        # Autoescape every template variable when the output target is HTML, so
        # user-supplied strings (titles, corpus_summary values, config blobs) cannot
        # inject script content. Markdown output is plain text; no HTML escaping.
        autoescape=(format == "html"),
    )
    template = env.from_string(
        (resources.files(_TEMPLATE_PKG) / template_name).read_text(encoding="utf-8")
    )

    rendered = template.render(
        title=title,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        bitig_version=__version__,
        corpus_summary=corpus_summary,
        resolved_config=json.dumps(provenance.get("resolved_config", {}), indent=2),
        results=results,
        provenance=json.dumps(provenance, indent=2, default=str),
    )
    output.write_text(rendered, encoding="utf-8")
    return output


def _collect_results(result_dir: Path) -> Any:
    if (result_dir / "result.json").is_file():
        yield _load_one(result_dir)
        return
    for sub in sorted(result_dir.iterdir()):
        if sub.is_dir() and (sub / "result.json").is_file():
            yield _load_one(sub)


def _load_one(result_subdir: Path) -> dict[str, Any]:
    data = json.loads((result_subdir / "result.json").read_text(encoding="utf-8"))
    figures = [str(p.resolve()) for p in sorted(result_subdir.glob("*.png"))]
    return {
        "method_name": data.get("method_name", "unknown"),
        "params": json.dumps(data.get("params", {}), indent=2),
        "figures": figures,
        "tables": [],  # Tables are exported as parquet; embedding in report deferred to Phase 6.
        "summary": None,
        "provenance": data.get("provenance"),
    }


def _first_provenance(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    for r in results:
        if r.get("provenance"):
            return r["provenance"]  # type: ignore[no-any-return]
    return None


def _summary_lr(summary: dict[str, Any]) -> float | None:
    """Numeric LR from an ``lr_summaries`` entry (numbers or numeric strings)."""
    numeric: dict[str, float] = {}
    for key in ("lr", "log_lr"):
        try:
            numeric[key] = float(summary[key])
        except (KeyError, TypeError, ValueError):
            continue
    try:
        return lr_from_values(numeric)
    except OverflowError:
        return None


def build_forensic_report(
    result_dir: str | Path,
    *,
    output: str | Path,
    title: str = "bitig forensic report",
    lr_summaries: dict[str, dict[str, str]] | None = None,
) -> Path:
    """Render a forensic-styled report with known/questioned framing, LR output, and a
    chain-of-custody block.

    The forensic fields (``hypothesis_pair``, ``questioned_description``, ``known_description``,
    ``acquisition_notes``, ``custody_notes``, ``source_hashes``) are read from the
    ``provenance`` of the first Result in ``result_dir``. Populate them when calling
    ``Provenance.current`` from your verification pipeline.

    Parameters
    ----------
    result_dir : path
        A Result directory or a parent directory of per-method Result subdirectories.
    output : path
        Output HTML path.
    title : str
    lr_summaries : dict, optional
        Per-method LR summaries keyed by method name, e.g.,
        ``{"general_impostors": {"log_lr": "1.34", "lr": "21.9"}}``. These render under the
        relevant method section. If None, no LR block is drawn per method.
    """
    result_dir = Path(result_dir)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    results = list(_collect_results(result_dir))
    provenance = _first_provenance(results) or {}

    if lr_summaries:
        for r in results:
            summary = lr_summaries.get(r["method_name"])
            if summary:
                r["lr_summary"] = summary
                # The statement is computed from the numeric LR with the package's
                # one verbal scale (audit 2026-09-26 N-P1.12), never hand-written.
                lr = _summary_lr(summary)
                r["lr_statement"] = lr_verbal_statement(lr) if lr is not None else None

    env = Environment(keep_trailing_newline=True, autoescape=True)
    template = env.from_string(
        (resources.files(_TEMPLATE_PKG) / "forensic_lr.html.j2").read_text(encoding="utf-8")
    )
    rendered = template.render(
        title=title,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        bitig_version=__version__,
        hypothesis_pair=provenance.get("hypothesis_pair"),
        questioned_description=provenance.get("questioned_description"),
        known_description=provenance.get("known_description"),
        acquisition_notes=provenance.get("acquisition_notes"),
        custody_notes=provenance.get("custody_notes"),
        source_hashes=provenance.get("source_hashes") or {},
        results=results,
        ladder_rows=ladder_rows(),
        provenance=json.dumps(provenance, indent=2, default=str),
    )
    output.write_text(rendered, encoding="utf-8")
    return output
