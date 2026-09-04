"""Project write operations with cache invalidation and auditing."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.cache import cache_delete
from apps.common.constants import CACHE_KEY_PROJECT_SUMMARY, CACHE_KEY_USAGE_COUNTS
from apps.projects import repositories as repo


def _invalidate(project_id: str | int | None = None) -> None:
    cache_delete(CACHE_KEY_USAGE_COUNTS)
    repo.invalidate_roster()
    if project_id is not None:
        cache_delete(CACHE_KEY_PROJECT_SUMMARY.format(project_id=project_id))


def create_project(*, data: dict[str, Any], request: HttpRequest) -> dict[str, Any]:
    document = repo.create_project({**data, "owner_id": str(request.user.pk)})
    _invalidate(document["project_id"])
    record(
        AuditAction.PROJECT_CREATED,
        request=request,
        target=str(document["project_id"]),
        detail=document["name"],
    )
    return document


def update_project(*, project_id: int, data: dict[str, Any], request: HttpRequest) -> dict[str, Any] | None:
    document = repo.update_project(project_id, data)
    _invalidate(project_id)
    if document:
        record(
            AuditAction.PROJECT_UPDATED,
            request=request,
            target=str(project_id),
            detail=document.get("name", ""),
        )
    return document


def archive_project(*, project_id: int, request: HttpRequest) -> bool:
    archived = repo.archive_project(project_id)
    _invalidate(project_id)
    if archived:
        record(AuditAction.PROJECT_DELETED, request=request, target=str(project_id))
    return archived
