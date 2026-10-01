"""Content-addressable cache for spaCy `DocBin` blobs.

Keyed by `(document_hash, spacy_model, backend_version, sorted_excluded_components)`. At this stage
the cache stores raw bytes — Task 13 will wire up `DocBin` serialisation on top.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path

from bitig.plumbing.hashing import hash_mapping

_log = logging.getLogger(__name__)


def cache_key(
    document_hash: str,
    spacy_model: str,
    backend_version: str,
    excluded_components: list[str],
) -> str:
    """Return a stable cache key for a (document, backend configuration) pair.

    `backend_version` is a structured string like 'spacy=3.7.2' (native spaCy backend) or
    'spacy_stanza=1.0.4;stanza=1.6.1' (Stanza-via-spacy-stanza backend). The native branch
    preserves the prior format so English caches built on older bitig versions remain valid.
    """
    return hash_mapping(
        {
            "doc": document_hash,
            "model": spacy_model,
            "version": backend_version,
            "exclude": sorted(excluded_components),
        }
    )


class DocBinCache:
    """Directory-backed cache. One file per key, named `<key>.docbin`.

    Each entry has a ``<key>.docbin.sha256`` sidecar written with it; ``get``
    returns ``None`` (a cache miss) and drops the entry if the bytes no longer
    match, and writes are atomic, so a truncated or altered file is never
    deserialised (audit 2026-09-26 P2).
    """

    _EXT = ".docbin"
    _SIDECAR = ".sha256"

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}{self._EXT}"

    def _sidecar(self, key: str) -> Path:
        return self.directory / f"{key}{self._EXT}{self._SIDECAR}"

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        sidecar = self._sidecar(key)
        if not p.is_file() or not sidecar.is_file():
            return None
        payload = p.read_bytes()
        if hashlib.sha256(payload).hexdigest() != sidecar.read_text(encoding="ascii").strip():
            _log.warning("dropping corrupt DocBin cache entry %s (checksum mismatch)", p.name)
            p.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            return None
        return payload

    def put(self, key: str, payload: bytes) -> None:
        self._atomic_write(self._path(key), payload)
        self._atomic_write(self._sidecar(key), hashlib.sha256(payload).hexdigest().encode("ascii"))

    def _atomic_write(self, path: Path, data: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def keys(self) -> list[str]:
        return sorted(f.stem for f in self.directory.glob(f"*{self._EXT}"))

    def size_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.directory.glob(f"*{self._EXT}"))

    def clear(self) -> None:
        for pattern in (f"*{self._EXT}", f"*{self._EXT}{self._SIDECAR}"):
            for f in self.directory.glob(pattern):
                f.unlink()
