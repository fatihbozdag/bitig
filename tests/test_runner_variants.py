"""Round-trip tests for each runner-dispatchable method variant on mini_corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml


def _study_yaml(
    tmp_path: Path,
    corpus_dir: Path,
    *,
    kind: str,
    feat_type: str = "mfw",
    feat_params: dict[str, Any] | None = None,
    method_params: dict[str, Any] | None = None,
    group_by: str | None = None,
) -> Path:
    method_cfg: dict[str, Any] = {
        "id": f"{kind}_1",
        "kind": kind,
        "params": dict(method_params or {}),
    }
    if kind != "consensus":
        method_cfg["features"] = "feat1"
    if group_by:
        method_cfg["group_by"] = group_by
    study = {
        "seed": 42,
        "preprocess": {"language": "en", "spacy": {}},
        "corpus": {
            "path": str(corpus_dir),
            "metadata": str(corpus_dir / "metadata.tsv"),
        },
        "features": [{"id": "feat1", "type": feat_type, "params": dict(feat_params or {"n": 50})}],
        "methods": [method_cfg],
        "output": {"dir": str(tmp_path / "runs"), "timestamp": False},
    }
    cfg_path = tmp_path / "study.yaml"
    cfg_path.write_text(yaml.safe_dump(study, sort_keys=False))
    return cfg_path


@pytest.mark.parametrize(
    "variant",
    ["burrows", "cosine", "argamon_linear", "quadratic", "eder", "eder_simple"],
)
def test_delta_variant_runs(tmp_path: Path, mini_corpus_dir: Path, variant: str) -> None:
    from bitig.runner import run_study

    cfg = _study_yaml(
        tmp_path,
        mini_corpus_dir,
        kind="delta",
        method_params={"variant": variant},
        group_by="author",
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    result_path = run_dir / "delta_1" / "result.json"
    assert result_path.exists(), f"no result.json for variant={variant}"
    payload = json.loads(result_path.read_text())
    assert payload["method_name"] == f"delta_{variant}"
    # Delta reports in-sample accuracy under an honest key (audit P2).
    assert "resubstitution_accuracy" in payload["values"]
    assert "accuracy" not in payload["values"]


@pytest.mark.parametrize(
    ("variant", "extra"),
    [
        ("pca", {}),
        ("mds", {"random_state": 0}),
        # mini_corpus is 4 docs → perplexity must be < n_samples for t-SNE
        # and n_neighbors < n_samples for UMAP.
        ("tsne", {"perplexity": 2.0, "random_state": 0}),
        ("umap", {"n_neighbors": 2, "random_state": 0}),
    ],
)
def test_reduce_variant_runs(
    tmp_path: Path,
    mini_corpus_dir: Path,
    variant: str,
    extra: dict[str, Any],
) -> None:
    from bitig.runner import run_study

    cfg = _study_yaml(
        tmp_path,
        mini_corpus_dir,
        kind="reduce",
        method_params={"variant": variant, "n_components": 2, **extra},
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    result_path = run_dir / "reduce_1" / "result.json"
    assert result_path.exists(), f"no result.json for variant={variant}"
    payload = json.loads(result_path.read_text())
    assert payload["method_name"] == variant
    assert "coordinates" in payload["values"]


@pytest.mark.parametrize(
    ("variant", "extra"),
    [
        ("hierarchical", {"n_clusters": 2, "linkage": "ward"}),
        ("kmeans", {"n_clusters": 2, "random_state": 0}),
        # 4 docs → min_cluster_size must drop below default 5 to produce non-noise.
        ("hdbscan", {"min_cluster_size": 2}),
    ],
)
def test_cluster_variant_runs(
    tmp_path: Path,
    mini_corpus_dir: Path,
    variant: str,
    extra: dict[str, Any],
) -> None:
    from bitig.runner import run_study

    cfg = _study_yaml(
        tmp_path,
        mini_corpus_dir,
        kind="cluster",
        method_params={"variant": variant, **extra},
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    result_path = run_dir / "cluster_1" / "result.json"
    assert result_path.exists(), f"no result.json for variant={variant}"
    payload = json.loads(result_path.read_text())
    assert payload["method_name"] == variant
    assert "labels" in payload["values"]


def test_consensus_emits_bct_plot(tmp_path: Path, mini_corpus_dir: Path) -> None:
    from bitig.runner import run_study

    cfg = _study_yaml(
        tmp_path,
        mini_corpus_dir,
        kind="consensus",
        method_params={"mfw_bands": [20, 40], "replicates": 5},
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    method_dir = run_dir / "consensus_1"
    assert (method_dir / "result.json").exists()
    # New default plot is the consensus tree; bar chart is a fallback only.
    assert (method_dir / "consensus_tree.png").exists()


def test_bayesian_emits_posterior_heatmap(tmp_path: Path, mini_corpus_dir: Path) -> None:
    """Bayesian attribution should also drop a posterior_heatmap.png."""
    from bitig.runner import run_study

    cfg = _study_yaml(
        tmp_path,
        mini_corpus_dir,
        kind="bayesian",
        # Bayesian wants raw counts (scale="none"), not z-scored MFW.
        feat_params={"n": 30, "scale": "none"},
        method_params={"prior_alpha": 1.0},
        group_by="author",
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    method_dir = run_dir / "bayesian_1"
    assert (method_dir / "result.json").exists()
    assert (method_dir / "confusion_matrix.png").exists()
    assert (method_dir / "posterior_heatmap.png").exists()
    payload = json.loads((method_dir / "result.json").read_text())
    assert "proba" in payload["values"]
    assert "classes" in payload["values"]


def test_pca_emits_biplot(tmp_path: Path, mini_corpus_dir: Path) -> None:
    """When method=reduce + variant=pca, runner should drop pca_biplot.png next to scatter.png."""
    from bitig.runner import run_study

    cfg = _study_yaml(
        tmp_path,
        mini_corpus_dir,
        kind="reduce",
        method_params={"variant": "pca", "n_components": 2},
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    method_dir = run_dir / "reduce_1"
    assert (method_dir / "scatter.png").exists()
    assert (method_dir / "pca_biplot.png").exists()


def test_classify_emits_reliability_diagram(tmp_path: Path) -> None:
    """End-to-end: classify with logreg should also drop a reliability_diagram.png."""
    from bitig.runner import run_study

    fed_dir = Path(__file__).parent / "fixtures" / "federalist"
    method_cfg: dict[str, Any] = {
        "id": "classify_1",
        "kind": "classify",
        "features": "feat1",
        "group_by": "author",
        "cv": {"kind": "leave_one_text_out"},
        "params": {"estimator": "logreg"},
    }
    study = {
        "seed": 42,
        "preprocess": {"language": "en", "spacy": {}},
        "corpus": {"path": str(fed_dir), "metadata": str(fed_dir / "metadata.tsv")},
        "features": [{"id": "feat1", "type": "mfw", "params": {"n": 80}}],
        "methods": [method_cfg],
        "output": {"dir": str(tmp_path / "runs"), "timestamp": False},
    }
    cfg_path = tmp_path / "study.yaml"
    cfg_path.write_text(yaml.safe_dump(study, sort_keys=False))
    run_dir = run_study(cfg_path, output_dir=tmp_path / "runs", run_name="r")
    method_dir = run_dir / "classify_1"
    assert (method_dir / "result.json").exists()
    assert (method_dir / "confusion_matrix.png").exists()
    assert (method_dir / "reliability_diagram.png").exists()
    payload = json.loads((method_dir / "result.json").read_text())
    assert "ece" in payload["values"]
    assert "brier" in payload["values"]


def test_general_imposters_runs_and_plots(tmp_path: Path) -> None:
    """End-to-end: verify fed_49 against Madison; result+plot land on disk."""
    from bitig.runner import run_study

    fed_dir = Path(__file__).parent / "fixtures" / "federalist"
    cfg = _study_yaml(
        tmp_path,
        fed_dir,
        kind="verify",
        method_params={
            "target_ids": ["fed_49"],
            "candidate": "Madison",
            "n_iter": 30,
            "feature_frac": 0.5,
            "base_delta": "burrows",
            "mfw_n": 80,
            "lowercase": True,
        },
        group_by="author",
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    method_dir = run_dir / "verify_1"
    assert (method_dir / "result.json").exists()
    assert (method_dir / "table_0.parquet").exists()
    assert (method_dir / "imposters_scores.png").exists()


def test_rolling_delta_runs_and_plots(tmp_path: Path) -> None:
    """End-to-end: fed_49 (disputed Madison) is scanned; result+plot land on disk."""
    from bitig.runner import run_study

    fed_dir = Path(__file__).parent / "fixtures" / "federalist"
    cfg = _study_yaml(
        tmp_path,
        fed_dir,
        kind="rolling_delta",
        method_params={
            "target_ids": ["fed_49"],
            "window_size": 400,
            "step": 200,
            "base_delta": "burrows",
            "mfw_n": 80,
            "lowercase": True,
        },
        group_by="author",
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    method_dir = run_dir / "rolling_delta_1"
    assert (method_dir / "result.json").exists()
    assert (method_dir / "table_0.parquet").exists()
    assert (method_dir / "rolling_delta.png").exists()


@pytest.mark.parametrize("variant", ["classic", "eder"])
def test_zeta_variant_runs(tmp_path: Path, mini_corpus_dir: Path, variant: str) -> None:
    from bitig.runner import run_study

    cfg = _study_yaml(
        tmp_path,
        mini_corpus_dir,
        kind="zeta",
        method_params={"variant": variant, "top_k": 5, "min_df": 1},
        group_by="author",
    )
    run_dir = run_study(cfg, output_dir=tmp_path / "runs", run_name="r")
    result_path = run_dir / "zeta_1" / "result.json"
    assert result_path.exists(), f"no result.json for variant={variant}"
