from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from bitig.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent.parent / "fixtures" / "mini_corpus"


pytestmark = pytest.mark.slow
pytest.importorskip("sentence_transformers", reason="requires bitig[embeddings]")


def test_embed_writes_parquet(tmp_path: Path) -> None:
    out = tmp_path / "emb.parquet"
    result = runner.invoke(
        app,
        [
            "embed",
            str(FIXTURES),
            "--model",
            "sentence-transformers/all-MiniLM-L6-v2",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    df = pd.read_parquet(out)
    assert df.shape == (4, 384)
