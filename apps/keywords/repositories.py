"""Keyword data access. The matrix pages keywords first, then fetches only those rows."""

from __future__ import annotations

import logging
import re
from typing import Any

from pymongo.errors import PyMongoError

from apps.common.mongo import MongoUnavailable, get_collection
from apps.common.schema import KEYWORDS

logger = logging.getLogger("rankvista.keywords")

LIST_PROJECTION = {
    "_id": 0,
    "keyword": 1,
    "keyword_lower": 1,
    "search_volume": 1,
    "kw_sales": 1,
    "sales_trend_pct": 1,
    "conversion_pct": 1,
    "is_tracked": 1,
    "current_rank": 1,
    "best_rank": 1,
    "asin": 1,
}

SORT_FIELDS = {
    "keyword": ("keyword_lower", 1),
    "-keyword": ("keyword_lower", -1),
    "sales": ("kw_sales", 1),
    "-sales": ("kw_sales", -1),
    "trend": ("sales_trend_pct", 1),
    "-trend": ("sales_trend_pct", -1),
    "conversion": ("conversion_pct", 1),
    "-conversion": ("conversion_pct", -1),
    "volume": ("search_volume", 1),
    "-volume": ("search_volume", -1),
    "rank": ("current_rank", 1),
    "-rank": ("current_rank", -1),
}
DEFAULT_SORT = "-sales"


def build_filter(
    project_id: int,
    asin: str,
    *,
    search: str = "",
    tracked: str = "",
    rank_min: int | None = None,
    rank_max: int | None = None,
    sales_min: int | None = None,
    conversion_min: float | None = None,
) -> dict[str, Any]:
    """Translate the keyword filter panel into an indexed query document."""
    query: dict[str, Any] = {"project_id": project_id, "asin": asin}
    if search:
        query["keyword_lower"] = {"$regex": re.escape(search.strip().lower())}
    if tracked == "tracked":
        query["is_tracked"] = True
    elif tracked == "untracked":
        query["is_tracked"] = False

    rank_clause: dict[str, Any] = {}
    if rank_min is not None:
        rank_clause["$gte"] = rank_min
    if rank_max is not None:
        rank_clause["$lte"] = rank_max
    if rank_clause:
        query["current_rank"] = rank_clause
    if sales_min is not None:
        query["kw_sales"] = {"$gte": sales_min}
    if conversion_min is not None:
        query["conversion_pct"] = {"$gte": conversion_min}
    return query


def list_keywords(
    *, query: dict[str, Any], sort: str = DEFAULT_SORT, offset: int = 0, limit: int = 25
) -> tuple[list[dict[str, Any]], int]:
    field, direction = SORT_FIELDS.get(sort, SORT_FIELDS[DEFAULT_SORT])
    try:
        collection = get_collection(KEYWORDS)
        total = collection.count_documents(query)
        cursor = (
            collection.find(query, LIST_PROJECTION)
            .sort([(field, direction), ("keyword_lower", 1)])
            .skip(offset)
            .limit(limit)
        )
        return list(cursor), total
    except PyMongoError as exc:
        logger.error("Keyword listing failed: %s", type(exc).__name__)
        raise MongoUnavailable("Keywords could not be loaded.") from exc


def count_for_project(project_id: int, asin: str | None = None) -> int:
    query: dict[str, Any] = {"project_id": project_id}
    if asin:
        query["asin"] = asin
    try:
        return get_collection(KEYWORDS).count_documents(query)
    except PyMongoError:
        return 0


def metric_summary(project_id: int, asin: str) -> dict[str, float]:
    """Aggregate keyword business metrics for the ASIN header strip."""
    pipeline = [
        {"$match": {"project_id": project_id, "asin": asin}},
        {
            "$group": {
                "_id": None,
                "keywords": {"$sum": 1},
                "tracked": {"$sum": {"$cond": ["$is_tracked", 1, 0]}},
                "sales": {"$sum": {"$ifNull": ["$kw_sales", 0]}},
                "avg_conversion": {"$avg": {"$ifNull": ["$conversion_pct", 0]}},
                "search_volume": {"$sum": {"$ifNull": ["$search_volume", 0]}},
            }
        },
    ]
    try:
        rows = list(get_collection(KEYWORDS).aggregate(pipeline))
    except PyMongoError:
        rows = []
    if not rows:
        return {"keywords": 0, "tracked": 0, "sales": 0, "avg_conversion": 0.0, "search_volume": 0}
    row = rows[0]
    return {
        "keywords": int(row.get("keywords", 0)),
        "tracked": int(row.get("tracked", 0)),
        "sales": int(row.get("sales", 0)),
        "avg_conversion": round(float(row.get("avg_conversion") or 0.0), 1),
        "search_volume": int(row.get("search_volume", 0)),
    }


def upsert_keyword(project_id: int, asin: str, keyword: str, data: dict[str, Any]) -> None:
    try:
        get_collection(KEYWORDS).update_one(
            {"project_id": project_id, "asin": asin, "keyword_lower": keyword.lower()},
            {"$set": {**data, "keyword": keyword, "keyword_lower": keyword.lower()}},
            upsert=True,
        )
    except PyMongoError as exc:
        raise MongoUnavailable("Keyword could not be saved.") from exc
