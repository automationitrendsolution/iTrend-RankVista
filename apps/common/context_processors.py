"""Template context shared by every rendered page."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def branding(request: HttpRequest) -> dict[str, object]:
    return {
        "BRAND": settings.BRAND,
        "DEBUG": settings.DEBUG,
    }
