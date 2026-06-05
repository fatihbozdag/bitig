"""Tests for the Result record."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from bitig.provenance import Provenance
from bitig.result import Result


def _prov() -> Provenance:
    return Provenance(
        bitig_version="0.1.0.dev0",
        python_version="3.11.7",
        spacy_model="en_core_web_sm",
        spacy_version="3.7.2",
        corpus_hash="c",
        feature_hash=None,
        seed=42,
        timestamp=datetime(2026, 4, 17, 12, 0, 0),
        resolved_config={},
    )


def test_to_json_encodes_numpy_bool(tmp_path) -> None:
    """np.bool_ scalars must JSON-encode (audit P2): they previously fell
    through _encode and made to_json() raise so result.json was never written."""
    r = Result(
        method_name="verify",
        values={"is_match": np.bool_(True), "flags": np.array([True, False])},
    )
    out = tmp_path / "result.json"
    r.to_json(out)  # must not raise
    restored = Result.from_json(out)
    assert restored.values["is_match"] is True
    assert list(restored.values["flags"]) == [True, False]


def test_result_basic_construction() -> None:
    r = Result(
        method_name="burrows_delta",
        params={"method": "burrows"},
        values={"distances": np.zeros((2, 2))},
        tables=[pd.DataFrame({"a": [1]})],
        figures=[],
        provenance=_prov(),
    )
    assert r.method_name == "burrows_delta"
    assert "distances" in r.values


def test_result_to_json_round_trip(tmp_path) -> None:
    r = Result(
        method_name="test",
        params={"k": 1},
        values={"labels": ["A", "B"], "matrix": np.array([[1.0, 2.0], [3.0, 4.0]])},
        tables=[],
        figures=[],
        provenance=_prov(),
    )
    path = tmp_path / "result.json"
    r.to_json(path)
    restored = Result.from_json(path)
    assert restored.method_name == "test"
    assert restored.params == {"k": 1}
    np.testing.assert_array_equal(restored.values["matrix"], r.values["matrix"])


def test_result_save_writes_tables_and_json(tmp_path) -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    r = Result(
        method_name="demo",
        params={},
        values={},
        tables=[df],
        figures=[],
        provenance=_prov(),
    )
    r.save(tmp_path)
    assert (tmp_path / "result.json").is_file()
    assert (tmp_path / "table_0.parquet").is_file()
    # Restored table round-trips.
    restored = pd.read_parquet(tmp_path / "table_0.parquet")
    pd.testing.assert_frame_equal(restored, df)
