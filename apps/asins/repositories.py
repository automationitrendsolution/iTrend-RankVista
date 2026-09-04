"""ASIN data access over the live warehouse registry.
project_id is pushed into every subquery so MySQL never scans the full summary table."""

from __future__ import annotations

import logging
from typing import Any

from apps.common import sourcedb
from apps.common.cache import cached_call
from apps.common.constants import CACHE_TTL_MEDIUM
from apps.common.images import product_image

logger = logging.getLogger("rankvista.asins")

MongoUnavailable = sourcedb.SourceUnavailable

SORT_KEYS = {
    "asin": lambda row: row["asin"],
    "-asin": lambda row: row["asin"],
    "title": lambda row: (row.get("title") or "").lower(),
    "-title": lambda row: (row.get("title") or "").lower(),
    "keywords": lambda row: row["tracked_keyword_count"],
    "-keywords": lambda row: row["tracked_keyword_count"],
    "status": lambda row: row["status"],
}
DESCENDING = {"-asin", "-title", "-keywords"}
DEFAULT_SORT = "-keywords"


def build_filter(
    project_id: str | int, *, search: str = "", status: str = "", marketplace: str = ""
) -> dict[str, Any]:
    return {
        "project_id": str(project_id),
        "search": (search or "").strip().lower(),
        "status": status or "",
    }


def _load_project_asins(project_id: str) -> list[dict[str, Any]]:
    """Every ASIN in one project with its keyword count. A project holds tens of rows."""

    def produce() -> list[dict[str, Any]]:
        asins = sourcedb.table("asins")
        keywords = sourcedb.table("keywords")
        categories = sourcedb.table("categories")

        registry = sourcedb.fetch_all(
            f"SELECT asin, title, brand, is_primary, first_seen_at, updated_at "
            f"FROM {asins} WHERE project_id = %s",
            [project_id],
        )
        if not registry:
            return []

        counts = {
            row["asin"]: int(row["keyword_count"] or 0)
            for row in sourcedb.fetch_all(
                f"SELECT asin, COUNT(DISTINCT keyword) AS keyword_count FROM {keywords} "
                f"WHERE project_id = %s GROUP BY asin",
                [project_id],
            )
        }

        codes = [row["asin"] for row in registry]
        placeholders = ", ".join(["%s"] * len(codes))
        kinds = {
            row["asin"]: row["asin_type"]
            for row in sourcedb.fetch_all(
                f"SELECT asin, asin_type FROM {categories} WHERE asin IN ({placeholders})",
                codes,
            )
        }

        return [
            {
                "project_id": project_id,
                "asin": row["asin"],
                "title": row.get("title") or "",
                "image_url": product_image(row["asin"], "thumb"),
                "marketplace": "US",
                "brand": row.get("brand") or "",
                "price": None,
                "is_primary": bool(row.get("is_primary")),
                "status": "active" if kinds.get(row["asin"]) == "our_asin" else "paused",
                "tracked_keyword_count": counts.get(row["asin"], 0),
                "updated_at": row.get("updated_at"),
            }
            for row in registry
        ]

    return cached_call(f"rv:asin:list:v1:{project_id}", CACHE_TTL_MEDIUM, produce)


def _apply(query: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    search, status = query.get("search"), query.get("status")
    if search:
        rows = [
            row
            for row in rows
            if search in row["asin"].lower()
            or search in row["title"].lower()
            or search in row["brand"].lower()
        ]
    if status:
        rows = [row for row in rows if row["status"] == status]
    return rows


def list_asins(
    *, query: dict[str, Any], sort: str = DEFAULT_SORT, offset: int = 0, limit: int = 25
) -> tuple[list[dict[str, Any]], int]:
    rows = _apply(query, _load_project_asins(query["project_id"]))
    key = SORT_KEYS.get(sort, SORT_KEYS[DEFAULT_SORT])
    # Python sorts stably, so a second pass pins primaries first without losing the order.
    rows = sorted(rows, key=lambda row: (key(row), row["asin"]), reverse=sort in DESCENDING)
    rows = sorted(rows, key=lambda row: not row["is_primary"])
    return rows[offset : offset + limit], len(rows)


def get_asin(project_id: str | int, asin: str) -> dict[str, Any] | None:
    for row in _load_project_asins(str(project_id)):
        if row["asin"] == asin:
            return row
    return None


def selector_options(project_id: str | int, limit: int = 200) -> list[dict[str, Any]]:
    """Compact ASIN list powering the project-wide ASIN switcher."""
    rows = sorted(
        _load_project_asins(str(project_id)),
        key=lambda row: (not row["is_primary"], -row["tracked_keyword_count"], row["asin"]),
    )
    return [
        {
            "asin": row["asin"],
            "title": row["title"],
            "image_url": row["image_url"],
            "is_primary": row["is_primary"],
            "tracked_keyword_count": row["tracked_keyword_count"],
        }
        for row in rows[:limit]
    ]


def default_asin(project_id: str | int, fallback: str = "") -> str:
    options = selector_options(project_id, limit=1)
    return str(options[0]["asin"]) if options else fallback


def count_for_project(project_id: str | int) -> int:
    return len(_load_project_asins(str(project_id)))


def upsert_asin(project_id: str | int, asin: str, data: dict[str, Any]) -> None:
    """The warehouse account is read-only; ASINs are managed by the upstream sync."""
    raise sourcedb.SourceUnavailable("ASINs are maintained by the upstream data sync.")
