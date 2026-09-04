"""Project data access over the live warehouse, merged with the MongoDB overlay.
Projects are derived from the ASIN registry; names, tags and status come from the overlay."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from apps.common import sourcedb
from apps.common.cache import cache_delete, cached_call
from apps.common.images import product_image
from apps.common.naming import clean, shorten
from apps.common.constants import CACHE_TTL_LONG, CACHE_TTL_MEDIUM, DEFAULT_PROJECT_SORT
from apps.projects import overlay

logger = logging.getLogger("rankvista.projects")

MongoUnavailable = sourcedb.SourceUnavailable

CACHE_KEY_ROSTER = "rv:proj:roster:v2"
CACHE_KEY_USAGE = "rv:usage:counts:v2"

def _as_utc(value: Any) -> datetime:
    """MySQL returns naive datetimes and Mongo returns aware ones; sorting needs both."""
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


SORT_KEYS: dict[str, Any] = {
    "last_opened": lambda p: _as_utc(p["last_opened_at"] or p["created_at"]),
    "recent": lambda p: _as_utc(p["created_at"]),
    "name_asc": lambda p: p["name"].lower(),
    "name_desc": lambda p: p["name"].lower(),
    "asins_desc": lambda p: p["asin_count"],
    "keywords_desc": lambda p: p["keyword_count"],
}
DESCENDING = {"last_opened", "recent", "name_desc", "asins_desc", "keywords_desc"}

# One row per project: ASIN counts from the registry, keyword counts from the summary.
ROSTER_SQL = """
    SELECT p.*, COALESCE(k.keyword_count, 0) AS keyword_count
    FROM (
        SELECT r.project_id,
               COUNT(DISTINCT r.asin) AS asin_count,
               MIN(r.first_seen_at) AS first_seen_at,
               SUBSTRING_INDEX(
                   GROUP_CONCAT(r.asin ORDER BY r.is_primary DESC, r.asin), ',', 1
               ) AS primary_asin,
               SUBSTRING_INDEX(
                   GROUP_CONCAT(r.title ORDER BY r.is_primary DESC, r.asin SEPARATOR '||'), '||', 1
               ) AS display_name,
               SUBSTRING_INDEX(
                   GROUP_CONCAT(r.brand ORDER BY r.is_primary DESC, r.asin SEPARATOR '||'), '||', 1
               ) AS brand
        FROM {asins} r
        GROUP BY r.project_id
    ) p
    LEFT JOIN (
        SELECT project_id, COUNT(DISTINCT keyword) AS keyword_count
        FROM {keywords} GROUP BY project_id
    ) k ON k.project_id = p.project_id
"""


def _roster() -> list[dict[str, Any]]:
    """Every project the warehouse knows about. Around a hundred rows, so cached whole."""

    def produce() -> list[dict[str, Any]]:
        sql = ROSTER_SQL.format(asins=sourcedb.table("asins"), keywords=sourcedb.table("keywords"))
        return sourcedb.fetch_all(sql)

    return cached_call(CACHE_KEY_ROSTER, CACHE_TTL_LONG, produce)


def build_filter(
    *,
    search: str = "",
    marketplace: str = "",
    status: str = "",
    owner_id: int | None = None,
    min_asins: int | None = None,
    min_keywords: int | None = None,
) -> dict[str, Any]:
    """Filter descriptor consumed by list_projects. A dict keeps the view signature stable."""
    return {
        "search": (search or "").strip().lower(),
        "marketplace": (marketplace or "").upper(),
        "status": status or "",
        "min_asins": min_asins,
        "min_keywords": min_keywords,
    }


def _decorate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge overlay metadata over the rows derived from the warehouse."""
    overlays = overlay.get_many([str(row["project_id"]) for row in rows])
    decorated = []
    for row in rows:
        project_id = str(row["project_id"])
        patch = overlays.get(project_id, {})
        full_title = clean(row.get("display_name"))
        decorated.append(
            {
                "project_id": project_id,
                "name": patch.get("name") or shorten(full_title) or f"Project {project_id}",
                "full_title": full_title,
                "marketplace": patch.get("marketplace") or "US",
                "primary_asin": patch.get("primary_asin") or row.get("primary_asin") or "",
                "image_url": patch.get("image_url") or product_image(row.get("primary_asin"), "card"),
                "brand": row.get("brand") or "",
                "asin_count": int(row.get("asin_count") or 0),
                "keyword_count": int(row.get("keyword_count") or 0),
                "status": patch.get("status") or "active",
                "tags": patch.get("tags") or [],
                "created_at": row.get("first_seen_at"),
                "updated_at": patch.get("updated_at"),
                "last_opened_at": patch.get("last_opened_at"),
            }
        )
    return decorated


def _matches(project: dict[str, Any], query: dict[str, Any]) -> bool:
    search = query.get("search")
    if search and not (
        search in project["name"].lower()
        or search in project["primary_asin"].lower()
        or search in project["project_id"]
    ):
        return False
    if query.get("marketplace") and project["marketplace"] != query["marketplace"]:
        return False

    status = query.get("status")
    if status:
        if project["status"] != status:
            return False
    elif project["status"] == "archived":
        return False

    if query.get("min_asins") and project["asin_count"] < query["min_asins"]:
        return False
    if query.get("min_keywords") and project["keyword_count"] < query["min_keywords"]:
        return False
    return True


def list_projects(
    *,
    query: dict[str, Any],
    sort: str = DEFAULT_PROJECT_SORT,
    offset: int = 0,
    limit: int = 25,
) -> tuple[list[dict[str, Any]], int]:
    """One page of project cards plus the total match count.
    Filtering precedes pagination, so the count always matches what is listed."""
    projects = [p for p in _decorate(_roster()) if _matches(p, query)]

    key = SORT_KEYS.get(sort, SORT_KEYS[DEFAULT_PROJECT_SORT])
    projects.sort(key=lambda p: (key(p), p["project_id"]), reverse=sort in DESCENDING)

    return projects[offset : offset + limit], len(projects)


def get_project(project_id: str | int) -> dict[str, Any] | None:
    project_id = str(project_id)
    for row in _roster():
        if str(row["project_id"]) == project_id:
            return _decorate([row])[0]
    return None


def usage_counts(owner_id: int | None = None) -> dict[str, int]:
    """Header counters: projects, ASINs and keywords currently tracked."""

    def produce() -> dict[str, int]:
        asins = sourcedb.table("asins")
        keywords = sourcedb.table("keywords")
        counts = sourcedb.fetch_one(
            f"SELECT COUNT(DISTINCT project_id) AS projects, COUNT(DISTINCT asin) AS asins "
            f"FROM {asins}"
        ) or {}
        return {
            "projects": int(counts.get("projects") or 0),
            "asins": int(counts.get("asins") or 0),
            "keywords": int(
                sourcedb.scalar(f"SELECT COUNT(DISTINCT project_id, keyword) FROM {keywords}")
            ),
        }

    return cached_call(CACHE_KEY_USAGE, CACHE_TTL_LONG, produce)


def distinct_marketplaces() -> list[str]:
    """Marketplace is an overlay concept; the warehouse tracks a single market."""
    return sorted({p["marketplace"] for p in _decorate(_roster())})


def next_project_id() -> str:
    highest = max((int(row["project_id"]) for row in _roster() if str(row["project_id"]).isdigit()),
                  default=90000)
    return str(highest + 1)


def create_project(data: dict[str, Any]) -> dict[str, Any]:
    """Register a project in the overlay. The read-only warehouse is never written to."""
    project_id = str(data.get("project_id") or next_project_id())
    document = overlay.upsert(
        project_id, {**data, "status": data.get("status", "active")}, owner_id=data.get("owner_id")
    )
    return {
        "project_id": project_id,
        "name": document.get("name", ""),
        "marketplace": document.get("marketplace", "US"),
        "primary_asin": document.get("primary_asin", ""),
        "image_url": document.get("image_url", ""),
        "tags": document.get("tags", []),
        "asin_count": 0,
        "keyword_count": 0,
        "status": "active",
    }


def update_project(project_id: str | int, data: dict[str, Any]) -> dict[str, Any] | None:
    overlay.upsert(str(project_id), data)
    return get_project(project_id) or {"project_id": str(project_id), **data}


def touch_last_opened(project_id: str | int) -> None:
    overlay.touch_last_opened(str(project_id))


def archive_project(project_id: str | int) -> bool:
    overlay.upsert(str(project_id), {"status": "archived"})
    return True


def has_ranking_data(project_id: str | int) -> bool:
    ranks = sourcedb.table("ranks")
    row = sourcedb.fetch_one(
        f"SELECT 1 AS ok FROM {ranks} WHERE project_id = %s LIMIT 1", [str(project_id)]
    )
    return row is not None


def refresh_counts(project_id: str | int) -> dict[str, int]:
    project = get_project(project_id)
    if not project:
        return {"asin_count": 0, "keyword_count": 0}
    return {"asin_count": project["asin_count"], "keyword_count": project["keyword_count"]}


def invalidate_roster() -> None:
    """Drop the cached roster after an overlay write changes a project."""
    cache_delete(CACHE_KEY_ROSTER)
