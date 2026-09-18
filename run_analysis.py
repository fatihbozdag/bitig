"""Validate the news study; --execute runs only a reviewed, adequately covered corpus."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from collect_corpus import (
    CASES,
    PAPERS,
    atomic_write,
    body_text,
    coverage_report,
    digest,
    load_rows,
    write_rows,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("study-data/corpus"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("study-data/validated-runs"))
    args = parser.parse_args()
    rows = load_rows(args.corpus)
    report = coverage_report(args.corpus, rows)
    atomic_write(
        args.corpus.parent / "coverage.json",
        json.dumps(report, indent=2, ensure_ascii=False).encode(),
    )
    if not report["ready_for_full_comparison"]:
        raise SystemExit(
            f"Study not ready: inspect {args.corpus.parent / 'coverage.json'}, fill event/paper gaps, "
            "verify publication dates and complete inclusion/extraction adjudication."
        )
    selected = [r for r in rows if r.get("inclusion_status") == "included"]
    # Enforce explicit review of agency/near-duplicate overlap, not automatic exclusion.
    if any(
        float(r.get("agency_overlap") or 0) >= 0.8 and r.get("overlap_review") != "independent"
        for r in selected
    ):
        raise SystemExit("High-overlap articles require overlap_review=independent or exclusion.")
    if not args.execute:
        print("Coverage and integrity checks passed. Use --execute for the analysis.")
        return
    from bitig.runner import StudyRunStatus, run_study

    # Keep exact body-only inputs permanently; resolved paths remain usable after the run.
    bundle = args.output.resolve() / datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    stage = bundle / "inputs"
    stage.mkdir(parents=True, exist_ok=False)
    staged_rows = []
    for row in selected:
        data = body_text(args.corpus, row).encode("utf-8")
        atomic_write(stage / row["filename"], data)
        staged = {**row, "section": "body", "sha256": digest(data), "source_sha256": row["sha256"]}
        for index, paper in enumerate(PAPERS):
            staged[f"paper_{index}"] = paper if row["newspaper"] == paper else "Rest"
        staged_rows.append(staged)
    write_rows(stage, staged_rows)
    study = {
        "name": "news-comparison",
        "seed": 42,
        "preprocess": {"language": "tr"},
        "corpus": {"path": str(stage), "metadata": str(stage / "meta.tsv")},
        "features": [
            {"id": "counts", "type": "mfw", "n": 500, "scale": "none", "lowercase": True},
            {"id": "mfw", "type": "mfw", "n": 500, "scale": "zscore", "lowercase": True},
        ],
        "methods": [
            {
                "id": "bayesian_cv",
                "kind": "bayesian",
                "features": "counts",
                "group_by": "newspaper",
                "cv": {"kind": "loao", "groups_from": "event"},
            },
            {
                "id": "delta_descriptive",
                "kind": "delta",
                "features": "mfw",
                "group_by": "newspaper",
            },
            {"id": "pca", "kind": "reduce", "features": "mfw", "n_components": 2},
            {"id": "cluster", "kind": "cluster", "features": "mfw", "n_clusters": len(PAPERS)},
        ],
        "report": {"format": "html"},
    }
    for index, paper in enumerate(PAPERS):
        study["methods"].append(
            {
                "id": f"zeta_paper_{index}",
                "kind": "zeta",
                "group_by": f"paper_{index}",
                "group_a": paper,
                "group_b": "Rest",
                "variant": "eder",
                "top_k": 30,
            }
        )
    study["methods"].extend(
        [
            {"id": "delta_event", "kind": "delta", "features": "mfw", "group_by": "event"},
            {
                "id": "zeta_papers",
                "kind": "zeta",
                "group_by": "newspaper",
                "group_a": "Sabah",
                "group_b": "Cumhuriyet",
                "variant": "eder",
                "top_k": 30,
            },
            {
                "id": "zeta_events",
                "kind": "zeta",
                "group_by": "event",
                "group_a": "ceren_ozdemir",
                "group_b": "emine_bulut",
                "variant": "eder",
                "top_k": 30,
            },
        ]
    )
    config = stage / "study.yaml"
    config.write_text(yaml.safe_dump(study, allow_unicode=True))
    directory = run_study(config, output_dir=bundle / "results", run_name="analysis")
    status = StudyRunStatus.load(directory)
    print(f"{status.status}: {directory} ({len(CASES)} events)")
    if status.status != "succeeded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
