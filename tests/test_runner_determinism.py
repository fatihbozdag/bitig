"""Same study + same seed → identical result values (audit 2026-09-26 N-P1.15)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import yaml

from bitig.runner import run_study

_MINI = Path(__file__).parent / "fixtures" / "mini_corpus"


def _study(tmp_path: Path, seed: int, name: str) -> Path:
    study = {
        "name": name,
        "seed": seed,
        "corpus": {"path": str(_MINI), "metadata": str(_MINI / "metadata.tsv")},
        "features": [{"id": "mfw", "type": "mfw", "n": 30}],
        "methods": [
            {
                "id": "km",
                "kind": "cluster",
                "features": "mfw",
                "variant": "kmeans",
                "n_clusters": 2,
                "n_init": 1,
            },
            {"id": "mds", "kind": "reduce", "features": "mfw", "variant": "mds"},
            {"id": "cons", "kind": "consensus", "mfw_bands": [10, 20], "replicates": 5},
        ],
        "output": {"dir": str(tmp_path / "out"), "timestamp": False},
    }
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(study), encoding="utf-8")
    return path


def _values(run_dir: Path, method: str) -> dict:
    data = json.loads((run_dir / method / "result.json").read_text(encoding="utf-8"))
    return {"values": data["values"], "params": data["params"]}


def _assert_close(x: object, y: object, where: str) -> None:
    """Equal structure and discrete values; floats equal up to rounding (BLAS threading
    can change the last bits of e.g. k-means inertia between otherwise identical runs)."""
    if isinstance(x, dict) and isinstance(y, dict):
        assert x.keys() == y.keys(), where
        for k in x:
            _assert_close(x[k], y[k], f"{where}.{k}")
    elif isinstance(x, list) and isinstance(y, list):
        assert len(x) == len(y), where
        for i, (xi, yi) in enumerate(zip(x, y, strict=True)):
            _assert_close(xi, yi, f"{where}[{i}]")
    elif isinstance(x, float) or isinstance(y, float):
        assert math.isclose(float(x), float(y), rel_tol=1e-9, abs_tol=1e-12), where  # type: ignore[arg-type]
    else:
        assert x == y, where


def test_same_seed_gives_identical_values(tmp_path: Path) -> None:
    a = run_study(_study(tmp_path, 7, "a"), run_name="a")
    b = run_study(_study(tmp_path, 7, "b"), run_name="b")
    for method in ("km", "mds", "cons"):
        assert not (a / method / "error.txt").exists(), (a / method / "error.txt").read_text()
        _assert_close(_values(a, method), _values(b, method), method)


def test_study_seed_reaches_consensus(tmp_path: Path) -> None:
    run_dir = run_study(_study(tmp_path, 11, "c"), run_name="c")
    assert _values(run_dir, "cons")["params"]["seed"] == 11
