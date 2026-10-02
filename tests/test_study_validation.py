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


def test_cv_folds_reaches_the_classifier(tmp_path: Path) -> None:
    """cv.folds was documented but ignored (always 5) (audit 2026-09-26 P2)."""
    import json

    import yaml

    from bitig.runner import run_study

    mini = Path(__file__).parent / "fixtures" / "mini_corpus"
    study = {
        "name": "t",
        "corpus": {"path": str(mini), "metadata": str(mini / "metadata.tsv")},
        "features": [{"id": "mfw", "type": "mfw", "n": 20}],
        "methods": [
            {
                "id": "c",
                "kind": "classify",
                "features": "mfw",
                "group_by": "author",
                "cv": {"kind": "stratified", "folds": 2},
            },
        ],
        "output": {"dir": str(tmp_path / "out"), "timestamp": False},
    }
    path = tmp_path / "s.yaml"
    path.write_text(yaml.safe_dump(study), encoding="utf-8")
    run_dir = run_study(path)
    assert not (run_dir / "c" / "error.txt").exists()  # 5 folds would fail on 2 docs/class
    assert json.loads((run_dir / "c" / "result.json").read_text())["values"]["accuracy"] >= 0


def test_group_kfold_is_rejected_at_load() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _cfg(
            _MFW,
            [{"id": "c", "kind": "classify", "features": "mfw", "cv": {"kind": "group_kfold"}}],
        )
