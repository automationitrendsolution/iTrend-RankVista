"""Template context shared by every rendered page."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def branding(request: HttpRequest) -> dict[str, object]:
    return {
        "BRAND": settings.BRAND,
        "DEBUG": settings.DEBUG,
    }


def permissions(request: HttpRequest) -> dict[str, object]:
    """Expose the page matrix so navigation hides what the role cannot open.
    The decorators remain the actual guard; this only avoids dead-end links."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"can": {}}

    from apps.accounts.pages import PAGES

    return {"can": {item.key: item.allows(user.role) for item in PAGES}}
