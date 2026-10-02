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


# -- Re-acknowledge (sealed custody log) --------------------------------------


def _changed(tmp_path: Path) -> Case:
    case = _run_case(tmp_path)
    (case.evidence_dir / "known" / "bob_one.txt").write_text("re-exported text", encoding="utf-8")
    return case


def test_reacknowledge_requires_a_reason(tmp_path: Path) -> None:
    case = _changed(tmp_path)
    with pytest.raises(CaseError, match="reason"):
        case.reacknowledge_evidence("evidence/known/bob_one.txt", reason="  ")


def test_reacknowledge_records_log_and_requires_rerun(tmp_path: Path) -> None:
    case = _changed(tmp_path)
    old = next(e.sha256 for e in case.record.evidence.known if e.path.endswith("bob_one.txt"))
    log = case.reacknowledge_evidence(
        "evidence/known/bob_one.txt", reason="re-exported as UTF-8", by="Examiner B"
    )
    assert log["old_sha256"] == old
    assert log["by"] == "Examiner B"
    assert case.verify_custody() == []

    reloaded = Case.load(case.root)
    assert reloaded.record.custody_log == [log]
    # The case state changed, so the earlier run can no longer be signed.
    with pytest.raises(CaseError, match="re-run"):
        reloaded.mark_signed()
    assert perform_run(reloaded).status == "succeeded"
    reloaded.mark_signed()
    assert reloaded.verify_seal().ok
    html = (reloaded.report_dir / "signed.html").read_text(encoding="utf-8")
    assert "re-exported as UTF-8" in html and "Examiner B" in html


def test_custody_log_is_sealed(tmp_path: Path) -> None:
    case = _changed(tmp_path)
    case.reacknowledge_evidence("evidence/known/bob_one.txt", reason="legit")
    assert perform_run(case).status == "succeeded"
    case.mark_signed()
    data = json.loads(case.case_json_path.read_text(encoding="utf-8"))
    data["custody_log"][0]["reason"] = "edited after signing"
    case.case_json_path.write_text(json.dumps(data), encoding="utf-8")
    assert not _check(Case.load(case.root), "case_state_hash").ok


def test_reacknowledge_rejects_missing_unchanged_and_unregistered(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    with pytest.raises(CaseError, match="unchanged"):
        case.reacknowledge_evidence("evidence/known/bob_one.txt", reason="r")
    with pytest.raises(CaseError, match="registered"):
        case.reacknowledge_evidence("evidence/known/nope.txt", reason="r")
    (case.evidence_dir / "known" / "bob_one.txt").unlink()
    with pytest.raises(CaseError, match="Fork"):
        case.reacknowledge_evidence("evidence/known/bob_one.txt", reason="r")


def test_reacknowledge_refused_on_signed_case(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.mark_signed()
    with pytest.raises(CaseError, match="signed"):
        case.reacknowledge_evidence("evidence/known/bob_one.txt", reason="r")


# -- N-P1.4: fork cannot launder tampered evidence ----------------------------


def test_fork_refuses_tampered_source(tmp_path: Path) -> None:
    from bitig.cases import fork_case

    case = _changed(tmp_path)
    with pytest.raises(CaseError, match="mismatch"):
        fork_case(case.root, "f1")
    assert not (case.root.parent / "f1").exists()


def test_acknowledged_fork_records_the_mismatch(tmp_path: Path) -> None:
    from bitig.cases import fork_case

    case = _changed(tmp_path)
    fork = fork_case(case.root, "f2", acknowledge_mismatch="source file re-exported by lab")
    parent = fork.record.forked_from
    assert parent is not None
    assert parent["case_id"] == "c"
    assert parent["custody_mismatches"] == ["evidence/known/bob_one.txt"]
    assert parent["acknowledged_reason"] == "source file re-exported by lab"
    registered = {e["path"]: e["sha256"] for e in parent["evidence"]}
    assert registered["evidence/known/bob_one.txt"] != next(
        e.sha256 for e in fork.record.evidence.known if e.path.endswith("bob_one.txt")
    )
    assert perform_run(fork).status == "succeeded"
    fork.mark_signed()
    html = (fork.report_dir / "signed.html").read_text(encoding="utf-8")
    assert "MISMATCH" in html and "re-exported by lab" in html


def test_acknowledged_fork_omits_missing_files(tmp_path: Path) -> None:
    from bitig.cases import fork_case

    case = _run_case(tmp_path)
    (case.evidence_dir / "known" / "bob_one.txt").unlink()
    fork = fork_case(case.root, "f3", acknowledge_mismatch="file lost")
    assert fork.record.forked_from["omitted_missing"] == ["evidence/known/bob_one.txt"]
    assert not any(e.path.endswith("bob_one.txt") for e in fork.record.evidence.known)


def test_clean_fork_records_parent(tmp_path: Path) -> None:
    from bitig.cases import fork_case

    case = _run_case(tmp_path)
    fork = fork_case(case.root, "f4")
    assert fork.record.forked_from["case_id"] == "c"
    assert fork.record.forked_from["custody_mismatches"] == []


def test_cli_fork_rejects_traversal_source_id(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from bitig.cli import app

    outside = tmp_path / "outside"
    Case.create(outside, id="victim", title="t", examiner="x", recipe="exploration")
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    result = CliRunner().invoke(
        app, ["case", "fork", "../outside/victim", "newc", "--cases-dir", str(cases_dir)]
    )
    assert result.exit_code == 1
    assert not (outside / "newc").exists()


# -- N-P1.7: evidence must be registered; strays are flagged ------------------


def _cli(*args: str):
    from typer.testing import CliRunner

    from bitig.cli import app

    return CliRunner().invoke(app, list(args))


def test_cli_dropped_file_is_flagged_and_case_cannot_be_signed(tmp_path: Path) -> None:
    cases = str(tmp_path / "cases")
    assert (
        _cli("case", "new", "c2", "--title", "T", "--examiner", "E", "--cases-dir", cases).exit_code
        == 0
    )
    dropped = tmp_path / "cases" / "c2" / "evidence" / "questioned" / "fed.txt"
    dropped.parent.mkdir(parents=True, exist_ok=True)
    dropped.write_text("dropped by hand", encoding="utf-8")

    status = _cli("case", "status", "c2", "--cases-dir", cases)
    assert "unregistered" in status.output and "fed.txt" in status.output
    sign = _cli("case", "sign", "c2", "--cases-dir", cases)
    assert sign.exit_code == 1 and "No evidence" in sign.output


def test_cli_add_evidence_registers_files(tmp_path: Path) -> None:
    cases = str(tmp_path / "cases")
    _cli("case", "new", "c3", "--title", "T", "--examiner", "E", "--cases-dir", cases)
    ok = _cli(
        "case",
        "add-evidence",
        "c3",
        str(_MINI / "alice_one.txt"),
        str(_MINI / "alice_two.txt"),
        "--role",
        "known",
        "--author",
        "Alice",
        "--cases-dir",
        cases,
    )
    assert ok.exit_code == 0, ok.output
    case = Case.load(tmp_path / "cases" / "c3")
    assert [e.author for e in case.record.evidence.known] == ["Alice", "Alice"]
    no_author = _cli(
        "case",
        "add-evidence",
        "c3",
        str(_MINI / "bob_one.txt"),
        "--role",
        "known",
        "--cases-dir",
        cases,
    )
    assert no_author.exit_code == 1


def test_file_dropped_after_signing_fails_verify(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.mark_signed()
    (case.evidence_dir / "known" / "late.txt").write_text("added later", encoding="utf-8")
    check = _check(case, "unregistered_files")
    assert not check.ok and "late.txt" in check.detail


# -- Stale handles (lost update) ----------------------------------------------


def test_stale_handle_cannot_unsign_a_case(tmp_path: Path) -> None:
    """GUI run page holds a handle through a long run while the case is signed
    elsewhere; its register_run save() used to write signed=False back."""
    case = _run_case(tmp_path)
    stale = Case.load(case.root)
    Case.load(case.root).mark_signed()
    (case.runs_dir / "later").mkdir()
    with pytest.raises(CaseError, match="changed by another"):
        stale.register_run("later")
    assert Case.load(case.root).record.signed


def test_stale_handle_cannot_drop_evidence_registered_elsewhere(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    stale = Case.load(case.root)
    Case.load(case.root).add_evidence(_MINI / "bob_two.txt", role="known", author="Bob")
    with pytest.raises(CaseError, match="changed by another"):
        stale.set_param("seed", 7)
    assert any(e.path.endswith("bob_two.txt") for e in Case.load(case.root).record.evidence.known)


# -- Listing and control corpus -----------------------------------------------


def test_one_bad_case_does_not_break_listing(tmp_path: Path) -> None:
    from bitig.cases import list_cases, scan_cases

    root = tmp_path / "cases"
    Case.create(root, id="good", title="t", examiner="x", recipe="exploration")
    (root / "bad").mkdir()
    (root / "bad" / "case.json").write_text("{}", encoding="utf-8")
    cases, problems = scan_cases(root)
    assert [c.record.id for c in cases] == ["good"]
    assert problems and problems[0][0].name == "bad"
    assert [c.record.id for c in list_cases(root)] == ["good"]
    result = _cli("case", "list", "--cases-dir", str(root))
    assert result.exit_code == 0 and "unreadable case" in result.output and "good" in result.output


def test_report_says_control_corpus_is_not_used(tmp_path: Path) -> None:
    case = _run_case(tmp_path)
    case.set_control_corpus("BUMR", n_docs=10)
    html = build_case_report(case).read_text(encoding="utf-8")
    assert "BUMR" in html and "not used by the analysis" in html


def test_seal_status_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """status separates broken from unverifiable and unsigned (audit 2026-09-26 follow-up)."""
    from bitig.signatures import HmacSignaturePlugin

    monkeypatch.delenv("BITIG_SIGNATURE_KEY", raising=False)
    null_case = make_signable(
        Case.create(tmp_path / "cases", id="n", title="t", examiner="x", recipe="exploration")
    )
    null_case.mark_signed()
    assert null_case.verify_seal().status == "unsigned"
    monkeypatch.setenv("BITIG_SIGNATURE_KEY", "k")
    assert null_case.verify_seal().status == "unsigned"
    assert null_case.verify_seal(signature_key="k").status == "broken"

    hmac_case = make_signable(
        Case.create(tmp_path / "cases", id="h", title="t", examiner="x", recipe="exploration")
    )
    hmac_case.mark_signed(signature_plugin=HmacSignaturePlugin(key="k"))
    assert hmac_case.verify_seal().status == "verified"
    monkeypatch.delenv("BITIG_SIGNATURE_KEY")
    assert hmac_case.verify_seal().status == "unverifiable"
    assert not hmac_case.verify_seal().ok
    assert hmac_case.verify_seal(signature_key="wrong").status == "broken"


def test_stale_handle_cannot_overwrite_another_handles_seal(tmp_path: Path) -> None:
    """Handle A loaded before B signed must not replace (then delete) B's seal files."""
    root = make_signable(
        Case.create(tmp_path / "cases", id="s", title="t", examiner="x", recipe="exploration")
    ).root
    a = Case.load(root)
    b = Case.load(root)
    b.mark_signed()
    sealed = (root / "report" / "signed.json").read_bytes()

    with pytest.raises(CaseError, match="changed by another handle"):
        a.mark_signed()
    assert (root / "report" / "signed.json").read_bytes() == sealed
    assert Case.load(root).verify_seal().status == "unsigned"


def test_scheme1_hmac_seal_does_not_trust_a_run_manifest(tmp_path: Path) -> None:
    """A scheme-1 HMAC does not cover run_manifest, so the manifest is not evidence."""
    case = make_signable(
        Case.create(tmp_path / "cases", id="l", title="t", examiner="x", recipe="exploration")
    )
    payload = {
        "latest_run": case.record.latest_run,
        "run_manifest": case._run_manifest(),
        "signature": {"scheme": 1},
    }
    check = case._run_outputs_check(payload)
    assert not check.ok and "legacy seal" in check.detail
    payload["signature"] = {"scheme": 2}
    assert case._run_outputs_check(payload).ok


def test_duplicate_document_ids_in_legacy_evidence_are_refused(tmp_path: Path) -> None:
    import dataclasses

    case = make_signable(
        Case.create(tmp_path / "cases", id="d", title="t", examiner="x", recipe="exploration")
    )
    known = case.record.evidence.known[0]
    case.record.evidence.questioned.append(dataclasses.replace(known, role="questioned"))
    with pytest.raises(CaseError, match="share a document id"):
        case.build_corpus()
