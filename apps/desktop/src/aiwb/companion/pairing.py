"""Pairing code v2 (roadmap 3.7.0 / mobile 0.4.0): one 80-bit secret, shown two ways.

* Short manual code: 16 Base32 characters (RFC 4648 alphabet A-Z 2-7), grouped ``ABCD-EFGH-IJKL-MNOP``.
  Input is normalised (case, spaces, dashes; 0->O, 1->I, 8->B are accepted as typos).
* QR / deep link: ``aiwb://pair?h=<ipv4>&p=<port>&k=<16 Base32 chars>``.

Both forms carry the same secret, from which the phone and the desktop derive
    master key = HMAC-SHA256(secret, "aiwb-pair-key-v2")              (32 bytes, envelope v1 key)
    pairing id = "pair-" + hex(HMAC-SHA256(secret, "aiwb-pair-id-v2"))[:12]
so the secret itself never goes over the network. The code is valid for 10 minutes, is consumed by the first
successful request, and the desktop cancels it after 5 failed attempts (see service.py). The Android side
(PairingCode.kt) is checked against packages/contracts/vectors/companion-pairing.v2.json.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit

SECRET_BYTES = 10
CODE_LEN = 16
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_TYPOS = str.maketrans({"0": "O", "1": "I", "8": "B"})


class PairingCodeError(ValueError):
    pass


def new_secret() -> bytes:
    return secrets.token_bytes(SECRET_BYTES)


def code_from_secret(secret: bytes) -> str:
    if len(secret) != SECRET_BYTES:
        raise PairingCodeError("secret must be 10 bytes")
    return base64.b32encode(secret).decode("ascii")


def format_code(code: str) -> str:
    c = normalize_code(code)
    return "-".join(c[i:i + 4] for i in range(0, CODE_LEN, 4))


def normalize_code(text: str) -> str:
    c = "".join(ch for ch in str(text).upper() if ch not in " -_\t\r\n").translate(_TYPOS)
    if len(c) != CODE_LEN or any(ch not in ALPHABET for ch in c):
        raise PairingCodeError("a pairing code has 16 characters (A-Z, 2-7)")
    return c


def secret_from_code(text: str) -> bytes:
    return base64.b32decode(normalize_code(text))


def master_key(secret: bytes) -> bytes:
    return hmac.new(secret, b"aiwb-pair-key-v2", hashlib.sha256).digest()


def pairing_id(secret: bytes) -> str:
    return "pair-" + hmac.new(secret, b"aiwb-pair-id-v2", hashlib.sha256).hexdigest()[:12]


def is_private_lan(host: str) -> bool:
    try:
        ip = ipaddress.IPv4Address(host)
    except ValueError:
        return False
    o = ip.packed
    return o[0] == 10 or o[0] == 127 or (o[0] == 172 and 16 <= o[1] <= 31) or (o[0] == 192 and o[1] == 168)


def build_uri(host: str, port: int, secret: bytes) -> str:
    return "aiwb://pair?" + urlencode({"h": host, "p": int(port), "k": code_from_secret(secret)})


def parse_uri(text: str) -> tuple[str, int, bytes]:
    """Returns (host, port, secret); only private-LAN / loopback IPv4 hosts are accepted."""
    u = urlsplit(text.strip())
    if u.scheme != "aiwb" or u.netloc != "pair":
        raise PairingCodeError("not an aiwb://pair link")
    q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
    host = q.get("h", "")
    if not is_private_lan(host):
        raise PairingCodeError("the desktop address must be on the local network")
    try:
        port = int(q.get("p", ""))
    except ValueError:
        raise PairingCodeError("bad port") from None
    if not 1 <= port <= 65535:
        raise PairingCodeError("bad port")
    return host, port, secret_from_code(q.get("k", ""))
