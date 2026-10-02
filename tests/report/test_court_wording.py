"""Court-facing wording regressions (audit 2026-09-26 N-P1.8, N-P1.9, N-P1.12)."""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from bitig.cases import Case
from bitig.forensic.verbal_scale import LR_LADDER
from bitig.report.case_report import build_case_report
from bitig.report.render import build_forensic_report
from bitig.report.scalars import gi_score, headline_scalars, latest_result_path
from bitig.result import Result

EN_DASH = "\u2013"
_DOCS = Path(__file__).resolve().parents[2] / "docs" / "site" / "forensic"


def _forensic_case(tmp_path: Path) -> Case:
    return Case.create(tmp_path / "c", id="f", title="t", examiner="x", recipe="imposters_lr")


def _attach(case: Case, method_id: str, values: dict) -> None:
    run_id = "2026-01-01T00-00-00Z"
    d = case.runs_dir / run_id / method_id
    d.mkdir(parents=True, exist_ok=True)
    Result(method_name="general_imposters", values=values).to_json(d / "result.json")
    if case.record.latest_run != run_id:
        case.register_run(run_id)


_TWO_DOCS = {"candidate": "A", "chance": 0.5, "scores": {"qa": 1.0, "qb": 0.0}}


def test_several_questioned_documents_are_never_collapsed_to_the_max(tmp_path: Path) -> None:
    case = _forensic_case(tmp_path)
    assert gi_score(_TWO_DOCS) is None
    label, value, _ = headline_scalars(case, Result(method_name="gi", values=_TWO_DOCS))[0]
    assert label == "GI score" and "see per-document table" in value
    _attach(case, "verify", _TWO_DOCS)
    html = build_case_report(case).read_text(encoding="utf-8")
    assert re.search(r"<td>qa</td><td[^>]*>1</td>", html)
    assert re.search(r"<td>qb</td><td[^>]*>0</td>", html)


def test_gi_report_never_calls_the_score_a_likelihood_ratio(tmp_path: Path) -> None:
    case = _forensic_case(tmp_path)
    _attach(case, "verify", {"candidate": "A", "chance": 0.5, "scores": {"q": 0.8}})
    html = build_case_report(case).read_text(encoding="utf-8")
    assert "likelihood ratio above" not in html
    assert "not a likelihood ratio" in html  # disclaimer is in the sealed template
    assert "H<sub>p</sub>" not in html
    assert "chance level" in html


def test_lr_report_keeps_hypotheses_and_lr_wording(tmp_path: Path) -> None:
    case = _forensic_case(tmp_path)
    _attach(case, "verify", {"lr": 50.0})
    html = build_case_report(case).read_text(encoding="utf-8")
    assert "H<sub>p</sub>" in html
    assert "likelihood ratio above" in html


def test_headline_result_is_chosen_by_method_kind(tmp_path: Path) -> None:
    case = _forensic_case(tmp_path)
    _attach(case, "aaa_other", {"x": 1})  # sorts before 'verify'
    _attach(case, "verify", {"candidate": "A", "scores": {"q": 0.7}})
    path = latest_result_path(case)
    assert path is not None and path.parent.name == "verify"


@pytest.mark.parametrize(
    ("log_lr", "rung"), [("5.5", "very strong support"), ("6.2", "extremely strong support")]
)
def test_forensic_lr_report_statement_follows_lr_ladder(
    tmp_path: Path, log_lr: str, rung: str
) -> None:
    res_dir = tmp_path / "res" / "m"
    res_dir.mkdir(parents=True)
    Result(method_name="general_impostors", values={}).to_json(res_dir / "result.json")
    out = build_forensic_report(
        tmp_path / "res",
        output=tmp_path / "r.html",
        lr_summaries={"general_impostors": {"log_lr": log_lr, "lr": "x"}},
    )
    html = out.read_text(encoding="utf-8")
    assert f"{rung} for the prosecution proposition" in html
    assert f"4{EN_DASH}5 very strong" not in html
    for label, lo, hi in LR_LADDER:
        hi_txt = "∞" if math.isinf(hi) else str(int(hi))
        assert f"{label} {int(lo)}{EN_DASH}{hi_txt}" in html


@pytest.mark.parametrize("doc", ["reporting.md", "calibration.md", "calibration.tr.md"])
def test_docs_verbal_scale_tables_match_lr_ladder(doc: str) -> None:
    """The docs tables must state the same bands as LR_LADDER (in |log10 LR|)."""
    text = (_DOCS / doc).read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\d) \u2013 (\d) \|", text, re.M)
    open_row = re.search(r"^\| ≥ (\d) \|", text, re.M)
    assert open_row is not None
    expected = [
        (str(round(math.log10(lo))), str(round(math.log10(hi))))
        for _, lo, hi in LR_LADDER
        if not math.isinf(hi)
    ]
    assert rows == expected
    assert open_row.group(1) == str(round(math.log10(LR_LADDER[-1][1])))
