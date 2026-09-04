"""Keyword data access over the live warehouse summary table.
The matrix pages keywords first, then fetches ranks only for that page."""

from __future__ import annotations

import logging
from typing import Any

from apps.common import sourcedb
from apps.common.cache import cached_call
from apps.common.constants import CACHE_TTL_LONG, CACHE_TTL_MEDIUM

logger = logging.getLogger("rankvista.keywords")

MongoUnavailable = sourcedb.SourceUnavailable

SORT_SQL = {
    "keyword": "k.keyword ASC",
    "-keyword": "k.keyword DESC",
    "sales": "k.keyword_sales_l4w ASC",
    "-sales": "k.keyword_sales_l4w DESC",
    "trend": "k.trend_l4w ASC",
    "-trend": "k.trend_l4w DESC",
    "conversion": "k.keyword_conversion_l4w ASC",
    "-conversion": "k.keyword_conversion_l4w DESC",
    "volume": "k.asins_in_top_10 DESC",
    "-volume": "k.asins_in_top_10 DESC",
    "rank": "(k.organic_rank = 0 OR k.organic_rank IS NULL) ASC, k.organic_rank ASC",
    "-rank": "k.organic_rank DESC",
}
DEFAULT_SORT = "-sales"


def build_filter(
    project_id: str | int,
    asin: str,
    *,
    search: str = "",
    tracked: str = "",
    rank_min: int | None = None,
    rank_max: int | None = None,
    sales_min: int | None = None,
    conversion_min: float | None = None,
) -> dict[str, Any]:
    return {
        "project_id": str(project_id),
        "asin": asin,
        "search": (search or "").strip(),
        "tracked": tracked or "",
        "rank_min": rank_min,
        "rank_max": rank_max,
        "sales_min": sales_min,
        "conversion_min": conversion_min,
    }


def _where(query: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses = ["k.project_id = %s", "k.asin = %s"]
    params: list[Any] = [query["project_id"], query["asin"]]

    if query.get("search"):
        clauses.append("k.keyword LIKE %s")
        params.append(f"%{query['search']}%")
    if query.get("tracked") == "tracked":
        clauses.append("k.organic_rank > 0")
    elif query.get("tracked") == "untracked":
        clauses.append("(k.organic_rank IS NULL OR k.organic_rank = 0)")
    if query.get("rank_min") is not None:
        clauses.append("k.organic_rank >= %s")
        params.append(query["rank_min"])
    if query.get("rank_max") is not None:
        clauses.append("k.organic_rank <= %s AND k.organic_rank > 0")
        params.append(query["rank_max"])
    if query.get("sales_min") is not None:
        clauses.append("k.keyword_sales_l4w >= %s")
        params.append(query["sales_min"])
    if query.get("conversion_min") is not None:
        clauses.append("k.keyword_conversion_l4w >= %s")
        params.append(query["conversion_min"])

    return " WHERE " + " AND ".join(clauses), params


def latest_snapshot(project_id: str, asin: str):
    """Newest snapshot date for an ASIN, cached because a correlated subquery costs seconds."""
    keywords = sourcedb.table("keywords")

    def produce():
        return sourcedb.scalar(
            f"SELECT MAX(snapshot_date) FROM {keywords} WHERE project_id = %s AND asin = %s",
            [project_id, asin],
            default=None,
        )

    return cached_call(f"rv:kw:snapshot:v1:{project_id}:{asin}", CACHE_TTL_LONG, produce)


def _row(row: dict[str, Any]) -> dict[str, Any]:
    rank = row.get("organic_rank")
    return {
        "keyword": row["keyword"],
        "keyword_lower": row["keyword"].lower(),
        "asin": row.get("asin", ""),
        "search_volume": int(row.get("asins_in_top_10") or 0),
        "kw_sales": int(row.get("keyword_sales_l4w") or 0),
        "sales_trend_pct": float(row.get("trend_l4w") or 0.0),
        "conversion_pct": float(row.get("keyword_conversion_l4w") or 0.0),
        "is_tracked": bool(rank and rank > 0),
        "current_rank": int(rank) if rank and rank > 0 else None,
        "best_rank": int(rank) if rank and rank > 0 else None,
        "tracked_from": row.get("tracked_from"),
    }


def list_keywords(
    *, query: dict[str, Any], sort: str = DEFAULT_SORT, offset: int = 0, limit: int = 25
) -> tuple[list[dict[str, Any]], int]:
    keywords = sourcedb.table("keywords")
    where, params = _where(query)
    snapshot = latest_snapshot(query["project_id"], query["asin"])
    if snapshot is not None:
        where += " AND k.snapshot_date = %s"
        params.append(snapshot)
    order = SORT_SQL.get(sort, SORT_SQL[DEFAULT_SORT])

    total = int(sourcedb.scalar(f"SELECT COUNT(*) FROM {keywords} k{where}", params))
    rows = sourcedb.fetch_all(
        f"SELECT k.keyword, k.asin, k.keyword_sales_l4w, k.keyword_conversion_l4w, k.trend_l4w, "
        f"k.organic_rank, k.asins_in_top_10, k.tracked_from "
        f"FROM {keywords} k{where} ORDER BY {order}, k.keyword ASC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    return [_row(row) for row in rows], total


def count_for_project(project_id: str | int, asin: str | None = None) -> int:
    keywords = sourcedb.table("keywords")
    if asin:
        return int(
            sourcedb.scalar(
                f"SELECT COUNT(DISTINCT keyword) FROM {keywords} WHERE project_id = %s AND asin = %s",
                [str(project_id), asin],
            )
        )
    return int(
        sourcedb.scalar(
            f"SELECT COUNT(DISTINCT keyword) FROM {keywords} WHERE project_id = %s",
            [str(project_id)],
        )
    )


def metric_summary(project_id: str | int, asin: str) -> dict[str, float]:
    """Aggregate keyword business metrics for the ASIN header strip."""
    keywords = sourcedb.table("keywords")
    project_id = str(project_id)
    snapshot = latest_snapshot(project_id, asin)

    def produce():
        return sourcedb.fetch_one(
            f"""SELECT COUNT(*) AS keywords,
                       SUM(CASE WHEN k.organic_rank > 0 THEN 1 ELSE 0 END) AS tracked,
                       SUM(k.keyword_sales_l4w) AS sales,
                       AVG(k.keyword_conversion_l4w) AS avg_conversion,
                       SUM(k.asins_in_top_10) AS search_volume
                FROM {keywords} k
                WHERE k.project_id = %s AND k.asin = %s AND k.snapshot_date = %s""",
            [project_id, asin, snapshot],
        ) or {}

    row = cached_call(f"rv:kw:summary:v1:{project_id}:{asin}", CACHE_TTL_MEDIUM, produce)
    return {
        "keywords": int(row.get("keywords") or 0),
        "tracked": int(row.get("tracked") or 0),
        "sales": int(row.get("sales") or 0),
        "avg_conversion": round(float(row.get("avg_conversion") or 0.0), 1),
        "search_volume": int(row.get("search_volume") or 0),
    }


def upsert_keyword(project_id: str | int, asin: str, keyword: str, data: dict[str, Any]) -> None:
    """The warehouse account is read-only; keywords are managed by the upstream sync."""
    raise sourcedb.SourceUnavailable("Keywords are maintained by the upstream data sync.")
