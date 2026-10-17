"""Central redaction and non-persistent PAT validation helpers."""
from __future__ import annotations

import re

_TOKEN_PATTERNS = (
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{16,}"),
    re.compile(r"(?i)(Authorization\s*[:=]\s*)(?:Bearer|token)\s+[^\s,;]+"),
    re.compile(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@"),
    re.compile(r"(?i)(access[_-]?token|api[_-]?key|client[_-]?secret|password)(\s*[:=]\s*)['\"]?[^\s'\"]{12,}"),
)


def redact_github_text(value: object, *, known_secrets: tuple[str, ...] = ()) -> str:
    """Return text suitable for logs/UI; never rely on server error text being safe."""
    text = str(value)
    for secret in known_secrets:
        if secret:
            text = text.replace(secret, "[REDACTED_SECRET]")
    # Order is intentional: scrub complete Authorization assignments before broad token forms.
    for pattern in _TOKEN_PATTERNS:
        if pattern.groups >= 2 and "Authorization" in pattern.pattern:
            text = pattern.sub(r"\1[REDACTED_SECRET]", text)
        elif pattern.groups >= 2 and "https?" in pattern.pattern:
            text = pattern.sub(r"\1[REDACTED]@", text)
        elif pattern.groups >= 2 and "access" in pattern.pattern.lower():
            text = pattern.sub(r"\1\2[REDACTED_SECRET]", text)
        else:
            text = pattern.sub("[REDACTED_SECRET]", text)
    return text


def validate_pat(token: str) -> str:
    """Validate token shape only; actual validity is established only by the API."""
    if not isinstance(token, str):
        raise ValueError("Enter a GitHub Personal Access Token as text.")
    token = token.strip()
    if not token:
        raise ValueError("Enter a GitHub Personal Access Token.")
    if len(token) > 1200:
        raise ValueError("The token is longer than the supported limit.")
    if any(ord(char) < 33 or ord(char) > 126 for char in token):
        raise ValueError("The token contains whitespace or non-ASCII/control characters. Paste only the token itself.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{20,1200}", token):
        raise ValueError("The token format is not recognized as a credential string. Paste only the token itself.")
    # GitHub currently issues recognizable prefixes; do not hard-fail on unknown ASCII formats,
    # because legacy PATs and future formats should be diagnosed by GitHub, not guessed locally.
    return token
