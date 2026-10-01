"""Tests for the config-driven runner."""

from pathlib import Path

import pytest
import yaml

from bitig.runner import run_study

pytestmark = pytest.mark.integration


def _write_study(tmp_path: Path, corpus_path: Path, metadata: Path) -> Path:
    study = {
        "name": "test-study",
        "seed": 42,
        "corpus": {"path": str(corpus_path), "metadata": str(metadata)},
        "features": [{"id": "mfw", "type": "mfw", "n": 100, "scale": "zscore", "lowercase": True}],
        "methods": [
            {
                "id": "burrows",
                "kind": "delta",
                "method": "burrows",
                "features": "mfw",
                "group_by": "author",
            },
            {
                "id": "pca",
                "kind": "reduce",
                "features": "mfw",
                "n_components": 2,
            },
        ],
        "cache": {"dir": str(tmp_path / "cache")},
        "output": {"dir": str(tmp_path / "results"), "timestamp": False},
    }
    cfg = tmp_path / "study.yaml"
    cfg.write_text(yaml.safe_dump(study))
    return cfg


def test_runner_executes_study(tmp_path: Path) -> None:
    fed = Path("tests/fixtures/federalist")
    cfg = _write_study(tmp_path, fed, fed / "metadata.tsv")
    run_dir = run_study(cfg, run_name="fixed-run")
    assert (run_dir / "burrows").is_dir()
    assert (run_dir / "burrows" / "result.json").is_file()
    assert (run_dir / "pca").is_dir()
    assert (run_dir / "pca" / "result.json").is_file()
    assert (run_dir / "resolved_config.json").is_file()


def test_runner_records_spacy_version_in_provenance(tmp_path: Path) -> None:
    """Every method's result.json must carry a non-empty spacy_version.

    Regression test for the audit finding that runner.py hardcoded spacy_version=""
    in every provenance record, making studies non-reproducible to the level of the
    exact spaCy release used.
    """
    import json
    import re

    import spacy

    fed = Path("tests/fixtures/federalist")
    cfg = _write_study(tmp_path, fed, fed / "metadata.tsv")
    run_dir = run_study(cfg, run_name="spacy-ver-check")

    for method_name in ("burrows", "pca"):
        data = json.loads((run_dir / method_name / "result.json").read_text())
        recorded = data["provenance"]["spacy_version"]
        assert recorded == spacy.__version__
        assert re.match(r"^\d+\.\d+\.\d+", recorded)
        # No spaCy model is loaded by the runner, so none may be claimed (audit 2026-09-26).
        assert data["provenance"]["spacy_model"].startswith("none")
