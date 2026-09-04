"""Query-parameter coercion helpers.
Malformed input always degrades to None instead of raising."""

from __future__ import annotations

from django.http import HttpRequest


def get_int(request: HttpRequest, key: str, default: int | None = None) -> int | None:
    raw = request.GET.get(key, "")
    if raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_float(request: HttpRequest, key: str, default: float | None = None) -> float | None:
    raw = request.GET.get(key, "")
    if raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def get_str(request: HttpRequest, key: str, default: str = "", *, allowed: set[str] | None = None) -> str:
    value = (request.GET.get(key) or default).strip()
    if allowed is not None and value not in allowed:
        return default
    return value


def has_active_filters(request: HttpRequest, keys: tuple[str, ...]) -> bool:
    return any(request.GET.get(key) for key in keys)
