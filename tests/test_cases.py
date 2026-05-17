"""Tests for the Case data model (spec §2, §6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bitig.cases import (
    Case,
    CaseError,
    CaseEvidence,
    CaseRecord,
    ControlCorpusRef,
    EvidenceEntry,
    compute_corpus_hash,
    hash_file,
    hash_text,
    list_cases,
)
from bitig.config.schema import StudyConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def cases_root(tmp_path: Path) -> Path:
    return tmp_path / "cases"


@pytest.fixture()
def text_factory(tmp_path: Path):
    counter = {"n": 0}

    def make(text: str = "The quick brown fox jumps over the lazy dog.") -> Path:
        counter["n"] += 1
        p = tmp_path / f"src_{counter['n']}.txt"
        p.write_text(text, encoding="utf-8")
        return p

    return make


# ---------------------------------------------------------------------------
# Directory layout + persistence
# ---------------------------------------------------------------------------


def test_create_lays_out_spec_directory(cases_root: Path):
    case = Case.create(
        cases_root,
        id="r-v-doe",
        title="R v. Doe — anonymous letter authorship",
        examiner="F. Bozdağ",
        recipe="imposters_lr",
    )

    assert case.root == cases_root / "r-v-doe"
    assert case.case_json_path.is_file()
    assert case.study_yaml_path.is_file()
    for sub in ("evidence/questioned", "evidence/known", "evidence/control", "runs", "report"):
        assert (case.root / sub).is_dir(), f"missing {sub}"


def test_create_refuses_to_overwrite_existing_case(cases_root: Path):
    Case.create(cases_root, id="dup", title="x", examiner="x", recipe="imposters_lr")
    with pytest.raises(CaseError):
        Case.create(cases_root, id="dup", title="x", examiner="x", recipe="imposters_lr")


def test_create_records_examiner_and_iso_timestamp(cases_root: Path):
    case = Case.create(
        cases_root, id="r1", title="t", examiner="Inspector Lestrade", recipe="delta_attribution"
    )
    assert case.record.examiner == "Inspector Lestrade"
    # ISO 8601 UTC with Z, matches the example in spec §2.
    assert case.record.created_at.endswith("Z")
    assert "T" in case.record.created_at


def test_save_and_load_round_trip(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="rt", title="t", examiner="x", recipe="imposters_lr")
    case.add_evidence(text_factory("questioned sample text"), role="questioned")
    case.add_evidence(text_factory("known sample text"), role="known", author="Doe", year=2019)
    case.set_control_corpus("BUMR-AT-2024", n_docs=240)

    reloaded = Case.load(case.root)
    assert reloaded.record.id == "rt"
    assert reloaded.record.mode == "forensic"
    assert len(reloaded.record.evidence.questioned) == 1
    assert len(reloaded.record.evidence.known) == 1
    assert reloaded.record.evidence.known[0].author == "Doe"
    assert reloaded.record.evidence.control is not None
    assert reloaded.record.evidence.control.corpus_id == "BUMR-AT-2024"


def test_load_rejects_non_case_directory(tmp_path: Path):
    (tmp_path / "not_a_case").mkdir()
    with pytest.raises(CaseError):
        Case.load(tmp_path / "not_a_case")


def test_list_cases_skips_non_case_directories(cases_root: Path):
    cases_root.mkdir()
    (cases_root / "stray_folder").mkdir()
    (cases_root / "stray.txt").write_text("ignore me", encoding="utf-8")

    Case.create(cases_root, id="alpha", title="t", examiner="x", recipe="exploration")
    Case.create(cases_root, id="beta", title="t", examiner="x", recipe="exploration")

    listing = list_cases(cases_root)
    assert [c.record.id for c in listing] == ["alpha", "beta"]


def test_list_cases_returns_empty_for_missing_root(tmp_path: Path):
    assert list_cases(tmp_path / "does-not-exist") == []


# ---------------------------------------------------------------------------
# Evidence registration + chain of custody
# ---------------------------------------------------------------------------


def test_add_evidence_copies_hashes_and_counts_tokens(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="e1", title="t", examiner="x", recipe="imposters_lr")
    src = text_factory("alpha beta gamma delta epsilon")  # 5 whitespace tokens

    entry = case.add_evidence(src, role="questioned")

    assert entry.role == "questioned"
    assert entry.tokens == 5
    assert entry.sha256 == hash_file(src)
    # Path is relative to the case root and the file is physically present there.
    assert (case.root / entry.path).is_file()
    assert Path(entry.path).is_absolute() is False


def test_add_evidence_refuses_to_overwrite_existing_name(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="dup", title="t", examiner="x", recipe="imposters_lr")
    src = text_factory("foo")
    case.add_evidence(src, role="known")
    with pytest.raises(CaseError):
        case.add_evidence(src, role="known")  # same filename


def test_add_evidence_accepts_dest_name_to_disambiguate(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="dup2", title="t", examiner="x", recipe="imposters_lr")
    src = text_factory("foo")
    case.add_evidence(src, role="known")
    second = case.add_evidence(src, role="known", dest_name="renamed.txt")
    assert second.path.endswith("renamed.txt")


def test_add_evidence_rejects_control_role(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="ctrl", title="t", examiner="x", recipe="imposters_lr")
    with pytest.raises(CaseError):
        case.add_evidence(text_factory(), role="control")


def test_verify_custody_clean_when_files_untouched(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="clean", title="t", examiner="x", recipe="imposters_lr")
    case.add_evidence(text_factory("a"), role="questioned")
    case.add_evidence(text_factory("b"), role="known")
    assert case.verify_custody() == []


def test_verify_custody_flags_modified_file(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="tamper", title="t", examiner="x", recipe="imposters_lr")
    entry = case.add_evidence(text_factory("original"), role="known")
    # Analyst (or attacker) edits the registered file behind bitig's back.
    (case.root / entry.path).write_text("tampered", encoding="utf-8")

    mismatches = case.verify_custody()
    assert [m.path for m in mismatches] == [entry.path]


def test_verify_custody_flags_missing_file(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="missing", title="t", examiner="x", recipe="imposters_lr")
    entry = case.add_evidence(text_factory("here"), role="known")
    (case.root / entry.path).unlink()
    assert [m.path for m in case.verify_custody()] == [entry.path]


def test_corpus_hash_changes_when_evidence_changes(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="ch", title="t", examiner="x", recipe="imposters_lr")
    case.add_evidence(text_factory("one"), role="questioned")
    h1 = case.record.corpus_hash
    case.add_evidence(text_factory("two"), role="known")
    h2 = case.record.corpus_hash
    assert h1 != h2
    assert h2 == compute_corpus_hash(case.record.evidence)


# ---------------------------------------------------------------------------
# Study config regeneration
# ---------------------------------------------------------------------------


def test_regenerate_study_yaml_writes_validated_study(cases_root: Path):
    case = Case.create(cases_root, id="sy", title="t", examiner="x", recipe="imposters_lr")
    study = yaml.safe_load(case.study_yaml_path.read_text(encoding="utf-8"))
    StudyConfig.model_validate(study)
    # study.yaml's corpus.path points at the Case's evidence dir, so a
    # `bitig run study.yaml` from inside the Case works.
    assert study["corpus"]["path"] == str(case.evidence_dir)


def test_study_hash_changes_when_recipe_changes(cases_root: Path):
    case = Case.create(cases_root, id="rh", title="t", examiner="x", recipe="imposters_lr")
    before = case.record.study_hash
    case.change_recipe("delta_attribution")
    after = case.record.study_hash
    assert before != after
    assert case.record.mode == "research"


def test_change_recipe_to_custom_with_verify_yields_forensic_mode(cases_root: Path):
    """Custom recipes derive their mode from the resolved study (spec §3 last row)."""
    case = Case.create(cases_root, id="cu", title="t", examiner="x", recipe="delta_attribution")
    assert case.record.mode == "research"

    case.change_recipe(
        "custom",
        overrides={
            "features": [{"id": "mfw", "type": "mfw", "top_n": 200}],
            "methods": [{"id": "v", "kind": "verify", "features": "mfw"}],
        },
    )
    assert case.record.recipe == "custom"
    assert case.record.mode == "forensic"


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_register_run_updates_latest_run_and_runs_list(cases_root: Path):
    case = Case.create(cases_root, id="run", title="t", examiner="x", recipe="exploration")

    run_id = "2026-05-17T12-04-21Z"
    (case.runs_dir / run_id).mkdir()
    case.register_run(run_id)

    assert case.record.latest_run == run_id
    assert run_id in case.record.runs

    # Calling twice with the same id is idempotent on the list.
    case.register_run(run_id)
    assert case.record.runs.count(run_id) == 1


def test_register_run_refuses_missing_directory(cases_root: Path):
    case = Case.create(cases_root, id="badrun", title="t", examiner="x", recipe="exploration")
    with pytest.raises(CaseError):
        case.register_run("never-created")


# ---------------------------------------------------------------------------
# Sign & lock (spec §6)
# ---------------------------------------------------------------------------


def test_mark_signed_writes_signed_json_and_freezes_case(cases_root: Path, text_factory):
    case = Case.create(
        cases_root, id="sign", title="t", examiner="F. Bozdağ", recipe="imposters_lr"
    )
    case.add_evidence(text_factory("q"), role="questioned")
    case.add_evidence(text_factory("k"), role="known")

    payload = case.mark_signed()

    assert case.is_signed
    signed_path = case.report_dir / "signed.json"
    assert signed_path.is_file()
    on_disk = json.loads(signed_path.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert payload["signed_by"] == "F. Bozdağ"
    assert payload["case_state_hash"]  # non-empty
    assert payload["bitig_version"]


def test_signed_case_rejects_mutations(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="frozen", title="t", examiner="x", recipe="imposters_lr")
    case.mark_signed()

    with pytest.raises(CaseError):
        case.add_evidence(text_factory(), role="questioned")
    with pytest.raises(CaseError):
        case.set_control_corpus("X", n_docs=1)
    with pytest.raises(CaseError):
        case.change_recipe("delta_attribution")
    with pytest.raises(CaseError):
        case.regenerate_study_yaml()
    with pytest.raises(CaseError):
        case.mark_signed()


def test_case_state_hash_changes_when_evidence_changes(cases_root: Path, text_factory):
    case = Case.create(cases_root, id="csh", title="t", examiner="x", recipe="imposters_lr")
    h1 = case._case_state_hash()
    case.add_evidence(text_factory("new evidence"), role="known")
    h2 = case._case_state_hash()
    assert h1 != h2


def test_signed_by_falls_back_to_examiner(cases_root: Path):
    case = Case.create(
        cases_root, id="auto", title="t", examiner="Dr. Watson", recipe="exploration"
    )
    payload = case.mark_signed()
    assert payload["signed_by"] == "Dr. Watson"


# ---------------------------------------------------------------------------
# Misc record-level helpers
# ---------------------------------------------------------------------------


def test_evidence_entry_dict_round_trip():
    e = EvidenceEntry(path="evidence/questioned/x.txt", sha256="abc", tokens=10, role="questioned")
    assert EvidenceEntry.from_dict(e.to_dict()) == e


def test_control_corpus_ref_round_trip():
    c = ControlCorpusRef(corpus_id="BUMR", n_docs=200)
    assert ControlCorpusRef.from_dict(c.to_dict()) == c


def test_compute_corpus_hash_is_deterministic_and_order_independent():
    ev1 = CaseEvidence(
        questioned=[EvidenceEntry(path="a.txt", sha256="aa", tokens=1, role="questioned")],
        known=[
            EvidenceEntry(path="b.txt", sha256="bb", tokens=2, role="known"),
            EvidenceEntry(path="c.txt", sha256="cc", tokens=3, role="known"),
        ],
    )
    ev2 = CaseEvidence(
        questioned=[EvidenceEntry(path="a.txt", sha256="aa", tokens=1, role="questioned")],
        known=[
            EvidenceEntry(path="c.txt", sha256="cc", tokens=3, role="known"),
            EvidenceEntry(path="b.txt", sha256="bb", tokens=2, role="known"),
        ],
    )
    assert compute_corpus_hash(ev1) == compute_corpus_hash(ev2)
    assert compute_corpus_hash(ev1) == hash_text(
        "known:b.txt:bb\nknown:c.txt:cc\nquestioned:a.txt:aa"
    )


def test_case_record_dict_round_trip():
    r = CaseRecord(
        id="rec",
        title="t",
        created_at="2026-05-17T00:00:00Z",
        examiner="x",
        recipe="imposters_lr",
        mode="forensic",
        evidence=CaseEvidence(
            questioned=[EvidenceEntry(path="q.txt", sha256="aa", tokens=1, role="questioned")],
            control=ControlCorpusRef(corpus_id="C", n_docs=10),
        ),
        overrides={"seed": 7},
    )
    assert CaseRecord.from_dict(r.to_dict()) == r
