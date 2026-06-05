"""Tests for the Case-aware report renderer (spec §7 step 6)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bitig.cases import Case
from bitig.provenance import Provenance
from bitig.report.case_report import (
    ReportRendererError,
    build_case_report,
)
from bitig.report.context import ReportContext
from bitig.result import Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_text(path: Path, content: str = "sample text here") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _seed_case(tmp_path: Path, *, recipe: str, mode_label: str) -> Case:
    """Create a Case with evidence + a fake run, ready to render."""
    cases_dir = tmp_path / "cases"
    case = Case.create(
        cases_dir,
        id=f"{mode_label}-case",
        title=f"{mode_label.capitalize()} test case",
        examiner="F. Bozdağ",
        recipe=recipe,
    )
    case.add_evidence(_make_text(tmp_path / "q.txt", "questioned text"), role="questioned")
    case.add_evidence(_make_text(tmp_path / "k.txt", "known text"), role="known", author="Doe")
    if recipe == "imposters_lr":
        case.set_control_corpus("BUMR-AT-2024", n_docs=240)
    return case


def _attach_run(case: Case, *, method_name: str, values: dict[str, object]) -> str:
    """Drop a fake result.json under runs/<id>/<method>/ and register it."""
    run_id = "2026-05-17T12-00-00Z"
    method_dir = case.runs_dir / run_id / method_name
    method_dir.mkdir(parents=True)
    result = Result(
        method_name=method_name,
        values=values,
        provenance=Provenance(
            bitig_version="0.1.1",
            python_version="3.11",
            spacy_model="en_core_web_trf",
            spacy_version="3.7",
            corpus_hash="ffeeddccbbaa00112233",
            feature_hash="abcdef1234567890",
            seed=42,
            timestamp=datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC),
            resolved_config={},
        ),
    )
    result.to_json(method_dir / "result.json")
    case.register_run(run_id)
    return run_id


# ---------------------------------------------------------------------------
# Forensic layout
# ---------------------------------------------------------------------------


def test_forensic_report_renders_lr_and_verbal_rung(tmp_path: Path) -> None:
    case = _seed_case(tmp_path, recipe="imposters_lr", mode_label="forensic")
    _attach_run(
        case,
        method_name="verify",
        values={"lr": 250.0, "auc": 0.91, "c_at_1": 0.84, "cllr": 0.22},
    )

    draft = build_case_report(case, format="html")
    assert draft.name == "draft.html"
    html = draft.read_text(encoding="utf-8")

    # Headline LR + verbal scale rung
    assert "LR" in html
    assert "250" in html
    assert "strong support" in html  # LR=250 → strong (100-1000)
    # Hypotheses block
    assert "prosecution" in html
    assert "defence" in html
    # Chain of custody surfaces the evidence files
    assert "q.txt" in html
    assert "k.txt" in html
    assert "BUMR-AT-2024" in html
    # Provenance footer
    assert "spaCy" in html
    assert "seed=42" in html


def test_forensic_report_handles_no_run(tmp_path: Path) -> None:
    case = _seed_case(tmp_path, recipe="imposters_lr", mode_label="forensic-empty")
    draft = build_case_report(case, format="html")
    html = draft.read_text(encoding="utf-8")
    # Headline strip falls back to a placeholder; no LR card.
    assert "no run yet" in html
    # Hypotheses still present (those are intrinsic to forensic mode).
    assert "prosecution" in html


# ---------------------------------------------------------------------------
# Research layout
# ---------------------------------------------------------------------------


def test_research_report_renders_pca_variance(tmp_path: Path) -> None:
    import numpy as np

    case = _seed_case(tmp_path, recipe="exploration", mode_label="research")
    _attach_run(
        case,
        method_name="pca",
        values={"explained_variance_ratio": np.array([0.6, 0.25, 0.1])},
    )

    draft = build_case_report(case, format="html")
    html = draft.read_text(encoding="utf-8")

    assert "Research question" in html
    assert "exploration" in html
    assert "PC1 var" in html
    # research layout has no LR / hypotheses block
    assert "Likelihood ratio" not in html
    assert "prosecution" not in html
    # Data availability stub is rendered
    assert "Data availability" in html


def test_research_report_falls_back_when_no_run(tmp_path: Path) -> None:
    case = _seed_case(tmp_path, recipe="delta_attribution", mode_label="research-empty")
    draft = build_case_report(case, format="html")
    html = draft.read_text(encoding="utf-8")
    assert "no run yet" in html
    assert "Research question" in html


# ---------------------------------------------------------------------------
# Signed-state toolbar
# ---------------------------------------------------------------------------


def test_signed_case_toolbar_shows_signed_badge(tmp_path: Path) -> None:
    case = _seed_case(tmp_path, recipe="imposters_lr", mode_label="signed-forensic")
    _attach_run(case, method_name="verify", values={"lr": 5.0})
    case.mark_signed()

    draft = build_case_report(case, format="html")
    html = draft.read_text(encoding="utf-8")
    assert "SIGNED" in html
    assert "draft · not signed" not in html


def test_unsigned_case_toolbar_shows_draft_badge(tmp_path: Path) -> None:
    case = _seed_case(tmp_path, recipe="exploration", mode_label="unsigned")
    draft = build_case_report(case, format="html")
    html = draft.read_text(encoding="utf-8")
    assert "draft · not signed" in html


# ---------------------------------------------------------------------------
# Frozen report + figure paths (audit P1.7, P1.8)
# ---------------------------------------------------------------------------


def test_build_on_signed_case_serves_frozen_snapshot(tmp_path: Path) -> None:
    """build_case_report on a signed case returns the immutable signed.html and
    never rewrites draft.html (audit P1.7)."""
    case = _seed_case(tmp_path, recipe="imposters_lr", mode_label="frozen")
    _attach_run(case, method_name="verify", values={"lr": 5.0})
    case.mark_signed()

    signed_html = case.report_dir / "signed.html"
    frozen_bytes = signed_html.read_bytes()
    draft_before = (case.report_dir / "draft.html").read_bytes()

    out = build_case_report(case, format="html")
    assert out == signed_html
    # Serving the frozen report must not mutate either artefact.
    assert signed_html.read_bytes() == frozen_bytes
    assert (case.report_dir / "draft.html").read_bytes() == draft_before
    # And the seal still verifies.
    assert case.verify_seal().ok


def test_forensic_rung_classified_from_raw_lr_not_rounded(tmp_path: Path) -> None:
    """The verbal rung must come from the RAW LR float, not the rounded display
    string (audit P1.11): LR=0.9999 displays as "1" but is "no support", not
    the "weak support" the old round-then-classify produced."""
    from bitig.report.case_report import _build_context

    case = _seed_case(tmp_path, recipe="imposters_lr", mode_label="rung")
    _attach_run(case, method_name="verify", values={"lr": 0.9999})
    ctx = _build_context(case)

    assert ctx.lr_value == "1"  # display rounds up...
    assert ctx.lr_verbal_rung == "no support"  # ...but the rung uses the raw float
    assert ctx.lr_ladder_rows  # ladder present for a real LR


def test_forensic_gi_result_has_no_lr_or_ladder(tmp_path: Path) -> None:
    """An uncalibrated GI win-fraction is not an LR: no LR value, no ladder, and
    the headline shows the GI score (a number), not the candidate name (P1.10)."""
    from bitig.report.case_report import _build_context

    case = _seed_case(tmp_path, recipe="imposters_lr", mode_label="gi")
    _attach_run(
        case,
        method_name="verify",
        values={"candidate": "suspect_A", "scores": {"suspect_A": 0.83}},
    )
    ctx = _build_context(case)

    assert ctx.lr_value is None
    assert ctx.lr_verbal_rung is None
    assert ctx.lr_ladder_rows == []
    assert ctx.headline_scalars[0].label == "GI score"
    assert "suspect_A" not in ctx.headline_scalars[0].value


def test_figure_paths_are_case_root_relative(tmp_path: Path) -> None:
    """Figure <img src> paths resolve against the case root, matching the
    base_url build_case_report passes to WeasyPrint (audit P1.8)."""
    case = _seed_case(tmp_path, recipe="exploration", mode_label="figs")
    run_id = _attach_run(case, method_name="pca", values={"explained_variance_ratio": [0.6, 0.3]})
    fig = case.runs_dir / run_id / "pca" / "scatter.png"
    fig.write_bytes(b"\x89PNG\r\n\x1a\n stub")

    html = build_case_report(case, format="html").read_text(encoding="utf-8")
    expected = f"runs/{run_id}/pca/scatter.png"
    assert expected in html
    # The path must resolve from the case root (where base_url points).
    assert (case.root / expected).is_file()


# ---------------------------------------------------------------------------
# ReportContext validation
# ---------------------------------------------------------------------------


def test_report_context_rejects_unknown_field() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReportContext(
            mode="forensic",
            title="t",
            case_id="c",
            examiner="x",
            date_iso="2026-05-17",
            bitig_version="0.1.1",
            case_state_hash="abc",
            unknown_thing=42,  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# PDF export — only when WeasyPrint is available
# ---------------------------------------------------------------------------


def _has_weasyprint() -> bool:
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not _has_weasyprint(), reason="WeasyPrint not installed")
def test_pdf_export_writes_pdf(tmp_path: Path) -> None:
    case = _seed_case(tmp_path, recipe="imposters_lr", mode_label="pdf-test")
    _attach_run(case, method_name="verify", values={"lr": 5.0})

    pdf = build_case_report(case, format="pdf")
    assert pdf.name == "final.pdf"
    assert pdf.is_file()
    assert pdf.stat().st_size > 1000  # rough sanity floor


def test_pdf_export_error_when_weasyprint_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate a missing WeasyPrint by patching the import inside the renderer.

    Avoids depending on the test environment's package set.
    """
    import bitig.report.case_report as cr

    def _raise_export(*_args, **_kwargs):
        raise ReportRendererError(
            "PDF export requires WeasyPrint. Install with: uv pip install 'bitig[reports]'"
        )

    monkeypatch.setattr(cr, "_export_pdf", _raise_export)

    case = _seed_case(tmp_path, recipe="imposters_lr", mode_label="pdf-fail")
    _attach_run(case, method_name="verify", values={"lr": 5.0})

    with pytest.raises(ReportRendererError, match="WeasyPrint"):
        build_case_report(case, format="pdf")
