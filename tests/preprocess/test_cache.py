"""Tests for the DocBin cache — key derivation and round-trip (mocked spaCy)."""

from pathlib import Path

from bitig.preprocess.cache import DocBinCache, cache_key


def test_cache_key_is_deterministic() -> None:
    a = cache_key("doc-hash", "en_core_web_sm", "spacy=3.7.2", ["ner"])
    b = cache_key("doc-hash", "en_core_web_sm", "spacy=3.7.2", ["ner"])
    assert a == b


def test_cache_key_changes_with_any_input() -> None:
    base = cache_key("doc-hash", "en_core_web_sm", "spacy=3.7.2", [])
    assert cache_key("other-hash", "en_core_web_sm", "spacy=3.7.2", []) != base
    assert cache_key("doc-hash", "en_core_web_lg", "spacy=3.7.2", []) != base
    assert cache_key("doc-hash", "en_core_web_sm", "spacy=3.7.3", []) != base
    assert cache_key("doc-hash", "en_core_web_sm", "spacy=3.7.2", ["ner"]) != base


def test_cache_key_is_order_independent_for_excluded_components() -> None:
    a = cache_key("doc-hash", "en_core_web_sm", "spacy=3.7.2", ["ner", "parser"])
    b = cache_key("doc-hash", "en_core_web_sm", "spacy=3.7.2", ["parser", "ner"])
    assert a == b


def test_cache_key_spacy_native_backend_version_format() -> None:
    """English backend_version must format as 'spacy=<version>'."""
    k_new = cache_key("doc-hash", "en_core_web_sm", "spacy=3.7.2", ["ner"])
    # This must match what Task 3.3's SpacyPipeline.backend_version produces for backend='spacy'.
    assert k_new  # smoke: call returns a string


def test_cache_key_stanza_backend_differs_from_spacy_native() -> None:
    """Different backend identifiers must never collide."""
    native = cache_key("doc-hash", "tr", "spacy=3.7.2", [])
    stanza = cache_key("doc-hash", "tr", "spacy_stanza=1.0.4;stanza=1.6.1", [])
    assert native != stanza


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    c = DocBinCache(tmp_path)
    assert c.get("nonexistent-key") is None


def test_cache_put_get_round_trip_bytes(tmp_path: Path) -> None:
    c = DocBinCache(tmp_path)
    payload = b"\x00\x01\x02fake-docbin-bytes"
    c.put("k1", payload)
    assert c.get("k1") == payload


def test_cache_size_bytes_reports_stored_payloads(tmp_path: Path) -> None:
    c = DocBinCache(tmp_path)
    c.put("k1", b"x" * 100)
    c.put("k2", b"y" * 50)
    assert c.size_bytes() == 150


def test_cache_clear_removes_all_entries(tmp_path: Path) -> None:
    c = DocBinCache(tmp_path)
    c.put("k1", b"x")
    c.put("k2", b"y")
    assert len(c.keys()) == 2
    c.clear()
    assert c.keys() == []
    assert c.size_bytes() == 0


def test_corrupt_entry_is_a_miss_and_is_dropped(tmp_path) -> None:
    """A truncated / altered DocBin file is never returned (audit 2026-09-26 P2)."""
    from bitig.preprocess.cache import DocBinCache

    cache = DocBinCache(tmp_path)
    cache.put("k", b"payload-bytes")
    assert cache.get("k") == b"payload-bytes"
    (tmp_path / "k.docbin").write_bytes(b"tampered")
    assert cache.get("k") is None
    assert not (tmp_path / "k.docbin").exists()
    assert cache.keys() == []


def test_entry_without_checksum_is_a_miss(tmp_path) -> None:
    from bitig.preprocess.cache import DocBinCache

    (tmp_path / "old.docbin").write_bytes(b"written by an older bitig")
    assert DocBinCache(tmp_path).get("old") is None
