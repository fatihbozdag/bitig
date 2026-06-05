"""Tests for the ParamField target resolver (spec §5.2 drawer save path)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bitig.cases import Case
from bitig.recipes import apply_param_target, read_param_target, resolve_recipe

# ---------------------------------------------------------------------------
# read_param_target / apply_param_target
# ---------------------------------------------------------------------------


def test_read_target_top_level_scalar():
    study = resolve_recipe("imposters_lr", corpus_path="/x")
    assert read_param_target(study, "seed") is None  # not yet set
    study["seed"] = 42
    assert read_param_target(study, "seed") == 42


def test_read_target_into_feature_list():
    study = resolve_recipe("imposters_lr", corpus_path="/x")
    assert read_param_target(study, "features[mfw].top_n") == 500


def test_read_target_into_method_list():
    study = resolve_recipe("imposters_lr", corpus_path="/x")
    assert read_param_target(study, "methods[verify].iterations") == 100
    assert read_param_target(study, "methods[verify].delta") == "cosine"


def test_read_target_missing_returns_none():
    study = resolve_recipe("imposters_lr", corpus_path="/x")
    assert read_param_target(study, "features[nope].x") is None
    assert read_param_target(study, "completely_unknown") is None


def test_apply_target_does_not_mutate_input():
    study = resolve_recipe("imposters_lr", corpus_path="/x")
    new = apply_param_target(study, "features[mfw].top_n", 1000)
    assert new["features"][0]["top_n"] == 1000
    assert study["features"][0]["top_n"] == 500  # original untouched


def test_apply_target_top_level_scalar():
    study = resolve_recipe("delta_attribution", corpus_path="/x")
    new = apply_param_target(study, "seed", 7)
    assert new["seed"] == 7


def test_apply_target_unknown_id_raises():
    study = resolve_recipe("imposters_lr", corpus_path="/x")
    with pytest.raises(KeyError):
        apply_param_target(study, "features[nope].top_n", 100)


def test_apply_target_malformed_path_raises():
    study = resolve_recipe("imposters_lr", corpus_path="/x")
    with pytest.raises(KeyError):
        apply_param_target(study, "this.is.too.deep", 1)


# ---------------------------------------------------------------------------
# Case.set_param — integration
# ---------------------------------------------------------------------------


def test_case_set_param_persists_into_study_yaml(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="sp", title="t", examiner="x", recipe="imposters_lr")

    case.set_param("features[mfw].top_n", 750)
    case.set_param("methods[verify].iterations", 200)
    case.set_param("seed", 1234)

    reloaded = Case.load(case.root)
    resolved = reloaded.resolved_study_dict()
    assert resolved["features"][0]["top_n"] == 750
    assert resolved["methods"][0]["iterations"] == 200
    assert resolved["seed"] == 1234


def test_case_set_param_signed_case_rejects(tmp_path: Path):
    from bitig.cases import CaseError

    case = Case.create(tmp_path / "cases", id="lock", title="t", examiner="x", recipe="exploration")
    (case.report_dir / "draft.html").write_text("<html>stub</html>", encoding="utf-8")
    case.mark_signed()
    with pytest.raises(CaseError):
        case.set_param("seed", 1)


def test_case_set_param_unknown_target_raises(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="bad", title="t", examiner="x", recipe="exploration")
    with pytest.raises(KeyError):
        case.set_param("features[nonsense].whatever", 1)
