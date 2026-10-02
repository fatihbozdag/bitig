"""Un-mocked end-to-end Case runs (audit 2026-09-26 N-P0.1 / N-P1.1).

Every other perform_run test replaces ``run_study`` with a fake, which is how
a Case that could never run any recipe shipped with a green suite. These tests
drive the real runner on registered evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bitig.case_run import perform_run
from bitig.cases import Case
from bitig.recipes import RECIPES

_MINI = Path(__file__).parent / "fixtures" / "mini_corpus"


def _case(tmp_path: Path, recipe: str) -> Case:
    case = Case.create(tmp_path / "cases", id="c", title="t", examiner="x", recipe=recipe)
    case.add_evidence(_MINI / "alice_two.txt", role="questioned")
    case.add_evidence(_MINI / "alice_one.txt", role="known", author="Alice")
    case.add_evidence(_MINI / "bob_one.txt", role="known", author="Bob")
    case.add_evidence(_MINI / "bob_two.txt", role="known", author="Bob")
    if recipe == "imposters_lr":
        case.set_param("methods[verify].candidate", "Alice")
        case.set_param("methods[verify].mfw_n", 20)
        case.set_param("methods[verify].n_iter", 20)
    return case


@pytest.mark.parametrize("recipe", sorted(RECIPES))
def test_every_recipe_runs_on_registered_evidence(tmp_path: Path, recipe: str) -> None:
    case = _case(tmp_path, recipe)
    outcome = perform_run(case)
    failed = [(m.method_id, m.error) for m in outcome.methods if not m.ok]
    assert outcome.status == "succeeded", (outcome.message, failed)
    assert case.record.latest_run == outcome.run_id


def test_verify_targets_the_questioned_documents(tmp_path: Path) -> None:
    case = _case(tmp_path, "imposters_lr")
    outcome = perform_run(case)
    assert outcome.status == "succeeded", outcome.message
    result = json.loads(
        (case.runs_dir / str(outcome.run_id) / "verify" / "result.json").read_text("utf-8")
    )
    assert result["params"]["target_ids"] == ["alice_two"]
    assert result["params"]["candidate"] == "Alice"


def test_unregistered_file_in_evidence_dir_is_not_analysed(tmp_path: Path) -> None:
    case = _case(tmp_path, "exploration")
    (case.evidence_dir / "known" / "planted.txt").write_text("planted text " * 20, "utf-8")
    outcome = perform_run(case)
    assert outcome.status == "succeeded", outcome.message
    result = json.loads(
        (case.runs_dir / str(outcome.run_id) / "pca" / "result.json").read_text("utf-8")
    )
    assert "planted" not in json.dumps(result)


def test_hand_edited_study_yaml_blocks_the_run(tmp_path: Path) -> None:
    case = _case(tmp_path, "exploration")
    study = yaml.safe_load(case.study_yaml_path.read_text("utf-8"))
    study["corpus"]["path"] = "/elsewhere"
    case.study_yaml_path.write_text(yaml.safe_dump(study), "utf-8")
    case.save()  # must not re-bless the edited file

    outcome = perform_run(Case.load(case.root))
    assert outcome.status == "blocked"
    assert "study.yaml" in outcome.message


def test_verify_without_candidate_is_blocked(tmp_path: Path) -> None:
    case = Case.create(tmp_path / "cases", id="c", title="t", examiner="x", recipe="imposters_lr")
    case.add_evidence(_MINI / "alice_two.txt", role="questioned")
    case.add_evidence(_MINI / "alice_one.txt", role="known", author="Alice")
    case.add_evidence(_MINI / "bob_one.txt", role="known", author="Bob")
    outcome = perform_run(case)
    assert outcome.status == "blocked"
    assert "Candidate author" in outcome.message


def test_verify_with_unknown_candidate_is_blocked(tmp_path: Path) -> None:
    case = _case(tmp_path, "imposters_lr")
    case.set_param("methods[verify].candidate", "Carol")
    outcome = perform_run(case)
    assert outcome.status == "blocked"
    assert "Carol" in outcome.message


def test_build_corpus_rejects_file_altered_after_registration(tmp_path: Path) -> None:
    from bitig.cases import CaseError

    case = _case(tmp_path, "exploration")
    (case.evidence_dir / "known" / "bob_one.txt").write_text("doctored", "utf-8")
    with pytest.raises(CaseError, match="custody"):
        case.build_corpus()


def test_duplicate_document_id_across_roles_is_rejected(tmp_path: Path) -> None:
    from bitig.cases import CaseError

    case = Case.create(tmp_path / "cases", id="c", title="t", examiner="x", recipe="exploration")
    case.add_evidence(_MINI / "alice_one.txt", role="questioned")
    with pytest.raises(CaseError, match="alice_one"):
        case.add_evidence(_MINI / "alice_one.txt", role="known", author="Alice")


def test_legacy_case_overrides_run_after_translation(tmp_path: Path) -> None:
    """A case created by bitig <= 0.3.1 stores old parameter names in overrides."""
    case = _case(tmp_path, "exploration")
    case.record.overrides = {
        "features": [{"id": "mfw", "type": "mfw", "top_n": 50}],
        "methods": [{"id": "pca", "kind": "reduce", "features": "mfw", "algorithm": "pca"}],
    }
    case.regenerate_study_yaml()
    case.save()
    outcome = perform_run(case)
    assert outcome.status == "succeeded", outcome.message


def test_questioned_document_added_after_set_param_is_targeted(tmp_path: Path) -> None:
    """set_param must not freeze the auto-filled target list into the overrides."""
    case = _case(tmp_path, "imposters_lr")
    extra = tmp_path / "late_q.txt"
    extra.write_text((_MINI / "bob_two.txt").read_text("utf-8"), "utf-8")
    case.add_evidence(extra, role="questioned")
    assert "target_ids" not in json.dumps(case.record.overrides)

    outcome = perform_run(case)
    assert outcome.status == "succeeded", outcome.message
    result = json.loads(
        (case.runs_dir / str(outcome.run_id) / "verify" / "result.json").read_text("utf-8")
    )
    assert sorted(result["params"]["target_ids"]) == ["alice_two", "late_q"]


def test_explicit_target_list_missing_a_questioned_document_blocks(tmp_path: Path) -> None:
    """A target list frozen by an older bitig blocks with a clear message, not a failed run."""
    case = _case(tmp_path, "imposters_lr")
    case.set_param("methods[verify].target_ids", ["alice_two"])
    extra = tmp_path / "late_q.txt"
    extra.write_text((_MINI / "bob_two.txt").read_text("utf-8"), "utf-8")
    case.add_evidence(extra, role="questioned")

    outcome = perform_run(case)
    assert outcome.status == "blocked"
    assert "late_q" in outcome.message and "not targeted" in outcome.message
    assert case.record.latest_run is None


def test_cli_case_run_exit_codes(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from bitig.cli import app

    runner = CliRunner()
    case = _case(tmp_path, "imposters_lr")
    cases_dir = str(tmp_path / "cases")

    ok = runner.invoke(app, ["case", "run", "c", "--cases-dir", cases_dir])
    assert ok.exit_code == 0, ok.output
    assert "succeeded" in ok.output
    assert Case.load(case.root).record.latest_run is not None

    (case.evidence_dir / "known" / "alice_one.txt").write_text("changed", "utf-8")
    blocked = runner.invoke(app, ["case", "run", "c", "--cases-dir", cases_dir])
    assert blocked.exit_code == 2, blocked.output
    assert "blocked" in blocked.output


def test_delta_attribution_run_emits_confusion_matrix(tmp_path: Path) -> None:
    """Predictions cover labelled documents only; the plot must still be drawn."""
    case = _case(tmp_path, "delta_attribution")
    outcome = perform_run(case)
    assert outcome.status == "succeeded", outcome.message
    figures = list((case.runs_dir / str(outcome.run_id)).rglob("confusion_matrix.png"))
    assert figures
