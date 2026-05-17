"""Tests for the Case signature plugin point (spec §7 step 7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bitig.cases import Case
from bitig.signatures import (
    DEFAULT_SIGNATURE_PLUGIN,
    SIGNATURE_PLUGINS,
    HmacSignaturePlugin,
    NullSignaturePlugin,
    SignaturePlugin,
    get_signature_plugin,
    verify_hmac_signature,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_contains_null_and_hmac():
    assert set(SIGNATURE_PLUGINS) == {"null", "hmac"}


def test_default_plugin_is_null_instance():
    assert isinstance(DEFAULT_SIGNATURE_PLUGIN, NullSignaturePlugin)
    assert DEFAULT_SIGNATURE_PLUGIN.id == "null"


def test_get_signature_plugin_none_returns_default():
    assert get_signature_plugin(None) is DEFAULT_SIGNATURE_PLUGIN
    assert get_signature_plugin("") is DEFAULT_SIGNATURE_PLUGIN


def test_get_signature_plugin_unknown_raises():
    with pytest.raises(KeyError, match="Unknown signature plugin"):
        get_signature_plugin("not_a_plugin")


def test_get_signature_plugin_resolves_null():
    plugin = get_signature_plugin("null")
    assert plugin.id == "null"
    assert isinstance(plugin, NullSignaturePlugin)


def test_get_signature_plugin_resolves_hmac(monkeypatch):
    monkeypatch.setenv("BITIG_SIGNATURE_KEY", "test-key-1234")
    plugin = get_signature_plugin("hmac")
    assert plugin.id == "hmac"
    assert isinstance(plugin, HmacSignaturePlugin)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_null_plugin_satisfies_protocol():
    assert isinstance(NullSignaturePlugin(), SignaturePlugin)


def test_hmac_plugin_satisfies_protocol():
    assert isinstance(HmacSignaturePlugin(key="x"), SignaturePlugin)


# ---------------------------------------------------------------------------
# NullSignaturePlugin behaviour
# ---------------------------------------------------------------------------


def test_null_plugin_passes_payload_through(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="n", title="t", examiner="x", recipe="exploration")
    payload = case.mark_signed(signature_plugin=NullSignaturePlugin())
    assert payload["signature_plugin_id"] == "null"
    assert "signature" not in payload


def test_mark_signed_without_plugin_writes_null_id(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="d", title="t", examiner="x", recipe="exploration")
    payload = case.mark_signed()
    assert payload["signature_plugin_id"] == "null"


# ---------------------------------------------------------------------------
# HmacSignaturePlugin behaviour
# ---------------------------------------------------------------------------


def test_hmac_plugin_requires_key():
    with pytest.raises(ValueError, match="requires a key"):
        HmacSignaturePlugin()


def test_hmac_plugin_reads_env_key(monkeypatch):
    monkeypatch.setenv("BITIG_SIGNATURE_KEY", "abc123")
    plugin = HmacSignaturePlugin()
    assert plugin._key == b"abc123"


def test_hmac_plugin_signs_payload(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="h", title="t", examiner="x", recipe="exploration")
    plugin = HmacSignaturePlugin(key="secret-key")

    payload = case.mark_signed(signature_plugin=plugin)

    assert payload["signature_plugin_id"] == "hmac"
    assert "signature" in payload
    sig = payload["signature"]
    assert sig["algorithm"] == "HMAC-SHA256"
    assert len(sig["value"]) == 64  # SHA-256 hex digest length
    assert len(sig["key_fingerprint"]) == 16

    # The on-disk signed.json matches the returned payload exactly.
    on_disk = json.loads((case.report_dir / "signed.json").read_text(encoding="utf-8"))
    assert on_disk == payload


def test_hmac_signature_verifies_with_same_key(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="v", title="t", examiner="x", recipe="exploration")
    payload = case.mark_signed(signature_plugin=HmacSignaturePlugin(key="my-key"))
    assert verify_hmac_signature(payload, key="my-key") is True


def test_hmac_signature_fails_with_different_key(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="vd", title="t", examiner="x", recipe="exploration")
    payload = case.mark_signed(signature_plugin=HmacSignaturePlugin(key="real-key"))
    assert verify_hmac_signature(payload, key="wrong-key") is False


def test_hmac_signature_fails_when_case_state_tampered(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="vt", title="t", examiner="x", recipe="exploration")
    payload = case.mark_signed(signature_plugin=HmacSignaturePlugin(key="k"))

    tampered = dict(payload)
    tampered["case_state_hash"] = "deadbeef" * 8
    assert verify_hmac_signature(tampered, key="k") is False


def test_verify_returns_false_on_missing_signature():
    assert verify_hmac_signature({"case_state_hash": "x"}, key="any") is False


# ---------------------------------------------------------------------------
# Case.record persists the plugin id across reload
# ---------------------------------------------------------------------------


def test_signature_plugin_id_round_trips(tmp_path: Path):
    case = Case.create(tmp_path / "cases", id="rt", title="t", examiner="x", recipe="exploration")
    case.mark_signed(signature_plugin=HmacSignaturePlugin(key="k"))

    reloaded = Case.load(case.root)
    assert reloaded.record.signature_plugin_id == "hmac"
    assert reloaded.record.signed is True


# ---------------------------------------------------------------------------
# Custom plugin — verify the extension surface
# ---------------------------------------------------------------------------


class _AuditTrailPlugin:
    """Demonstrates the extension surface: stamps a custom audit field."""

    id: str = "audit-trail-test"

    def sign(self, payload, *, case):
        out = dict(payload)
        out["audit_trail"] = {"case_id": case.record.id, "examiner": case.record.examiner}
        return out


def test_custom_plugin_can_augment_payload(tmp_path: Path):
    case = Case.create(
        tmp_path / "cases",
        id="aud",
        title="t",
        examiner="Inspector Lestrade",
        recipe="exploration",
    )
    payload = case.mark_signed(signature_plugin=_AuditTrailPlugin())

    assert payload["signature_plugin_id"] == "audit-trail-test"
    assert payload["audit_trail"]["case_id"] == "aud"
    assert payload["audit_trail"]["examiner"] == "Inspector Lestrade"
