"""Ranking history over the live warehouse.
Matrix reads are bounded to the keywords on the current page and the visible window."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from apps.common import sourcedb
from apps.common.cache import cached_call
from apps.common.constants import (
    CACHE_TTL_LONG,
    RANK_DISTRIBUTION_BUCKETS,
    VISIBILITY_RANK_CEILING,
)
from apps.common.dates import DateWindow

logger = logging.getLogger("rankvista.rankings")

MongoUnavailable = sourcedb.SourceUnavailable


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def matrix_rows(
    *, project_id: str | int, asin: str, keyword_lowers: list[str], window: DateWindow
) -> dict[str, dict[date, dict[str, Any]]]:
    """Rank observations for the paged keywords, keyed by keyword then bucket date."""
    if not keyword_lowers:
        return {}

    ranks = sourcedb.table("ranks")
    placeholders = ", ".join(["%s"] * len(keyword_lowers))
    rows = sourcedb.fetch_all(
        f"""SELECT h.keyword, h.rank_date, h.organic_rank, h.choice_badge
            FROM {ranks} h
            WHERE h.project_id = %s AND h.asin = %s
              AND h.rank_date BETWEEN %s AND %s
              AND LOWER(h.keyword) IN ({placeholders})""",
        [str(project_id), asin, window.start, window.end, *keyword_lowers],
    )

    grid: dict[str, dict[date, dict[str, Any]]] = {}
    for row in rows:
        observed = _as_date(row.get("rank_date"))
        if observed is None:
            continue
        bucket = window.bucket_for(observed)
        key = row["keyword"].lower()
        rank = row.get("organic_rank")
        rank = int(rank) if rank and int(rank) > 0 else -1
        cell = grid.setdefault(key, {})
        existing = cell.get(bucket)
        # Within a weekly/monthly bucket the best (lowest positive) rank wins.
        if existing is None or _is_better(rank, existing.get("rank")):
            cell[bucket] = {"rank": rank, "is_amazon_choice": bool(row.get("choice_badge"))}
        elif row.get("choice_badge"):
            existing["is_amazon_choice"] = True
    return grid


def _is_better(candidate: Any, current: Any) -> bool:
    if not isinstance(candidate, int) or candidate <= 0:
        return False
    if not isinstance(current, int) or current <= 0:
        return True
    return candidate < current


def tracked_dates(*, project_id: str | int, asin: str, window: DateWindow) -> set[date]:
    """Dates on which any rank check ran, separating untracked from unranked."""
    ranks = sourcedb.table("ranks")
    rows = sourcedb.fetch_all(
        f"""SELECT DISTINCT h.rank_date FROM {ranks} h
            WHERE h.project_id = %s AND h.asin = %s AND h.rank_date BETWEEN %s AND %s""",
        [str(project_id), asin, window.start, window.end],
    )
    return {d for d in (_as_date(row["rank_date"]) for row in rows) if d is not None}


def daily_overview(*, project_id: str | int, asin: str, window: DateWindow) -> list[dict[str, Any]]:
    """Per-day visibility, average position, badge count and rank distribution."""
    ranks = sourcedb.table("ranks")
    buckets_sql = ",\n".join(
        f"SUM(CASE WHEN h.organic_rank BETWEEN {spec['min']} AND {spec['max']} THEN 1 ELSE 0 END) AS `b_{spec['key']}`"
        for spec in RANK_DISTRIBUTION_BUCKETS
    )
    rows = sourcedb.fetch_all(
        f"""SELECT h.rank_date,
                   COUNT(*) AS tracked,
                   SUM(CASE WHEN h.organic_rank > 0 THEN 1 ELSE 0 END) AS ranked,
                   SUM(CASE WHEN h.organic_rank > 0 AND h.organic_rank <= %s THEN 1 ELSE 0 END) AS page_one,
                   SUM(CASE WHEN h.organic_rank > 0 THEN h.organic_rank ELSE 0 END) AS rank_sum,
                   SUM(CASE WHEN h.choice_badge = 1 THEN 1 ELSE 0 END) AS badges,
                   {buckets_sql}
            FROM {ranks} h
            WHERE h.project_id = %s AND h.asin = %s AND h.rank_date BETWEEN %s AND %s
            GROUP BY h.rank_date
            ORDER BY h.rank_date ASC""",
        [VISIBILITY_RANK_CEILING, str(project_id), asin, window.start, window.end],
    )

    series: list[dict[str, Any]] = []
    for row in rows:
        observed = _as_date(row["rank_date"])
        if observed is None:
            continue
        tracked = int(row.get("tracked") or 0)
        ranked = int(row.get("ranked") or 0)
        series.append(
            {
                "date": observed,
                "tracked": tracked,
                "ranked": ranked,
                "visibility": round(100 * int(row.get("page_one") or 0) / tracked, 1) if tracked else 0.0,
                "avg_position": round(int(row.get("rank_sum") or 0) / ranked, 1) if ranked else None,
                "badges": int(row.get("badges") or 0),
                "distribution": {
                    spec["key"]: int(row.get(f"b_{spec['key']}") or 0)
                    for spec in RANK_DISTRIBUTION_BUCKETS
                },
            }
        )
    return series


def keyword_history(
    *, project_id: str | int, asin: str, keyword_lower: str, window: DateWindow
) -> list[dict[str, Any]]:
    """Full rank history for a single keyword, oldest first."""
    ranks = sourcedb.table("ranks")
    rows = sourcedb.fetch_all(
        f"""SELECT h.rank_date, h.organic_rank, h.sponsored_rank, h.choice_badge
            FROM {ranks} h
            WHERE h.project_id = %s AND h.asin = %s AND LOWER(h.keyword) = %s
              AND h.rank_date BETWEEN %s AND %s
            ORDER BY h.rank_date ASC""",
        [str(project_id), asin, keyword_lower, window.start, window.end],
    )
    history = []
    for row in rows:
        rank = row.get("organic_rank")
        history.append(
            {
                "date": _as_date(row["rank_date"]),
                "rank": int(rank) if rank and int(rank) > 0 else -1,
                "sponsored_rank": row.get("sponsored_rank"),
                "is_amazon_choice": bool(row.get("choice_badge")),
            }
        )
    return history


def latest_observation_date(*, project_id: str | int, asin: str) -> date | None:
    ranks = sourcedb.table("ranks")
    row = sourcedb.fetch_one(
        f"SELECT MAX(rank_date) AS latest FROM {ranks} WHERE project_id = %s AND asin = %s",
        [str(project_id), asin],
    )
    return _as_date(row["latest"]) if row and row.get("latest") else None


def available_range(*, project_id: str | int, asin: str) -> tuple[date | None, date | None]:
    """Oldest and newest observation for an ASIN, used to clamp the date picker."""
    ranks = sourcedb.table("ranks")
    def produce():
        return sourcedb.fetch_one(
            f"SELECT MIN(rank_date) AS lo, MAX(rank_date) AS hi FROM {ranks} "
            f"WHERE project_id = %s AND asin = %s",
            [str(project_id), asin],
        )

    row = cached_call(f"rv:rank:range:v1:{project_id}:{asin}", CACHE_TTL_LONG, produce)
    if not row:
        return None, None
    return _as_date(row.get("lo")), _as_date(row.get("hi"))
