"""Logging filters that keep secrets out of log output."""

from __future__ import annotations

import logging
import re

SENSITIVE_PATTERNS = [
    re.compile(r"(password[\"'\s:=]+)([^\s,&\"']+)", re.IGNORECASE),
    re.compile(r"(passwd[\"'\s:=]+)([^\s,&\"']+)", re.IGNORECASE),
    re.compile(r"(secret[\"'\s:=]+)([^\s,&\"']+)", re.IGNORECASE),
    re.compile(r"(token[\"'\s:=]+)([^\s,&\"']+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"'\s:=]+)([^\s,&\"']+)", re.IGNORECASE),
    re.compile(r"(authorization[\"'\s:=]+)([^\s,\"']+)", re.IGNORECASE),
    re.compile(r"(cookie[\"'\s:=]+)([^\s;\"']+)", re.IGNORECASE),
    re.compile(r"(sessionid[\"'\s:=]+)([^\s;\"']+)", re.IGNORECASE),
    # Credentials embedded in a connection URI: scheme://user:password@host
    re.compile(r"(://[^:/\s]+:)([^@\s]+)(@)"),
]

REDACTED = "[redacted]"


def redact(text: str) -> str:
    for pattern in SENSITIVE_PATTERNS:
        if pattern.groups == 3:
            text = pattern.sub(rf"\1{REDACTED}\3", text)
        else:
            text = pattern.sub(rf"\1{REDACTED}", text)
    return text


class RedactSensitiveFilter(logging.Filter):
    """Strip credential-looking substrings from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(
                        redact(a) if isinstance(a, str) else a for a in record.args
                    )
        except Exception:  # pragma: no cover - logging must never raise
            return True
        return True
