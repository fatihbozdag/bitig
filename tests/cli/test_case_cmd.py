"""Tests for ``bitig case [new|open|list|status|fork|sign]``."""

from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from bitig.cases import Case
from bitig.cli import app

# Rich wraps long lines at the detected terminal width and CliRunner emulates
# a narrow terminal; force a wide one so paths and table rows survive intact
# (same trick used elsewhere in this repo for help-text tests).
os.environ.setdefault("COLUMNS", "200")

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new(
    cases_dir: Path,
    case_id: str = "alpha",
    *,
    recipe: str = "imposters_lr",
    title: str = "Test case",
    examiner: str = "F. Bozdağ",
) -> None:
    result = runner.invoke(
        app,
        [
            "case",
            "new",
            case_id,
            "--title",
            title,
            "--examiner",
            examiner,
            "--recipe",
            recipe,
            "--cases-dir",
            str(cases_dir),
        ],
    )
    assert result.exit_code == 0, result.output


def _make_text_file(path: Path, content: str = "alpha beta gamma") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _stub_report(cases_dir: Path, case_id: str) -> None:
    """Write a draft.html so `case sign` succeeds (mark_signed needs a report — audit P1.5)."""
    report_dir = cases_dir / case_id / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "draft.html").write_text("<html>stub</html>", encoding="utf-8")


# ---------------------------------------------------------------------------
# `case new`
# ---------------------------------------------------------------------------


def test_case_new_creates_directory_and_records_metadata(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    result = runner.invoke(
        app,
        [
            "case",
            "new",
            "r-v-doe",
            "--title",
            "R v. Doe",
            "--examiner",
            "Dr. Watson",
            "--recipe",
            "imposters_lr",
            "--cases-dir",
            str(cases_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "created case r-v-doe" in result.output
    assert "forensic" in result.output

    case = Case.load(cases_dir / "r-v-doe")
    assert case.record.examiner == "Dr. Watson"
    assert case.record.mode == "forensic"
    assert case.record.recipe == "imposters_lr"


def test_case_new_unknown_recipe_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "case",
            "new",
            "bogus",
            "--title",
            "x",
            "--examiner",
            "x",
            "--recipe",
            "not_a_real_recipe",
            "--cases-dir",
            str(tmp_path / "cases"),
        ],
    )
    assert result.exit_code != 0
    assert "error" in result.output.lower()


def test_case_new_refuses_to_overwrite(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "dup")
    result = runner.invoke(
        app,
        [
            "case",
            "new",
            "dup",
            "--title",
            "y",
            "--examiner",
            "y",
            "--cases-dir",
            str(cases_dir),
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# `case list`
# ---------------------------------------------------------------------------


def test_case_list_shows_each_case(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "alpha", recipe="exploration", title="Alpha")
    _new(cases_dir, "beta", recipe="imposters_lr", title="Beta")

    result = runner.invoke(app, ["case", "list", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output
    assert "forensic" in result.output  # beta is imposters_lr


def test_case_list_handles_empty_root(tmp_path: Path) -> None:
    result = runner.invoke(app, ["case", "list", "--cases-dir", str(tmp_path / "empty")])
    assert result.exit_code == 0
    assert "no cases" in result.output.lower()


# ---------------------------------------------------------------------------
# `case open`
# ---------------------------------------------------------------------------


def test_case_open_prints_path_and_metadata(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "alpha", title="One-line summary case")

    result = runner.invoke(app, ["case", "open", "alpha", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 0
    assert "alpha" in result.output
    # Rich may line-wrap the long path; flatten whitespace before checking.
    flat = " ".join(result.output.split())
    assert str(cases_dir / "alpha") in flat
    assert "One-line summary case" in result.output


def test_case_open_unknown_case_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["case", "open", "missing", "--cases-dir", str(tmp_path / "cases")])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# `case status`
# ---------------------------------------------------------------------------


def test_case_status_runs_custody_check_clean(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "clean")

    result = runner.invoke(app, ["case", "status", "clean", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 0
    assert "custody: OK" in result.output


def test_case_status_exits_2_on_custody_mismatch(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "tamper")

    # Register a piece of evidence via the API, then mutate the file on disk.
    case = Case.load(cases_dir / "tamper")
    src = _make_text_file(tmp_path / "src.txt", "original")
    entry = case.add_evidence(src, role="known")
    (case.root / entry.path).write_text("tampered", encoding="utf-8")

    result = runner.invoke(app, ["case", "status", "tamper", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 2
    assert "custody mismatch" in result.output.lower()


def test_case_status_no_verify_skips_custody_check(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "skip")
    case = Case.load(cases_dir / "skip")
    src = _make_text_file(tmp_path / "src.txt", "x")
    entry = case.add_evidence(src, role="known")
    (case.root / entry.path).write_text("tampered", encoding="utf-8")

    result = runner.invoke(
        app, ["case", "status", "skip", "--no-verify", "--cases-dir", str(cases_dir)]
    )
    assert result.exit_code == 0
    assert "custody" not in result.output.lower()  # never reached the OK / mismatch line


# ---------------------------------------------------------------------------
# `case fork`
# ---------------------------------------------------------------------------


def test_case_fork_creates_unsigned_descendant(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "source")

    case = Case.load(cases_dir / "source")
    case.add_evidence(_make_text_file(tmp_path / "q.txt", "q"), role="questioned")
    case.add_evidence(_make_text_file(tmp_path / "k.txt", "k"), role="known")
    case.set_control_corpus("BUMR", n_docs=10)
    _stub_report(cases_dir, "source")
    case.mark_signed()

    result = runner.invoke(app, ["case", "fork", "source", "iter1", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 0

    forked = Case.load(cases_dir / "iter1")
    assert forked.record.signed is False
    assert len(forked.record.evidence.questioned) == 1
    assert len(forked.record.evidence.known) == 1
    assert forked.record.evidence.control is not None
    assert forked.record.evidence.control.corpus_id == "BUMR"
    assert forked.record.runs == []
    # Title carries provenance by default.
    assert "fork of source" in forked.record.title


def test_case_fork_custom_title_and_examiner(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "src")
    result = runner.invoke(
        app,
        [
            "case",
            "fork",
            "src",
            "alt",
            "--title",
            "Alternate run",
            "--examiner",
            "Other Examiner",
            "--cases-dir",
            str(cases_dir),
        ],
    )
    assert result.exit_code == 0
    forked = Case.load(cases_dir / "alt")
    assert forked.record.title == "Alternate run"
    assert forked.record.examiner == "Other Examiner"


def test_case_fork_destination_exists_errors(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "src")
    _new(cases_dir, "dest")
    result = runner.invoke(app, ["case", "fork", "src", "dest", "--cases-dir", str(cases_dir)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# `case sign`
# ---------------------------------------------------------------------------


def test_case_sign_writes_signed_json_and_freezes(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "tosign", examiner="Original Examiner")
    _stub_report(cases_dir, "tosign")

    result = runner.invoke(app, ["case", "sign", "tosign", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 0
    assert "signed tosign" in result.output

    signed_json = cases_dir / "tosign" / "report" / "signed.json"
    assert signed_json.is_file()
    payload = json.loads(signed_json.read_text(encoding="utf-8"))
    assert payload["signed_by"] == "Original Examiner"
    assert payload["case_state_hash"]

    # Re-signing is rejected.
    again = runner.invoke(app, ["case", "sign", "tosign", "--cases-dir", str(cases_dir)])
    assert again.exit_code != 0


def test_case_sign_override_signed_by(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "case1", examiner="Default Examiner")
    _stub_report(cases_dir, "case1")

    result = runner.invoke(
        app,
        [
            "case",
            "sign",
            "case1",
            "--signed-by",
            "Override Person",
            "--cases-dir",
            str(cases_dir),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(
        (cases_dir / "case1" / "report" / "signed.json").read_text(encoding="utf-8")
    )
    assert payload["signed_by"] == "Override Person"


def test_case_sign_unknown_case_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["case", "sign", "ghost", "--cases-dir", str(tmp_path / "cases")])
    assert result.exit_code != 0


def test_case_sign_hmac_plugin_wraps_signature(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BITIG_SIGNATURE_KEY", "test-key-cli")
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "hmac1")
    _stub_report(cases_dir, "hmac1")

    result = runner.invoke(
        app,
        [
            "case",
            "sign",
            "hmac1",
            "--signature-plugin",
            "hmac",
            "--cases-dir",
            str(cases_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "signature plugin: hmac" in result.output
    assert "HMAC-SHA256" in result.output

    payload = json.loads(
        (cases_dir / "hmac1" / "report" / "signed.json").read_text(encoding="utf-8")
    )
    assert payload["signature"]["algorithm"] == "HMAC-SHA256"


def test_case_sign_unknown_plugin_errors(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "p")
    result = runner.invoke(
        app,
        ["case", "sign", "p", "--signature-plugin", "totally-fake", "--cases-dir", str(cases_dir)],
    )
    assert result.exit_code != 0
    assert "Unknown signature plugin" in result.output


# ---------------------------------------------------------------------------
# `case verify` (audit P1.1)
# ---------------------------------------------------------------------------


def test_case_verify_passes_for_untampered_seal(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "vok")
    _stub_report(cases_dir, "vok")
    assert runner.invoke(app, ["case", "sign", "vok", "--cases-dir", str(cases_dir)]).exit_code == 0

    result = runner.invoke(app, ["case", "verify", "vok", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 0, result.output
    assert "seal verified" in result.output


def test_case_verify_exits_2_on_tamper(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "vbad")
    _stub_report(cases_dir, "vbad")
    runner.invoke(app, ["case", "sign", "vbad", "--cases-dir", str(cases_dir)])

    # Tamper with the frozen report after signing.
    (cases_dir / "vbad" / "report" / "signed.html").write_text("<html>forged</html>", "utf-8")

    result = runner.invoke(app, ["case", "verify", "vbad", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 2
    assert "SEAL BROKEN" in result.output


def test_case_verify_exits_1_when_unsigned(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    _new(cases_dir, "uns")
    result = runner.invoke(app, ["case", "verify", "uns", "--cases-dir", str(cases_dir)])
    assert result.exit_code == 1
    assert "not signed" in result.output
