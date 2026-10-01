"""`bitig run` failure reporting and run-folder reuse (audit 2026-09-26 P2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from bitig.cli import app
from bitig.runner import failed_methods, run_study

_MINI = Path(__file__).parent / "fixtures" / "mini_corpus"


def _study(tmp_path: Path, methods: list[dict], *, timestamp: bool = False) -> Path:
    study = {
        "name": "t",
        "corpus": {"path": str(_MINI), "metadata": str(_MINI / "metadata.tsv")},
        "features": [{"id": "mfw", "type": "mfw", "n": 20}],
        "methods": methods,
        "output": {"dir": str(tmp_path / "out"), "timestamp": timestamp},
    }
    path = tmp_path / "s.yaml"
    path.write_text(yaml.safe_dump(study), encoding="utf-8")
    return path


_PCA = {"id": "pca", "kind": "reduce", "features": "mfw", "n_components": 2}
_BROKEN = {"id": "zeta", "kind": "zeta", "group_by": "nonexistent"}


def test_cli_exits_1_and_names_failed_methods(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["run", str(_study(tmp_path, [_PCA, _BROKEN]))])
    assert result.exit_code == 1
    assert "zeta" in result.output and "failed" in result.output
    err = (tmp_path / "out" / "zeta" / "error.txt").read_text(encoding="utf-8")
    assert "Traceback" in err  # full traceback, not just str(exc)


def test_cli_exits_0_when_everything_succeeds(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["run", str(_study(tmp_path, [_PCA]))])
    assert result.exit_code == 0, result.output


def test_reusing_a_run_folder_is_refused_without_overwrite(tmp_path: Path) -> None:
    path = _study(tmp_path, [_PCA, _BROKEN])
    run_study(path)
    with pytest.raises(FileExistsError, match="previous run"):
        run_study(path)


def test_overwrite_removes_only_the_previous_runs_outputs(tmp_path: Path) -> None:
    run_study(_study(tmp_path, [_PCA, _BROKEN]))
    keep = tmp_path / "out" / "notes.txt"
    keep.write_text("mine", encoding="utf-8")
    run_dir = run_study(_study(tmp_path, [_PCA]), overwrite=True)
    assert keep.read_text(encoding="utf-8") == "mine"
    assert not (run_dir / "zeta").exists()  # stale output from the previous config is gone
    assert failed_methods(run_dir) == {}


def test_timestamped_runs_never_collide(tmp_path: Path) -> None:
    path = _study(tmp_path, [_PCA], timestamp=True)
    a, b = run_study(path), run_study(path)
    assert a != b
