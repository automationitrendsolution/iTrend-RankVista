"""Project data access. Every query is projected, indexed and paginated in Mongo."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from apps.common.constants import DEFAULT_PROJECT_SORT, PROJECT_SORT_OPTIONS
from apps.common.mongo import MongoUnavailable, get_collection
from apps.common.schema import ASINS, KEYWORDS, PROJECTS, RANKINGS

logger = logging.getLogger("rankvista.projects")

CARD_PROJECTION = {
    "_id": 0,
    "project_id": 1,
    "name": 1,
    "marketplace": 1,
    "primary_asin": 1,
    "image_url": 1,
    "asin_count": 1,
    "keyword_count": 1,
    "status": 1,
    "tags": 1,
    "created_at": 1,
    "updated_at": 1,
    "last_opened_at": 1,
}

SORT_BY_KEY = {option["key"]: option for option in PROJECT_SORT_OPTIONS}


def _sort_spec(sort_key: str) -> list[tuple[str, int]]:
    option = SORT_BY_KEY.get(sort_key, SORT_BY_KEY[DEFAULT_PROJECT_SORT])
    return [(option["field"], option["direction"]), ("project_id", -1)]


def build_filter(
    *,
    search: str = "",
    marketplace: str = "",
    status: str = "",
    owner_id: int | None = None,
    min_asins: int | None = None,
    min_keywords: int | None = None,
) -> dict[str, Any]:
    """Translate UI filters into an indexed Mongo query document."""
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    else:
        query["status"] = {"$ne": "archived"}
    if marketplace:
        query["marketplace"] = marketplace.upper()
    if owner_id is not None:
        query["owner_id"] = owner_id
    if search:
        escaped = re.escape(search.strip())
        query["$or"] = [
            {"name_lower": {"$regex": escaped.lower()}},
            {"primary_asin": {"$regex": escaped, "$options": "i"}},
        ]
    if min_asins:
        query["asin_count"] = {"$gte": min_asins}
    if min_keywords:
        query["keyword_count"] = {"$gte": min_keywords}
    return query


def list_projects(
    *,
    query: dict[str, Any],
    sort: str = DEFAULT_PROJECT_SORT,
    offset: int = 0,
    limit: int = 25,
) -> tuple[list[dict[str, Any]], int]:
    """Return one page of project cards plus the total match count."""
    try:
        collection = get_collection(PROJECTS)
        total = collection.count_documents(query)
        cursor = (
            collection.find(query, CARD_PROJECTION)
            .sort(_sort_spec(sort))
            .skip(offset)
            .limit(limit)
        )
        return list(cursor), total
    except PyMongoError as exc:
        logger.error("Project listing failed: %s", type(exc).__name__)
        raise MongoUnavailable("Projects could not be loaded.") from exc


def get_project(project_id: int) -> dict[str, Any] | None:
    try:
        return get_collection(PROJECTS).find_one({"project_id": project_id}, {"_id": 0})
    except PyMongoError as exc:
        logger.error("Project fetch failed: %s", type(exc).__name__)
        raise MongoUnavailable("Project could not be loaded.") from exc


def usage_counts(owner_id: int | None = None) -> dict[str, int]:
    """Header counters: projects, ASINs and keywords currently tracked."""
    scope: dict[str, Any] = {} if owner_id is None else {"owner_id": owner_id}
    try:
        projects = get_collection(PROJECTS)
        pipeline = [
            {"$match": {**scope, "status": {"$ne": "archived"}}},
            {
                "$group": {
                    "_id": None,
                    "projects": {"$sum": 1},
                    "asins": {"$sum": {"$ifNull": ["$asin_count", 0]}},
                    "keywords": {"$sum": {"$ifNull": ["$keyword_count", 0]}},
                }
            },
        ]
        result = list(projects.aggregate(pipeline))
        if not result:
            return {"projects": 0, "asins": 0, "keywords": 0}
        row = result[0]
        return {
            "projects": int(row.get("projects", 0)),
            "asins": int(row.get("asins", 0)),
            "keywords": int(row.get("keywords", 0)),
        }
    except PyMongoError as exc:
        logger.error("Usage aggregation failed: %s", type(exc).__name__)
        return {"projects": 0, "asins": 0, "keywords": 0}


def distinct_marketplaces() -> list[str]:
    try:
        values = get_collection(PROJECTS).distinct("marketplace")
        return sorted(v for v in values if v)
    except PyMongoError:
        return []


def next_project_id() -> int:
    """Allocate the next public project id without a separate counter document."""
    try:
        latest = list(
            get_collection(PROJECTS).find({}, {"project_id": 1}).sort("project_id", -1).limit(1)
        )
        return int(latest[0]["project_id"]) + 1 if latest else 10001
    except (PyMongoError, KeyError, ValueError):
        return int(datetime.now(timezone.utc).timestamp())


def create_project(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    document = {
        **data,
        "project_id": data.get("project_id") or next_project_id(),
        "name_lower": data["name"].lower(),
        "asin_count": data.get("asin_count", 0),
        "keyword_count": data.get("keyword_count", 0),
        "status": data.get("status", "active"),
        "created_at": now,
        "updated_at": now,
        "last_opened_at": now,
    }
    try:
        get_collection(PROJECTS).insert_one(document)
    except DuplicateKeyError:
        document["project_id"] = next_project_id()
        get_collection(PROJECTS).insert_one(document)
    except PyMongoError as exc:
        raise MongoUnavailable("Project could not be created.") from exc
    document.pop("_id", None)
    return document


def update_project(project_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    changes = {**data, "updated_at": datetime.now(timezone.utc)}
    if "name" in data:
        changes["name_lower"] = data["name"].lower()
    try:
        return get_collection(PROJECTS).find_one_and_update(
            {"project_id": project_id},
            {"$set": changes},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
    except PyMongoError as exc:
        raise MongoUnavailable("Project could not be updated.") from exc


def touch_last_opened(project_id: int) -> None:
    """Record that a project was opened, driving the default sort order."""
    try:
        get_collection(PROJECTS).update_one(
            {"project_id": project_id},
            {"$set": {"last_opened_at": datetime.now(timezone.utc)}},
        )
    except PyMongoError:
        logger.debug("Could not update last_opened_at for project %s", project_id)


def archive_project(project_id: int) -> bool:
    """Soft-archive a project. Ranking history is deliberately preserved."""
    try:
        result = get_collection(PROJECTS).update_one(
            {"project_id": project_id},
            {"$set": {"status": "archived", "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count > 0
    except PyMongoError as exc:
        raise MongoUnavailable("Project could not be archived.") from exc


def refresh_counts(project_id: int) -> dict[str, int]:
    """Recompute the denormalised ASIN and keyword counters for one project."""
    try:
        asins = get_collection(ASINS).count_documents({"project_id": project_id})
        keywords = get_collection(KEYWORDS).count_documents({"project_id": project_id})
        get_collection(PROJECTS).update_one(
            {"project_id": project_id},
            {"$set": {"asin_count": asins, "keyword_count": keywords}},
        )
        return {"asin_count": asins, "keyword_count": keywords}
    except PyMongoError:
        return {"asin_count": 0, "keyword_count": 0}


def has_ranking_data(project_id: int) -> bool:
    try:
        return get_collection(RANKINGS).find_one({"project_id": project_id}, {"_id": 1}) is not None
    except PyMongoError:
        return False
