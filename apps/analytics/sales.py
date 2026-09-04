"""Niche unit-sales history, one warehouse table per year.
Aggregated in SQL so the app never pulls raw daily rows across millions of records."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from apps.common import sourcedb
from apps.common.cache import cached_call
from apps.common.constants import CACHE_TTL_LONG

logger = logging.getLogger("rankvista.sales")

MONTH_LABELS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

INTERVAL_MONTHLY = "monthly"
INTERVAL_WEEKLY = "weekly"
SALES_INTERVALS = (INTERVAL_MONTHLY, INTERVAL_WEEKLY)

# 53 covers an ISO year that carries a week 53.
WEEK_COUNT = 53


def available_years() -> list[str]:
    return sorted(settings.SOURCE_DB.get("SALES_TABLES", {}))


def _table(year: str) -> str | None:
    name = settings.SOURCE_DB.get("SALES_TABLES", {}).get(year)
    if not name or "`" in name:
        return None
    return f"`{name}`"


def _year_series(year: str, interval: str, asins: tuple[str, ...]) -> list[int | None]:
    """Units per bucket for one year, or an empty list when the year has no table."""
    table = _table(year)
    if table is None:
        return []

    if interval == INTERVAL_WEEKLY:
        bucket, size = "WEEK(Date, 3)", WEEK_COUNT
    else:
        bucket, size = "MONTH(Date)", 12

    where, params = "", []
    if asins:
        placeholders = ", ".join(["%s"] * len(asins))
        where = f" WHERE ASIN COLLATE utf8mb4_general_ci IN ({placeholders})"
        params = list(asins)

    rows = sourcedb.fetch_all(
        f"SELECT {bucket} AS bucket, SUM(Units) AS units FROM {table}{where} "
        f"GROUP BY bucket ORDER BY bucket",
        params,
    )

    series: list[int | None] = [None] * size
    for row in rows:
        index = int(row["bucket"] or 0)
        # MONTH() is 1-based; WEEK(..., 3) is ISO and also 1-based.
        if 1 <= index <= size:
            series[index - 1] = int(row["units"] or 0)
    return series


def niche_sales(
    *,
    interval: str = INTERVAL_MONTHLY,
    asins: tuple[str, ...] = (),
    years: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Units per bucket for each year, ready to plot.
    `asins` narrows the niche to a project's tracked products."""
    if interval not in SALES_INTERVALS:
        interval = INTERVAL_MONTHLY

    wanted = [year for year in (years or available_years()) if _table(year)]
    if not wanted:
        return {"years": [], "labels": [], "interval": interval, "has_data": False}

    scope = "|".join(sorted(asins)) if asins else "all"
    key = f"rv:sales:v1:{interval}:{','.join(wanted)}:{hash(scope) & 0xFFFFFFFF}"

    def produce() -> dict[str, Any]:
        return {
            year: _year_series(year, interval, asins)
            for year in wanted
        }

    try:
        by_year = cached_call(key, CACHE_TTL_LONG, produce)
    except sourcedb.SourceUnavailable:
        logger.warning("Niche sales unavailable")
        return {"years": [], "labels": [], "interval": interval, "has_data": False}

    labels = (
        list(MONTH_LABELS)
        if interval == INTERVAL_MONTHLY
        else [f"W{index + 1}" for index in range(WEEK_COUNT)]
    )

    years_out = [
        {"year": year, "values": values, "total": sum(v for v in values if v)}
        for year, values in by_year.items()
        if any(v for v in values)
    ]
    years_out.sort(key=lambda row: row["year"])

    return {
        "years": years_out,
        "labels": labels,
        "interval": interval,
        "has_data": bool(years_out),
    }
