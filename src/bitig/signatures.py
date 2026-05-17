"""Signature plugin point for ``Case.mark_signed`` (spec §6 last paragraph).

Sign & lock in bitig is a chain-of-custody anchor: it freezes the Case,
writes ``report/signed.json`` with the canonical state hash, and stamps
the PDF footer. That's enough for an analyst to defend the artefact
against later tampering, because anyone re-running the same Case must
produce the same hashes.

A *signature plugin* wraps that anchor with an additional cryptographic
binding — for example, a hardware-key digital signature over the
``case_state_hash``. The spec calls this out as a future extension point;
this module implements the framework so concrete plugins (PGP, PIV,
HSM-backed keys, …) can be added without touching ``bitig.cases``.

Built-in plugins:
* :class:`NullSignaturePlugin` — default. Passes the payload through
  untouched. ``mark_signed`` behaves exactly as before.
* :class:`HmacSignaturePlugin` — pure-stdlib demonstration. Computes an
  HMAC-SHA256 over ``case_state_hash + report_html_hash`` with a shared
  secret loaded from ``BITIG_SIGNATURE_KEY`` (or passed at construction).
  Useful for CI / internal audit pipelines; not a substitute for an
  HSM-backed signature in adversarial settings.

Registry:
* :data:`SIGNATURE_PLUGINS` maps short ids ("null", "hmac") to factories.
* :func:`get_signature_plugin` resolves a string id (e.g. from the CLI's
  ``--signature-plugin`` flag) to a plugin instance, raising
  :exc:`KeyError` for unknown ids.

A plugin's ``sign(payload, *, case)`` may either mutate ``payload`` in
place or return a new dict; ``Case.mark_signed`` uses the returned dict
as the canonical ``signed.json`` content.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from bitig.cases import Case


SignaturePayload = dict[str, Any]


@runtime_checkable
class SignaturePlugin(Protocol):
    """Implementors wrap the unsigned ``signed.json`` payload.

    The protocol intentionally permits in-place mutation OR returning a
    fresh dict; either is fine. ``id`` is what gets written to
    ``case.json`` so reloads can record which plugin produced the
    signature.
    """

    id: str

    def sign(self, payload: SignaturePayload, *, case: Case) -> SignaturePayload: ...


# ---------------------------------------------------------------------------
# Built-ins
# ---------------------------------------------------------------------------


class NullSignaturePlugin:
    """Default plugin — leaves ``payload`` untouched.

    Calling ``mark_signed`` with this plugin (the default) is identical
    to the chain-of-custody-only behaviour bitig has had since the Case
    model landed.
    """

    id: str = "null"

    def sign(self, payload: SignaturePayload, *, case: Case) -> SignaturePayload:
        return payload


class HmacSignaturePlugin:
    """HMAC-SHA256 signature over the case state hash + report HTML hash.

    The key may be passed at construction or read from the
    ``BITIG_SIGNATURE_KEY`` environment variable. The signed payload
    gains a top-level ``"signature"`` block::

        {
          "signature": {
            "algorithm": "HMAC-SHA256",
            "key_fingerprint": "<sha256(key)[:16]>",
            "value": "<hex digest>"
          }
        }

    This is a demonstration, not a substitute for a hardware-backed
    signature. The key fingerprint helps a verifier match the signature
    to a known key without disclosing the key itself.
    """

    id: str = "hmac"

    def __init__(self, key: bytes | str | None = None) -> None:
        if key is None:
            env_key = os.environ.get("BITIG_SIGNATURE_KEY")
            if not env_key:
                raise ValueError(
                    "HmacSignaturePlugin requires a key — pass one to __init__ "
                    "or set BITIG_SIGNATURE_KEY in the environment."
                )
            key = env_key
        if isinstance(key, str):
            key = key.encode("utf-8")
        self._key: bytes = key

    def sign(self, payload: SignaturePayload, *, case: Case) -> SignaturePayload:
        message_parts = [
            str(payload.get("case_state_hash", "")),
            str(payload.get("report_html_hash") or ""),
            str(payload.get("signed_at", "")),
        ]
        message = "\n".join(message_parts).encode("utf-8")
        digest = hmac.new(self._key, message, hashlib.sha256).hexdigest()
        fingerprint = hashlib.sha256(self._key).hexdigest()[:16]

        out = dict(payload)
        out["signature"] = {
            "algorithm": "HMAC-SHA256",
            "key_fingerprint": fingerprint,
            "value": digest,
        }
        return out


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


SIGNATURE_PLUGINS: dict[str, Callable[[], SignaturePlugin]] = {
    "null": NullSignaturePlugin,
    "hmac": HmacSignaturePlugin,
}
"""Public registry. Keys match the ``--signature-plugin`` CLI flag."""


DEFAULT_SIGNATURE_PLUGIN: SignaturePlugin = NullSignaturePlugin()
"""Used by :meth:`bitig.cases.Case.mark_signed` when no plugin is passed."""


def get_signature_plugin(plugin_id: str | None) -> SignaturePlugin:
    """Resolve a string id to a plugin instance.

    Passing ``None`` returns the default (null) plugin. Unknown ids
    raise :class:`KeyError` with a helpful list of valid options.
    """
    if plugin_id is None or plugin_id == "":
        return DEFAULT_SIGNATURE_PLUGIN
    if plugin_id not in SIGNATURE_PLUGINS:
        raise KeyError(
            f"Unknown signature plugin {plugin_id!r}. Known: {sorted(SIGNATURE_PLUGINS)}"
        )
    return SIGNATURE_PLUGINS[plugin_id]()


def verify_hmac_signature(signed_payload: SignaturePayload, *, key: bytes | str) -> bool:
    """Standalone verifier for HMAC-signed payloads.

    Returns True iff the payload's signature value matches a fresh
    HMAC-SHA256 over the same ``(case_state_hash, report_html_hash,
    signed_at)`` triple using ``key``. False on missing signature, key
    mismatch, or tampered fields.
    """
    sig = signed_payload.get("signature")
    if not isinstance(sig, dict) or sig.get("algorithm") != "HMAC-SHA256":
        return False
    if isinstance(key, str):
        key = key.encode("utf-8")
    message_parts = [
        str(signed_payload.get("case_state_hash", "")),
        str(signed_payload.get("report_html_hash") or ""),
        str(signed_payload.get("signed_at", "")),
    ]
    message = "\n".join(message_parts).encode("utf-8")
    expected = hmac.new(key, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(sig.get("value", "")))


__all__ = [
    "DEFAULT_SIGNATURE_PLUGIN",
    "SIGNATURE_PLUGINS",
    "HmacSignaturePlugin",
    "NullSignaturePlugin",
    "SignaturePayload",
    "SignaturePlugin",
    "get_signature_plugin",
    "verify_hmac_signature",
]
