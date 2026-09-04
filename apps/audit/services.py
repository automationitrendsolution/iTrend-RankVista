"""Audit recording helpers.
Recording must never break a request, so every failure is swallowed and logged."""

from __future__ import annotations

import logging

from django.http import HttpRequest

from apps.audit.models import AuditLog

logger = logging.getLogger("rankvista.audit")


def client_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45] or None
    return request.META.get("REMOTE_ADDR") or None


def record(
    action: str,
    *,
    request: HttpRequest | None = None,
    actor=None,
    target: str = "",
    detail: str = "",
) -> None:
    """Write one audit entry. Never raises."""
    try:
        if actor is None and request is not None:
            candidate = getattr(request, "user", None)
            actor = candidate if candidate is not None and candidate.is_authenticated else None
        AuditLog.objects.create(
            action=action,
            actor=actor,
            actor_label=(getattr(actor, "email", "") or "system")[:254],
            target=target[:254],
            detail=detail[:500],
            ip_address=client_ip(request),
        )
    except Exception as exc:  # pragma: no cover - auditing is best effort
        logger.warning("Audit write failed for %s: %s", action, type(exc).__name__)
