"""Ranking history access and aggregation.
Matrix reads are bounded to the keywords on the current page and the visible window."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from pymongo.errors import PyMongoError

from apps.common.constants import (
    RANK_DISTRIBUTION_BUCKETS,
    VISIBILITY_RANK_CEILING,
)
from apps.common.dates import DateWindow
from apps.common.mongo import MongoUnavailable, get_collection
from apps.common.schema import RANKINGS

logger = logging.getLogger("rankvista.rankings")


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def matrix_rows(
    *, project_id: int, asin: str, keyword_lowers: list[str], window: DateWindow
) -> dict[str, dict[date, dict[str, Any]]]:
    """Rank observations for the paged keywords, keyed by keyword then bucket date."""
    if not keyword_lowers:
        return {}

    query = {
        "project_id": project_id,
        "asin": asin,
        "keyword_lower": {"$in": keyword_lowers},
        "date": {"$gte": window.start_dt, "$lt": window.end_dt},
    }
    projection = {"_id": 0, "keyword_lower": 1, "date": 1, "rank": 1, "is_amazon_choice": 1}

    try:
        cursor = get_collection(RANKINGS).find(query, projection)
    except PyMongoError as exc:
        logger.error("Matrix query failed: %s", type(exc).__name__)
        raise MongoUnavailable("Ranking history could not be loaded.") from exc

    grid: dict[str, dict[date, dict[str, Any]]] = {}
    for doc in cursor:
        observed = _as_date(doc.get("date"))
        if observed is None:
            continue
        bucket = window.bucket_for(observed)
        row = grid.setdefault(doc["keyword_lower"], {})
        existing = row.get(bucket)
        # Within a weekly/monthly bucket the best (lowest positive) rank wins.
        rank = doc.get("rank")
        if existing is None or _is_better(rank, existing.get("rank")):
            row[bucket] = {"rank": rank, "is_amazon_choice": bool(doc.get("is_amazon_choice"))}
        elif doc.get("is_amazon_choice"):
            existing["is_amazon_choice"] = True
    return grid


def _is_better(candidate: Any, current: Any) -> bool:
    if not isinstance(candidate, int) or candidate <= 0:
        return False
    if not isinstance(current, int) or current <= 0:
        return True
    return candidate < current


def tracked_dates(*, project_id: int, asin: str, window: DateWindow) -> set[date]:
    """Dates on which any rank check ran, used to separate untracked from unranked."""
    pipeline = [
        {
            "$match": {
                "project_id": project_id,
                "asin": asin,
                "date": {"$gte": window.start_dt, "$lt": window.end_dt},
            }
        },
        {"$group": {"_id": "$date"}},
    ]
    try:
        rows = get_collection(RANKINGS).aggregate(pipeline)
        return {d for d in (_as_date(row["_id"]) for row in rows) if d is not None}
    except PyMongoError:
        return set()


def daily_overview(*, project_id: int, asin: str, window: DateWindow) -> list[dict[str, Any]]:
    """Per-day visibility, average position, badge count and rank distribution."""
    bucket_conditions: list[Any] = []
    for spec in RANK_DISTRIBUTION_BUCKETS:
        bucket_conditions.append(
            {
                "$sum": {
                    "$cond": [
                        {
                            "$and": [
                                {"$gte": ["$rank", spec["min"]]},
                                {"$lte": ["$rank", spec["max"]]},
                            ]
                        },
                        1,
                        0,
                    ]
                }
            }
        )

    group: dict[str, Any] = {
        "_id": "$date",
        "tracked": {"$sum": 1},
        "ranked": {"$sum": {"$cond": [{"$gt": ["$rank", 0]}, 1, 0]}},
        "page_one": {
            "$sum": {
                "$cond": [
                    {
                        "$and": [
                            {"$gt": ["$rank", 0]},
                            {"$lte": ["$rank", VISIBILITY_RANK_CEILING]},
                        ]
                    },
                    1,
                    0,
                ]
            }
        },
        "rank_sum": {"$sum": {"$cond": [{"$gt": ["$rank", 0]}, "$rank", 0]}},
        "badges": {"$sum": {"$cond": ["$is_amazon_choice", 1, 0]}},
    }
    for spec, condition in zip(RANK_DISTRIBUTION_BUCKETS, bucket_conditions, strict=True):
        group[f"b_{spec['key']}"] = condition

    pipeline = [
        {
            "$match": {
                "project_id": project_id,
                "asin": asin,
                "date": {"$gte": window.start_dt, "$lt": window.end_dt},
            }
        },
        {"$group": group},
        {"$sort": {"_id": 1}},
    ]

    try:
        rows = list(get_collection(RANKINGS).aggregate(pipeline, allowDiskUse=True))
    except PyMongoError as exc:
        logger.error("Overview aggregation failed: %s", type(exc).__name__)
        raise MongoUnavailable("Rank analytics could not be loaded.") from exc

    series: list[dict[str, Any]] = []
    for row in rows:
        observed = _as_date(row["_id"])
        if observed is None:
            continue
        tracked = int(row.get("tracked", 0))
        ranked = int(row.get("ranked", 0))
        series.append(
            {
                "date": observed,
                "tracked": tracked,
                "ranked": ranked,
                "visibility": round(100 * row.get("page_one", 0) / tracked, 1) if tracked else 0.0,
                "avg_position": round(row.get("rank_sum", 0) / ranked, 1) if ranked else None,
                "badges": int(row.get("badges", 0)),
                "distribution": {
                    spec["key"]: int(row.get(f"b_{spec['key']}", 0))
                    for spec in RANK_DISTRIBUTION_BUCKETS
                },
            }
        )
    return series


def keyword_history(
    *, project_id: int, asin: str, keyword_lower: str, window: DateWindow
) -> list[dict[str, Any]]:
    """Full rank history for a single keyword, oldest first."""
    query = {
        "project_id": project_id,
        "asin": asin,
        "keyword_lower": keyword_lower,
        "date": {"$gte": window.start_dt, "$lt": window.end_dt},
    }
    try:
        cursor = (
            get_collection(RANKINGS)
            .find(query, {"_id": 0, "date": 1, "rank": 1, "is_amazon_choice": 1})
            .sort("date", 1)
        )
        return [{**doc, "date": _as_date(doc["date"])} for doc in cursor]
    except PyMongoError as exc:
        raise MongoUnavailable("Keyword history could not be loaded.") from exc


def latest_observation_date(*, project_id: int, asin: str) -> date | None:
    try:
        rows = list(
            get_collection(RANKINGS)
            .find({"project_id": project_id, "asin": asin}, {"_id": 0, "date": 1})
            .sort("date", -1)
            .limit(1)
        )
        return _as_date(rows[0]["date"]) if rows else None
    except PyMongoError:
        return None
