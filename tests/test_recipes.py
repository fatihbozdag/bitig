"""Tests for the recipe registry (spec §3, §5.2)."""

from __future__ import annotations

import pytest

from bitig.config.schema import StudyConfig
from bitig.recipes import (
    CUSTOM_RECIPE_ID,
    RECIPES,
    derive_mode,
    is_custom,
    recipe_mode,
    resolve_recipe,
)


def test_registry_holds_five_named_recipes():
    """The spec locks five named recipes plus custom (which is *not* in the registry)."""
    assert set(RECIPES) == {
        "imposters_lr",
        "delta_attribution",
        "exploration",
        "zeta_contrast",
        "bayesian",
    }
    assert CUSTOM_RECIPE_ID not in RECIPES


@pytest.mark.parametrize("recipe_id", sorted(RECIPES))
def test_recipe_defaults_validate_as_study_config(recipe_id: str):
    """Each recipe's defaults must produce a study.yaml that passes Pydantic."""
    resolved = resolve_recipe(recipe_id, corpus_path="/tmp/x")
    StudyConfig.model_validate(resolved)  # raises on failure


@pytest.mark.parametrize("recipe_id", sorted(RECIPES))
def test_recipe_declared_mode_matches_derived_mode(recipe_id: str):
    """Declared mode in code must equal what derive_mode infers from the
    resolved study — otherwise the §3 rule is a lie."""
    resolved = resolve_recipe(recipe_id, corpus_path="/tmp/x")
    declared = RECIPES[recipe_id].mode
    assert derive_mode(resolved) == declared


def test_only_imposters_recipe_is_forensic():
    """Exactly one of the five named recipes is forensic (spec §3 table)."""
    forensic = [r for r in RECIPES.values() if r.mode == "forensic"]
    assert [r.id for r in forensic] == ["imposters_lr"]


def test_resolve_recipe_uses_corpus_path_argument():
    resolved = resolve_recipe("delta_attribution", corpus_path="/data/letters")
    assert resolved["corpus"]["path"] == "/data/letters"


def test_resolve_recipe_overrides_replace_recipe_defaults():
    """Top-level keys in overrides replace the recipe's defaults wholesale."""
    custom_methods = [{"id": "myverify", "kind": "verify", "features": "mfw"}]
    resolved = resolve_recipe(
        "imposters_lr",
        overrides={"methods": custom_methods},
        corpus_path="/tmp/x",
    )
    assert resolved["methods"] == custom_methods


def test_resolve_recipe_unknown_id_raises():
    with pytest.raises(KeyError):
        resolve_recipe("not_a_recipe", corpus_path="/tmp/x")


def test_resolve_custom_recipe_passes_overrides_verbatim():
    overrides = {
        "features": [{"id": "mfw", "type": "mfw", "top_n": 100}],
        "methods": [{"id": "delta", "kind": "delta", "features": "mfw"}],
        "seed": 7,
    }
    resolved = resolve_recipe("custom", overrides=overrides, corpus_path="/tmp/x")
    assert resolved["features"] == overrides["features"]
    assert resolved["methods"] == overrides["methods"]
    assert resolved["seed"] == 7


def test_derive_mode_dispatches_on_method_kind():
    forensic_dict = {"methods": [{"id": "v", "kind": "verify"}]}
    research_dict = {"methods": [{"id": "d", "kind": "delta"}]}
    empty_dict: dict = {"methods": []}

    assert derive_mode(forensic_dict) == "forensic"
    assert derive_mode(research_dict) == "research"
    assert derive_mode(empty_dict) == "research"


def test_derive_mode_accepts_validated_study_config():
    """The same function must work on a Pydantic StudyConfig too."""
    resolved = resolve_recipe("imposters_lr", corpus_path="/tmp/x")
    cfg = StudyConfig.model_validate(resolved)
    assert derive_mode(cfg) == "forensic"


def test_recipe_mode_for_custom_requires_resolved_study():
    with pytest.raises(ValueError):
        recipe_mode(CUSTOM_RECIPE_ID)


def test_recipe_mode_for_custom_derives_from_study():
    resolved = {"methods": [{"id": "v", "kind": "verify"}]}
    assert recipe_mode(CUSTOM_RECIPE_ID, study=resolved) == "forensic"


def test_is_custom_helper():
    assert is_custom("custom")
    assert not is_custom("imposters_lr")
