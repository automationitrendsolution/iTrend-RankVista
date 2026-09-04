"""HTMX request classification.
A boosted link is an HTMX request yet still needs a full page, not a partial."""

from __future__ import annotations

from django.http import HttpRequest


def is_partial(request: HttpRequest) -> bool:
    """True when the caller wants a fragment: HTMX, but not a boosted navigation."""
    htmx = getattr(request, "htmx", None)
    return bool(htmx) and not getattr(htmx, "boosted", False)


def is_boosted(request: HttpRequest) -> bool:
    htmx = getattr(request, "htmx", None)
    return bool(htmx) and bool(getattr(htmx, "boosted", False))
