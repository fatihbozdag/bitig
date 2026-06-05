import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bitig.cli import app

# Force a wide terminal so Rich doesn't hard-wrap error messages across lines
# and fragment the substrings we assert on (see tests/cli/test_case_cmd.py).
os.environ["COLUMNS"] = "200"

runner = CliRunner()
FED = Path(__file__).parent.parent / "fixtures" / "federalist"
pytestmark = pytest.mark.integration


def test_classify_stratified_runs() -> None:
    """The default cv-kind (stratified) actually classifies authors (audit P1.16)."""
    result = runner.invoke(
        app,
        [
            "classify",
            str(FED),
            "--metadata",
            str(FED / "metadata.tsv"),
            "--estimator",
            "logreg",
            "--group-by",
            "author",
            "--mfw",
            "200",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "accuracy" in result.stdout.lower()


def test_classify_loao_grouping_by_target_is_rejected() -> None:
    """cv-kind=loao with groups defaulting to the target is degenerate (~0 accuracy)
    and must be refused with a clear error, not silently scored (audit P1.16)."""
    result = runner.invoke(
        app,
        [
            "classify",
            str(FED),
            "--metadata",
            str(FED / "metadata.tsv"),
            "--group-by",
            "author",
            "--cv-kind",
            "loao",
            "--mfw",
            "200",
        ],
    )
    assert result.exit_code == 1
    # Wrap-robust: assert distinctive single tokens rather than a long phrase.
    flat = "".join(result.stdout.split())
    assert "identicaltotheclassificationtarget" in flat
    assert "LeaveOneGroupOut" in result.stdout
