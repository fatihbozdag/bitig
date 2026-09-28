"""Study params are checked against the runner's constructors (audit 2026-09-26 N-P1.14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bitig.config import load_config
from bitig.config.schema import StudyConfig
from bitig.runner import validate_study_params

_EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _cfg(features: list[dict], methods: list[dict]) -> StudyConfig:
    return StudyConfig.model_validate(
        {"name": "t", "corpus": {"path": "x"}, "features": features, "methods": methods}
    )


_MFW = [{"id": "mfw", "type": "mfw", "n": 100}]


def test_delta_method_key_is_a_deprecated_alias_for_variant() -> None:
    cfg = _cfg(_MFW, [{"id": "d", "kind": "delta", "features": "mfw", "method": "cosine"}])
    with pytest.warns(DeprecationWarning, match="variant"):
        validate_study_params(cfg)
    assert cfg.methods[0].params == {"variant": "cosine"}


def test_delta_method_and_variant_together_is_an_error() -> None:
    cfg = _cfg(
        _MFW,
        [{"id": "d", "kind": "delta", "features": "mfw", "method": "cosine", "variant": "eder"}],
    )
    with pytest.raises(ValueError, match="not both"):
        validate_study_params(cfg)


@pytest.mark.parametrize(
    ("features", "methods", "needle"),
    [
        ([{"id": "mfw", "type": "mfw", "top_n": 100}], [], "top_n"),
        (_MFW, [{"id": "v", "kind": "verify", "iterations": 5}], "iterations"),
        (_MFW, [{"id": "p", "kind": "reduce", "features": "mfw", "algorithm": "pca"}], "algorithm"),
        (
            _MFW,
            [
                {
                    "id": "k",
                    "kind": "cluster",
                    "features": "mfw",
                    "variant": "kmeans",
                    "linkage": "ward",
                }
            ],
            "linkage",
        ),
        (_MFW, [{"id": "c", "kind": "classify", "features": "mfw", "folds": 3}], "folds"),
        ([{"id": "pos", "type": "pos_ngram"}], [], "not supported"),
    ],
)
def test_unknown_params_and_unsupported_features_are_rejected(features, methods, needle) -> None:
    with pytest.raises(ValueError, match=needle):
        validate_study_params(_cfg(features, methods))


def test_valid_params_pass() -> None:
    validate_study_params(
        _cfg(
            _MFW,
            [
                {"id": "d", "kind": "delta", "features": "mfw", "variant": "cosine"},
                {
                    "id": "p",
                    "kind": "reduce",
                    "features": "mfw",
                    "variant": "mds",
                    "n_components": 2,
                },
                {
                    "id": "v",
                    "kind": "verify",
                    "target_ids": ["q"],
                    "candidate": "A",
                    "n_iter": 10,
                    "base_delta": "cosine",
                },
            ],
        )
    )


@pytest.mark.parametrize(
    "study", ["quickstart/study.yaml", "federalist/study.yaml", "turkish_seyfettin/study.yaml"]
)
def test_shipped_examples_validate(study: str) -> None:
    validate_study_params(load_config(_EXAMPLES / study))
