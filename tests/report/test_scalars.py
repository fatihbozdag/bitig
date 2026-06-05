"""Tests for the shared headline-scalar derivation (audit P1.10a)."""

from __future__ import annotations

from pathlib import Path

from bitig.cases import Case
from bitig.report.scalars import headline_scalars
from bitig.result import Result


def _forensic_case(tmp_path: Path) -> Case:
    return Case.create(tmp_path / "c", id="f", title="t", examiner="x", recipe="imposters_lr")


def _research_case(tmp_path: Path) -> Case:
    return Case.create(tmp_path / "c", id="r", title="t", examiner="x", recipe="exploration")


def test_forensic_headline_uses_gi_score_never_candidate_name(tmp_path: Path) -> None:
    """A General Impostors result has no LR — the headline must show the numeric
    GI score, never the candidate's NAME falling out of next(iter(values))."""
    case = _forensic_case(tmp_path)
    result = Result(
        method_name="verify",
        values={
            "candidate": "suspect_A",
            "imposters": ["x", "y"],
            "threshold": 0.5,
            "scores": {"suspect_A": 0.83},
        },
    )
    label, value, primary = headline_scalars(case, result)[0]
    assert label == "GI score"
    assert value == "0.83"
    assert "suspect_A" not in value
    assert primary


def test_forensic_headline_shows_lr_when_present(tmp_path: Path) -> None:
    case = _forensic_case(tmp_path)
    result = Result(method_name="verify", values={"lr": 250.0, "auc": 0.91})
    scalars = headline_scalars(case, result)
    assert scalars[0] == ("LR", "250", True)
    assert ("AUC", "0.91", False) in scalars


def test_research_headline_pca(tmp_path: Path) -> None:
    case = _research_case(tmp_path)
    result = Result(method_name="pca", values={"explained_variance_ratio": [0.6, 0.3]})
    labels = [label for label, _v, _p in headline_scalars(case, result)]
    assert labels[:2] == ["PC1 var", "PC2 var"]


def test_headline_no_result_placeholder(tmp_path: Path) -> None:
    case = _research_case(tmp_path)
    assert headline_scalars(case, None) == [("status", "no run yet", True)]
