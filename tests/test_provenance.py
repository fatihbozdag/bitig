"""Tests for the Provenance record."""

from datetime import datetime

from bitig.provenance import Provenance


def test_provenance_basic_construction():
    p = Provenance(
        bitig_version="0.1.0.dev0",
        python_version="3.11.7",
        spacy_model="en_core_web_sm",
        spacy_version="3.7.2",
        corpus_hash="deadbeef",
        feature_hash=None,
        seed=42,
        timestamp=datetime(2026, 4, 17, 12, 0, 0),
        resolved_config={"seed": 42},
    )
    assert p.seed == 42
    assert p.feature_hash is None


def test_provenance_round_trips_to_dict():
    p = Provenance(
        bitig_version="0.1.0.dev0",
        python_version="3.11.7",
        spacy_model="en_core_web_sm",
        spacy_version="3.7.2",
        corpus_hash="abc123",
        feature_hash="feat456",
        seed=7,
        timestamp=datetime(2026, 4, 17, 12, 0, 0),
        resolved_config={"seed": 7, "nested": {"k": "v"}},
    )
    d = p.to_dict()
    restored = Provenance.from_dict(d)
    assert restored == p


def test_provenance_current_captures_runtime():
    p = Provenance.current(
        spacy_model="en_core_web_sm",
        spacy_version="3.7.2",
        corpus_hash="h",
        feature_hash=None,
        seed=1,
        resolved_config={},
    )
    assert p.bitig_version
    assert "." in p.python_version


def test_current_snapshots_resolved_config():
    """resolved_config is deep-copied, so mutating the caller's dict afterwards
    can't retroactively change a captured provenance record (audit P3)."""
    cfg = {"nested": {"k": "v"}}
    p = Provenance.current(
        spacy_model="en_core_web_sm",
        spacy_version="3.7.2",
        corpus_hash="h",
        feature_hash=None,
        seed=1,
        resolved_config=cfg,
    )
    cfg["nested"]["k"] = "MUTATED"
    assert p.resolved_config["nested"]["k"] == "v"
    assert isinstance(p.timestamp, datetime)


def test_provenance_forensic_fields_default_to_none() -> None:
    """The chain-of-custody fields must be optional — existing callers that don't pass
    them get Provenance records identical to the pre-forensic form."""
    p = Provenance.current(
        spacy_model="x",
        spacy_version="1.0",
        corpus_hash="h",
        feature_hash=None,
        seed=0,
        resolved_config={},
    )
    assert p.questioned_description is None
    assert p.known_description is None
    assert p.hypothesis_pair is None
    assert p.acquisition_notes is None
    assert p.custody_notes is None
    assert p.source_hashes == {}
    assert p.has_forensic_metadata is False


def test_provenance_round_trips_forensic_fields() -> None:
    """All forensic fields survive serialisation to/from dict."""
    p = Provenance.current(
        spacy_model="x",
        spacy_version="1.0",
        corpus_hash="h",
        feature_hash=None,
        seed=0,
        resolved_config={},
        questioned_description="email thread seized 2026-04-15",
        known_description="15 personal emails 2024-2026",
        hypothesis_pair="H1: written by suspect; H0: written by someone else",
        acquisition_notes="drive image from warrant A-2026-0412",
        custody_notes="no modifications after acquisition",
        source_hashes={"email_q": "abc123", "email_k1": "def456"},
    )
    assert p.has_forensic_metadata is True
    restored = Provenance.from_dict(p.to_dict())
    assert restored == p


def test_provenance_from_dict_accepts_records_without_forensic_fields() -> None:
    """Backward compatibility — loading a pre-forensic result.json must still work."""
    legacy_payload = {
        "bitig_version": "0.1.0.dev0",
        "python_version": "3.11.7",
        "spacy_model": "en_core_web_sm",
        "spacy_version": "3.7.2",
        "corpus_hash": "abc",
        "feature_hash": None,
        "seed": 1,
        "timestamp": "2026-04-17T12:00:00",
        "resolved_config": {},
        # No forensic fields at all.
    }
    restored = Provenance.from_dict(legacy_payload)
    assert restored.questioned_description is None
    assert restored.source_hashes == {}
    assert restored.has_forensic_metadata is False


def test_has_forensic_metadata_true_when_any_field_populated() -> None:
    base = {
        "spacy_model": "x",
        "spacy_version": "1.0",
        "corpus_hash": "h",
        "feature_hash": None,
        "seed": 0,
        "resolved_config": {},
    }
    # Each individual field alone triggers the flag.
    for extra in (
        {"questioned_description": "Q desc"},
        {"known_description": "K desc"},
        {"hypothesis_pair": "H1 vs H0"},
        {"acquisition_notes": "warrant"},
        {"custody_notes": "sealed"},
        {"source_hashes": {"d": "abc"}},
    ):
        p = Provenance.current(**base, **extra)
        assert p.has_forensic_metadata is True, f"{extra} did not set the flag"
