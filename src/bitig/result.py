"""The Result record — uniform return type from every analytical method."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from bitig.provenance import Provenance


@dataclass
class Result:
    method_name: str
    params: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    tables: list[pd.DataFrame] = field(default_factory=list)
    figures: list[Any] = field(default_factory=list)
    provenance: Provenance | None = None

    def to_json(self, path: str | Path) -> None:
        """Persist params + values + provenance to a single JSON file.

        ndarray values are encoded as `{"__ndarray__": list, "shape": ..., "dtype": ...}` so they
        round-trip exactly.
        """
        payload = {
            "method_name": self.method_name,
            "params": _encode(self.params),
            "values": _encode(self.values),
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }
        # Atomic write so an interrupted save can't leave a truncated result.json.
        path = Path(path)
        tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        try:
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    @classmethod
    def from_json(cls, path: str | Path) -> Result:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            method_name=data["method_name"],
            params=_decode(data["params"]),
            values=_decode(data["values"]),
            tables=[],
            figures=[],
            provenance=Provenance.from_dict(data["provenance"]) if data["provenance"] else None,
        )

    def save(self, directory: str | Path) -> Path:
        """Persist everything to `directory/`: result.json, tables as parquet, figures deferred to viz layer."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.to_json(directory / "result.json")
        for i, df in enumerate(self.tables):
            df.to_parquet(directory / f"table_{i}.parquet")
        return directory


def _encode(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_encode(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return {
            "__ndarray__": obj.tolist(),
            "shape": list(obj.shape),
            "dtype": str(obj.dtype),
        }
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer | np.floating):
        return obj.item()
    return obj


def _decode(obj: Any) -> Any:
    if isinstance(obj, dict):
        # Only treat as our ndarray encoding when the full sentinel triple is
        # present — a user value dict that merely happens to contain a
        # "__ndarray__" key must decode as a plain dict, not crash (audit P3).
        if "__ndarray__" in obj and "shape" in obj and "dtype" in obj:
            arr = np.array(obj["__ndarray__"], dtype=obj["dtype"])
            return arr.reshape(obj["shape"])
        return {k: _decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode(v) for v in obj]
    return obj
