"""Encryption at rest and masking for connection credentials.
User passwords are hashed by Django; these must stay reversible, so they are encrypted."""

from __future__ import annotations

import base64
import hashlib
import os
import re

from cryptography.fernet import Fernet, InvalidToken

ENC_PREFIX = "enc:"
KEY_ENV = "RANKVISTA_SECRET_KEY"

# scheme://user:password@host - the part that must never be shown or logged.
URI_CREDENTIALS = re.compile(r"(://[^:/\s]+:)([^@\s]+)(@)")


class SecretError(RuntimeError):
    """Raised when an encrypted value cannot be decrypted."""


def _fernet() -> Fernet:
    raw = os.environ.get(KEY_ENV) or os.environ.get("SECRET_KEY") or ""
    if not raw:
        raise SecretError(f"{KEY_ENV} (or SECRET_KEY) must be set to use encrypted values.")
    # Fernet needs 32 url-safe base64 bytes; derive them so any passphrase works.
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    """Return an `enc:` token safe to store in .env instead of a plaintext secret."""
    return ENC_PREFIX + _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    body = token[len(ENC_PREFIX):] if token.startswith(ENC_PREFIX) else token
    try:
        return _fernet().decrypt(body.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise SecretError("Could not decrypt value; the key may have changed.") from exc


def resolve(value: str | None) -> str:
    """Return a usable secret, decrypting `enc:` values transparently."""
    if not value:
        return ""
    if value.startswith(ENC_PREFIX):
        return decrypt(value)
    return value


def mask(value: str | None, keep: int = 2) -> str:
    """Render a secret for display: never more than a couple of characters survive."""
    if not value:
        return "(not set)"
    if len(value) <= keep * 2:
        return "*" * 8
    return f"{value[:keep]}{'*' * 8}{value[-keep:]}"


def mask_uri(uri: str | None) -> str:
    """Show a connection URI with the password replaced, host kept for diagnostics."""
    if not uri:
        return "(not set)"
    return URI_CREDENTIALS.sub(r"\1********\3", uri)


def fingerprint(value: str | None) -> str:
    """Short stable hash so two environments can be compared without revealing values."""
    if not value:
        return "-"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
