"""Read-side helpers shared by the project screens."""

from __future__ import annotations

from typing import Any

from django.http import Http404

from apps.common.cache import cached_call
from apps.common.constants import CACHE_KEY_USAGE_COUNTS, CACHE_TTL_SHORT
from apps.projects import repositories as repo


def usage_counters() -> dict[str, int]:
    """Cached platform-wide counters shown above the project grid."""
    return cached_call(CACHE_KEY_USAGE_COUNTS, CACHE_TTL_SHORT, repo.usage_counts)


def require_project(project_id: int) -> dict[str, Any]:
    """Fetch a project or raise 404 so views never branch on None."""
    project = repo.get_project(project_id)
    if not project:
        raise Http404("Project not found.")
    return project
