"""The Provenance record — captured on every Result so re-runs are fully reproducible.

Forensic use adds a chain-of-custody layer on top of the software/corpus hashing: optional
fields capturing *which* documents count as "known" vs. "questioned", the hypothesis pair
being tested, how the source material was acquired, and free-text custody notes. These are
the metadata courts and forensic-linguistic journals (IJSLL, *Language and Law*) expect for
a submission to be traceable back to source material.

All forensic fields are ``Optional``; analyses that are not forensic in intent just omit them
and the record is unchanged from its pre-forensic form.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import platform
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bitig._version import __version__
from bitig.corpus.corpus import CORPUS_HASH_SCHEME

_TRACKED_LIBRARIES = ("numpy", "scipy", "scikit-learn", "pandas", "textstat", "nltk", "pyphen")


@functools.lru_cache(maxsize=1)
def library_versions() -> dict[str, str]:
    """Installed versions of result-shaping libraries, plus a cmudict checksum if present."""
    from importlib import metadata

    out: dict[str, str] = {}
    for name in _TRACKED_LIBRARIES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    try:
        import nltk
    except ImportError:
        return dict(out)
    for root in nltk.data.path:
        zip_path = Path(root) / "corpora" / "cmudict.zip"
        if zip_path.is_file():
            out["nltk_data:cmudict.zip sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            break
    return dict(out)


@dataclass
class Provenance:
    bitig_version: str
    python_version: str
    spacy_model: str
    spacy_version: str
    corpus_hash: str
    feature_hash: str | None
    seed: int
    timestamp: datetime
    resolved_config: dict[str, Any]
    # --- Forensic chain-of-custody (optional) ---
    questioned_description: str | None = None
    known_description: str | None = None
    hypothesis_pair: str | None = None
    acquisition_notes: str | None = None
    custody_notes: str | None = None
    source_hashes: dict[str, str] = field(default_factory=dict)
    # Which Corpus.hash scheme produced corpus_hash; records written before the
    # field existed used scheme 1, whose hash is not comparable (N-P1.16).
    corpus_hash_scheme: int = 1
    # Versions of the libraries whose behaviour shapes results, and checksums of
    # data they load (e.g. NLTK's cmudict for English syllables).
    library_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        raw_ts = data["timestamp"]
        ts = datetime.fromisoformat(raw_ts) if isinstance(raw_ts, str) else raw_ts
        return cls(
            bitig_version=data["bitig_version"],
            python_version=data["python_version"],
            spacy_model=data["spacy_model"],
            spacy_version=data["spacy_version"],
            corpus_hash=data["corpus_hash"],
            feature_hash=data.get("feature_hash"),
            seed=int(data["seed"]),
            timestamp=ts,
            resolved_config=dict(data.get("resolved_config") or {}),
            questioned_description=data.get("questioned_description"),
            known_description=data.get("known_description"),
            hypothesis_pair=data.get("hypothesis_pair"),
            acquisition_notes=data.get("acquisition_notes"),
            custody_notes=data.get("custody_notes"),
            source_hashes=dict(data.get("source_hashes") or {}),
            corpus_hash_scheme=int(data.get("corpus_hash_scheme", 1)),
            library_versions=dict(data.get("library_versions") or {}),
        )

    @classmethod
    def current(
        cls,
        *,
        spacy_model: str,
        spacy_version: str,
        corpus_hash: str,
        feature_hash: str | None,
        seed: int,
        resolved_config: dict[str, Any],
        questioned_description: str | None = None,
        known_description: str | None = None,
        hypothesis_pair: str | None = None,
        acquisition_notes: str | None = None,
        custody_notes: str | None = None,
        source_hashes: dict[str, str] | None = None,
    ) -> Provenance:
        return cls(
            bitig_version=__version__,
            python_version=platform.python_version(),
            spacy_model=spacy_model,
            spacy_version=spacy_version,
            corpus_hash=corpus_hash,
            feature_hash=feature_hash,
            seed=seed,
            timestamp=datetime.now(UTC),
            # Snapshot the config so later mutation of the caller's dict can't
            # retroactively change a captured provenance record (audit P3).
            resolved_config=copy.deepcopy(resolved_config),
            questioned_description=questioned_description,
            known_description=known_description,
            hypothesis_pair=hypothesis_pair,
            acquisition_notes=acquisition_notes,
            custody_notes=custody_notes,
            source_hashes=dict(source_hashes) if source_hashes else {},
            corpus_hash_scheme=CORPUS_HASH_SCHEME,
            library_versions=library_versions(),
        )

    @property
    def has_forensic_metadata(self) -> bool:
        """True if any chain-of-custody field has been populated."""
        return any(
            (
                self.questioned_description,
                self.known_description,
                self.hypothesis_pair,
                self.acquisition_notes,
                self.custody_notes,
                self.source_hashes,
            )
        )
