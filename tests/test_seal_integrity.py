"""Seal integrity regressions (audit 2026-09-26 N-P1.2, N-P1.3, N-P1.5, N-P1.6, N-P1.7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bitig.case_run import perform_run
from bitig.cases import Case, CaseError
from bitig.report.case_report import ReportRendererError, build_case_report
from tests._signable import make_signable

_MINI = Path(__file__).parent / "fixtures" / "mini_corpus"


def _run_case(tmp_path: Path) -> Case:
    """A real exploration case with a successful run (figures included)."""
    case = Case.create(tmp_path / "cases", id="c", title="t", examiner="x", recipe="exploration")
    case.add_evidence(_MINI / "alice_one.txt", role="known", author="Alice")
    case.add_evidence(_MINI / "alice_two.txt", role="known", author="Alice")
    case.add_evidence(_MINI / "bob_one.txt", role="known", author="Bob")
    outcome = perform_run(case)
    assert outcome.status == "succeeded", outcome.message
    return case


def _check(case: Case, name: str):
    return next(c for c in case.verify_seal().checks if c.name == name)


# -- N-P1.2 / N-P1.7: signing preconditions -----------------------------------


def test_sign_refused_without_evidence_or_run(tmp_path: Path) -> None:
    case = Case.create(tmp_path / "cases", id="c", title="t", examiner="x", recipe="exploration")
    with pytest.raises(CaseError, match="No evidence"):
        case.mark_signed()
    assert not case.record.signed


def test_sign_refused_when_case_changed_after_run(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.add_evidence(_MINI / "bob_two.txt", role="known", author="Bob")
    with pytest.raises(CaseError, match="re-run"):
        case.mark_signed()
    # Re-running on the new state makes it signable again.
    assert perform_run(case).status == "succeeded"
    case.mark_signed()
    assert case.verify_seal().ok


def test_sign_refused_on_custody_mismatch_through_the_api(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    (case.evidence_dir / "known" / "bob_one.txt").write_text("doctored", encoding="utf-8")
    with pytest.raises(CaseError, match="custody"):
        case.mark_signed()


def test_sign_refused_when_study_yaml_edited(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    with case.study_yaml_path.open("a", encoding="utf-8") as fh:
        fh.write("\n# edited\n")
    with pytest.raises(CaseError, match=r"study\.yaml"):
        case.mark_signed()


def test_register_run_refused_on_signed_case(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.mark_signed()
    (case.runs_dir / "later").mkdir()
    with pytest.raises(CaseError, match="signed"):
        case.register_run("later")


def test_load_rejects_traversing_latest_run(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    data = json.loads(case.case_json_path.read_text(encoding="utf-8"))
    data["latest_run"] = "../../outside"
    case.case_json_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CaseError, match="Invalid"):
        Case.load(case.root)


# -- N-P1.3: a failed sign leaves nothing behind ------------------------------


class _Boom:
    id = "boom"

    def sign(self, payload, *, case):
        raise RuntimeError("plugin failure")


@pytest.mark.parametrize("exc", [RuntimeError, KeyboardInterrupt])
def test_failed_sign_rolls_back_completely(tmp_path: Path, monkeypatch, exc) -> None:
    case = _run_case(tmp_path)

    def boom(payload, *, case):
        raise exc("interrupted")

    plugin = _Boom()
    monkeypatch.setattr(plugin, "sign", boom)
    with pytest.raises(exc):
        case.mark_signed(signed_by="Alice", signature_plugin=plugin)

    reloaded = Case.load(case.root)
    assert not reloaded.record.signed
    assert not (case.report_dir / "signed.html").exists()
    assert not (case.report_dir / "signed.json").exists()
    assert not list(case.report_dir.glob(".signed*"))  # no temp files left
    html = build_case_report(reloaded, format="html").read_text(encoding="utf-8")
    assert "draft · not signed" in html


def test_stray_signed_html_is_not_served_for_unsigned_case(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.report_dir.mkdir(parents=True, exist_ok=True)
    (case.report_dir / "signed.html").write_text("<html>STALE SIGNED</html>", encoding="utf-8")
    out = build_case_report(case, format="html")
    assert out.name == "draft.html"
    assert "STALE" not in out.read_text(encoding="utf-8")


# -- N-P1.5: run outputs are sealed -------------------------------------------


def test_swapping_a_figure_after_signing_breaks_the_seal(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.mark_signed()
    assert case.verify_seal().ok
    figures = sorted((case.runs_dir / str(case.record.latest_run)).rglob("*.png"))
    assert figures, "exploration run should emit figures"
    figures[0].write_bytes(b"forged png")
    check = _check(case, "run_outputs")
    assert not check.ok and figures[0].name in check.detail


def test_editing_result_json_after_signing_breaks_the_seal(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.mark_signed()
    result_json = next((case.runs_dir / str(case.record.latest_run)).rglob("result.json"))
    result_json.write_text(result_json.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert not _check(case, "run_outputs").ok


def test_legacy_seal_without_run_manifest_fails_with_clear_label(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.mark_signed()
    signed_json = case.report_dir / "signed.json"
    payload = json.loads(signed_json.read_text(encoding="utf-8"))
    payload.pop("run_manifest")
    signed_json.write_text(json.dumps(payload), encoding="utf-8")
    check = _check(case, "run_outputs")
    assert not check.ok and "legacy seal" in check.detail


def test_report_figure_paths_resolve_from_report_dir(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    html = build_case_report(case, format="html").read_text(encoding="utf-8")
    srcs = [part.split('"', 1)[0] for part in html.split('src="')[1:]]
    figures = [s for s in srcs if s.endswith(".png")]
    assert figures
    for src in figures:
        assert src.startswith("../runs/")
        assert (case.report_dir / src).is_file()


# -- N-P1.6: export respects the seal -----------------------------------------


def test_export_refuses_signed_case_without_signed_html(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.mark_signed()
    (case.report_dir / "signed.html").unlink()
    with pytest.raises(ReportRendererError, match="missing"):
        build_case_report(case, format="html")


def test_export_refuses_signed_case_with_altered_results(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.mark_signed()
    result_json = next((case.runs_dir / str(case.record.latest_run)).rglob("result.json"))
    result_json.write_text("{}", encoding="utf-8")
    with pytest.raises(ReportRendererError, match="run_outputs"):
        build_case_report(case, format="html")


def test_make_signable_helper_still_signs(tmp_path: Path) -> None:
    case = Case.create(tmp_path / "cases", id="h", title="t", examiner="x", recipe="exploration")
    make_signable(case).mark_signed()
    assert case.verify_seal().ok
