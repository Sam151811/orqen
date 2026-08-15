"""Attestation.

A passport is a public URL with no login. That is the point - and it means
anyone can screenshot one, edit the numbers, and forward it. For a document
whose whole purpose is to be trusted by someone who did not run the audit, that
is a real gap.

Signing closes it. Each passport carries a detached Ed25519 signature over a
canonical serialisation of its own content. The public key is published at a
well-known URL, so verification needs nothing from Orqen but the document and
the key - a third party can check a passport with twenty lines of Python and no
access to this service at all.

What this does and does not establish:

  it does establish   that the document was issued by the holder of this key and
                      has not been altered since
  it does not establish
                      that the measurements are correct, that the gateway
                      returned honest responses, or that the key holder is
                      trustworthy. A signature is provenance, not truth.

Key handling is deliberately blunt: one key, from the environment, no rotation,
no revocation list. Real attestation infrastructure has all three. Saying so
here is better than implying otherwise by omission.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey)
    AVAILABLE = True
except ImportError:  # pragma: no cover
    AVAILABLE = False

ALG = "ed25519"
SIG_FIELD = "attestation"

# Fields excluded from the signed payload: they are metadata about delivery
# rather than content, and including them would make an identical passport
# verify differently depending on how it was fetched.
EXCLUDE = {SIG_FIELD, "drift"}

_key: "Ed25519PrivateKey | None" = None
_ephemeral = False


def _load() -> "Ed25519PrivateKey | None":
    """ORQEN_SIGNING_KEY is a base64 32-byte Ed25519 seed.

    Absent one, an ephemeral key is generated so the feature is exercised in
    development - but passports say so, because a signature from a key that dies
    with the process attests to nothing.
    """
    global _key, _ephemeral
    if not AVAILABLE or _key is not None:
        return _key
    raw = os.getenv("ORQEN_SIGNING_KEY", "").strip()
    if raw:
        try:
            _key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw))
            _ephemeral = False
            return _key
        except Exception:  # noqa: BLE001 - a bad key must not stop the service
            pass
    _key = Ed25519PrivateKey.generate()
    _ephemeral = True
    return _key


def generate_key() -> str:
    """Print a key to put in the environment: python -m orqen.attest"""
    k = Ed25519PrivateKey.generate()
    return base64.b64encode(k.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())).decode()


def public_key_b64() -> str | None:
    k = _load()
    if k is None:
        return None
    return base64.b64encode(k.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)).decode()


def key_id() -> str | None:
    pk = public_key_b64()
    return hashlib.sha256(pk.encode()).hexdigest()[:16] if pk else None


def canonical(passport: dict) -> bytes:
    """Deterministic bytes for a passport.

    Sorted keys, no insignificant whitespace, UTF-8. Any verifier that follows
    this rule reproduces the same bytes; the rule is short enough to restate in
    a paragraph, which matters more than using a formal canonicalisation spec
    nobody will implement.
    """
    body = {k: v for k, v in passport.items() if k not in EXCLUDE}
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str).encode("utf-8")


def sign(passport: dict) -> dict | None:
    k = _load()
    if k is None:
        return None
    payload = canonical(passport)
    return {
        "alg": ALG,
        "key_id": key_id(),
        "public_key": public_key_b64(),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "signature": base64.b64encode(k.sign(payload)).decode(),
        "ephemeral_key": _ephemeral,
        "canonicalisation": ("JSON with sorted keys, separators ',' and ':', "
                             "UTF-8, excluding the attestation and drift fields"),
    }


def verify(passport: dict) -> dict:
    """Check a passport against its own attestation. Never raises."""
    att = passport.get(SIG_FIELD)
    if not att:
        return {"verified": False, "reason": "this passport carries no attestation"}
    if not AVAILABLE:
        return {"verified": False,
                "reason": "signature support is not installed on this instance"}
    try:
        payload = canonical(passport)
        digest = hashlib.sha256(payload).hexdigest()
        if att.get("payload_sha256") != digest:
            return {"verified": False, "key_id": att.get("key_id"),
                    "reason": "content does not match the signed digest; the "
                              "document has been altered since it was issued"}
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(att["public_key"]))
        pub.verify(base64.b64decode(att["signature"]), payload)
    except Exception as exc:  # noqa: BLE001
        return {"verified": False, "key_id": att.get("key_id"),
                "reason": f"signature check failed: {type(exc).__name__}"}

    return {
        "verified": True,
        "key_id": att.get("key_id"),
        "ephemeral_key": att.get("ephemeral_key", False),
        "caveat": ("Confirms the document was issued by the holder of this key "
                   "and is unaltered. It does not confirm the measurements are "
                   "correct."),
    }


if __name__ == "__main__":  # pragma: no cover
    print(generate_key())
