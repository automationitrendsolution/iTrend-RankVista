"""ASIN data access scoped to a project."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import PyMongoError

from apps.common.mongo import MongoUnavailable, get_collection
from apps.common.schema import ASINS

logger = logging.getLogger("rankvista.asins")

LIST_PROJECTION = {
    "_id": 0,
    "project_id": 1,
    "asin": 1,
    "title": 1,
    "image_url": 1,
    "marketplace": 1,
    "brand": 1,
    "price": 1,
    "status": 1,
    "is_primary": 1,
    "tracked_keyword_count": 1,
    "updated_at": 1,
}

SORT_FIELDS = {
    "asin": ("asin", 1),
    "-asin": ("asin", -1),
    "title": ("title", 1),
    "-title": ("title", -1),
    "keywords": ("tracked_keyword_count", 1),
    "-keywords": ("tracked_keyword_count", -1),
    "status": ("status", 1),
}
DEFAULT_SORT = "-keywords"


def build_filter(
    project_id: int, *, search: str = "", status: str = "", marketplace: str = ""
) -> dict[str, Any]:
    query: dict[str, Any] = {"project_id": project_id}
    if status:
        query["status"] = status
    if marketplace:
        query["marketplace"] = marketplace.upper()
    if search:
        escaped = re.escape(search.strip())
        query["$or"] = [
            {"asin": {"$regex": escaped, "$options": "i"}},
            {"title": {"$regex": escaped, "$options": "i"}},
            {"brand": {"$regex": escaped, "$options": "i"}},
        ]
    return query


def list_asins(
    *, query: dict[str, Any], sort: str = DEFAULT_SORT, offset: int = 0, limit: int = 25
) -> tuple[list[dict[str, Any]], int]:
    field, direction = SORT_FIELDS.get(sort, SORT_FIELDS[DEFAULT_SORT])
    try:
        collection = get_collection(ASINS)
        total = collection.count_documents(query)
        cursor = (
            collection.find(query, LIST_PROJECTION)
            .sort([("is_primary", -1), (field, direction), ("asin", 1)])
            .skip(offset)
            .limit(limit)
        )
        return list(cursor), total
    except PyMongoError as exc:
        logger.error("ASIN listing failed: %s", type(exc).__name__)
        raise MongoUnavailable("ASINs could not be loaded.") from exc


def get_asin(project_id: int, asin: str) -> dict[str, Any] | None:
    try:
        return get_collection(ASINS).find_one(
            {"project_id": project_id, "asin": asin}, LIST_PROJECTION
        )
    except PyMongoError as exc:
        raise MongoUnavailable("ASIN could not be loaded.") from exc


def selector_options(project_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Compact ASIN list powering the project-wide ASIN switcher."""
    try:
        cursor = (
            get_collection(ASINS)
            .find(
                {"project_id": project_id},
                {"_id": 0, "asin": 1, "title": 1, "image_url": 1, "is_primary": 1,
                 "tracked_keyword_count": 1},
            )
            .sort([("is_primary", -1), ("tracked_keyword_count", -1), ("asin", 1)])
            .limit(limit)
        )
        return list(cursor)
    except PyMongoError:
        return []


def default_asin(project_id: int, fallback: str = "") -> str:
    """The ASIN a ranking screen opens on: the primary, else the busiest."""
    options = selector_options(project_id, limit=1)
    if options:
        return str(options[0]["asin"])
    return fallback


def upsert_asin(project_id: int, asin: str, data: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    try:
        get_collection(ASINS).update_one(
            {"project_id": project_id, "asin": asin},
            {"$set": {**data, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except PyMongoError as exc:
        raise MongoUnavailable("ASIN could not be saved.") from exc


def count_for_project(project_id: int) -> int:
    try:
        return get_collection(ASINS).count_documents({"project_id": project_id})
    except PyMongoError:
        return 0
