"""Companion envelope v1 (Integration Spec §11.2): authenticated encryption from the standard library only.

* keys:   enc = HMAC(master, "aiwb-companion-enc-v1"), mac = HMAC(master, "aiwb-companion-mac-v1")
* cipher: keystream block i = HMAC(enc, nonce || uint32_be(i)) (HMAC-SHA256 as a PRF in CTR mode)
* MAC:    HMAC(mac, "v1|kid|ts|nonce|re|ct") over the ciphertext (encrypt-then-MAC), constant-time check
* replay: 16-byte random nonce + timestamp window; the receiver remembers nonces (see service.py)

The Android client implements the same construction (CompanionCrypto.kt); both are checked against
packages/contracts/vectors/companion-envelope.v1.json.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

VERSION = 1
MAX_SKEW_SECONDS = 300
_FIELDS = ("v", "kid", "ts", "nonce", "re", "ct", "mac")


class EnvelopeError(ValueError):
    """Authentication/format failure; the message never contains key material."""


def b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64d(text: str) -> bytes:
    if not isinstance(text, str) or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in text):
        raise EnvelopeError("bad base64url")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _h(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def _keys(master: bytes) -> tuple[bytes, bytes]:
    return _h(master, b"aiwb-companion-enc-v1"), _h(master, b"aiwb-companion-mac-v1")


def _xor_stream(key: bytes, nonce: bytes, data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while len(out) < len(data):
        out += _h(key, nonce + i.to_bytes(4, "big"))
        i += 1
    return bytes(a ^ b for a, b in zip(data, out))


def _mac_input(env: dict[str, Any]) -> bytes:
    return f"v1|{env['kid']}|{env['ts']}|{env['nonce']}|{env['re']}|{env['ct']}".encode("utf-8")


def seal_bytes(master: bytes, kid: str, plaintext: bytes, *, ts: int | None = None, nonce: bytes | None = None,
               reply_to: str = "") -> dict[str, Any]:
    nonce = nonce if nonce is not None else os.urandom(16)
    if len(nonce) != 16:
        raise EnvelopeError("nonce must be 16 bytes")
    ek, mk = _keys(master)
    env: dict[str, Any] = {"v": VERSION, "kid": kid, "ts": int(time.time()) if ts is None else int(ts),
                           "nonce": b64e(nonce), "re": reply_to, "ct": b64e(_xor_stream(ek, nonce, plaintext))}
    env["mac"] = b64e(_h(mk, _mac_input(env)))
    return env


def seal(master: bytes, kid: str, obj: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return seal_bytes(master, kid, json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), **kw)


def check_shape(env: Any) -> dict[str, Any]:
    if not isinstance(env, dict) or set(env) != set(_FIELDS):
        raise EnvelopeError("bad envelope fields")
    if env["v"] != VERSION or not isinstance(env["ts"], int) or isinstance(env["ts"], bool):
        raise EnvelopeError("bad envelope version/timestamp")
    for k in ("kid", "nonce", "re", "ct", "mac"):
        if not isinstance(env[k], str) or len(env[k]) > 400_000:
            raise EnvelopeError(f"bad envelope field {k}")
    if not env["kid"] or len(env["kid"]) > 80:
        raise EnvelopeError("bad key id")
    return env


def open_bytes(master: bytes, env: Any, *, now: float | None = None, max_skew: int = MAX_SKEW_SECONDS) -> bytes:
    env = check_shape(env)
    ek, mk = _keys(master)
    if not hmac.compare_digest(b64d(env["mac"]), _h(mk, _mac_input(env))):
        raise EnvelopeError("authentication failed")
    if abs((time.time() if now is None else now) - env["ts"]) > max_skew:
        raise EnvelopeError("message too old or clock skew too large")
    nonce = b64d(env["nonce"])
    if len(nonce) != 16:
        raise EnvelopeError("bad nonce")
    return _xor_stream(ek, nonce, b64d(env["ct"]))


def open_json(master: bytes, env: Any, **kw: Any) -> dict[str, Any]:
    try:
        obj = json.loads(open_bytes(master, env, **kw).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        if isinstance(exc, EnvelopeError):
            raise
        raise EnvelopeError("bad plaintext") from None
    if not isinstance(obj, dict):
        raise EnvelopeError("plaintext must be an object")
    return obj
