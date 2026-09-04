"""Rank overview KPIs and chart geometry.
Series are aggregated in Mongo and turned into SVG paths here, so the browser draws only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from apps.common.cache import cached_call
from apps.common.constants import (
    CACHE_KEY_RANK_OVERVIEW,
    CACHE_TTL_MEDIUM,
    RANK_DISTRIBUTION_BUCKETS,
)
from apps.common.dates import DateWindow
from apps.rankings import repositories as rank_repo

CHART_WIDTH = 240
CHART_HEIGHT = 64
CHART_PADDING = 4


@dataclass(slots=True)
class Sparkline:
    """Precomputed SVG geometry for one KPI card chart."""

    path: str = ""
    area: str = ""
    points: list[tuple[float, float]] = field(default_factory=list)
    axis_labels: tuple[str, str, str] = ("", "", "")
    has_data: bool = False


def _sparkline(values: list[float | None], *, invert: bool = False) -> Sparkline:
    """Map a numeric series onto the fixed KPI chart box.
    ``invert`` flips the axis so a better (lower) rank sits higher."""
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return Sparkline()

    low, high = min(present), max(present)
    span = (high - low) or 1.0
    usable_w = CHART_WIDTH - 2 * CHART_PADDING
    usable_h = CHART_HEIGHT - 2 * CHART_PADDING
    step = usable_w / max(1, len(values) - 1)

    points: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        if value is None:
            continue
        ratio = (value - low) / span
        if not invert:
            ratio = 1 - ratio
        x = CHART_PADDING + index * step
        y = CHART_PADDING + ratio * usable_h
        points.append((round(x, 2), round(y, 2)))

    if len(points) < 2:
        return Sparkline()

    path = "M " + " L ".join(f"{x} {y}" for x, y in points)
    area = (
        f"{path} L {points[-1][0]} {CHART_HEIGHT} L {points[0][0]} {CHART_HEIGHT} Z"
    )
    top, mid, bottom = (
        _axis_label(high if not invert else low),
        _axis_label((high + low) / 2),
        _axis_label(low if not invert else high),
    )
    return Sparkline(path=path, area=area, points=points, axis_labels=(top, mid, bottom), has_data=True)


def _axis_label(value: float) -> str:
    return f"{value:.0f}" if abs(value) >= 10 else f"{value:.1f}".rstrip("0").rstrip(".")


@dataclass(slots=True)
class DistributionColumn:
    """One stacked bar in the distribution chart, as percentage segments."""

    label: str
    segments: list[dict[str, Any]]
    total: int


def _distribution_columns(series: list[dict[str, Any]]) -> list[DistributionColumn]:
    columns: list[DistributionColumn] = []
    for point in series:
        counts = point["distribution"]
        total = sum(counts.values())
        segments = []
        if total:
            for spec in RANK_DISTRIBUTION_BUCKETS:
                count = counts.get(spec["key"], 0)
                if count:
                    segments.append(
                        {
                            "key": spec["key"],
                            "tone": spec["tone"],
                            "count": count,
                            "height": round(100 * count / total, 2),
                        }
                    )
        columns.append(
            DistributionColumn(label=point["date"].strftime("%d %b"), segments=segments, total=total)
        )
    return columns


def _latest(series: list[dict[str, Any]], key: str) -> Any:
    for point in reversed(series):
        value = point.get(key)
        if value is not None:
            return value
    return None


def build_overview(
    *, project_id: int, asin: str, window: DateWindow
) -> dict[str, Any]:
    """KPI cards and chart geometry for the rank overview strip."""
    cache_key = CACHE_KEY_RANK_OVERVIEW.format(
        project_id=project_id,
        asin=asin or "none",
        start=window.start.isoformat(),
        end=window.end.isoformat(),
        interval=window.interval,
    )

    def produce() -> dict[str, Any]:
        series = rank_repo.daily_overview(project_id=project_id, asin=asin, window=window)
        return _shape_overview(series)

    if not asin:
        return _shape_overview([])
    return cached_call(cache_key, CACHE_TTL_MEDIUM, produce)


def _shape_overview(series: list[dict[str, Any]]) -> dict[str, Any]:
    visibility_values = [point["visibility"] for point in series]
    position_values = [point["avg_position"] for point in series]
    badge_values = [float(point["badges"]) for point in series]

    latest_distribution = series[-1]["distribution"] if series else {}
    distribution_legend = [
        {
            "key": spec["key"],
            "label": spec["label"],
            "tone": spec["tone"],
            "count": latest_distribution.get(spec["key"], 0),
        }
        for spec in reversed(RANK_DISTRIBUTION_BUCKETS)
    ]

    return {
        "has_data": bool(series),
        "visibility": {
            "value": _latest(series, "visibility") or 0.0,
            "chart": _sparkline(visibility_values),
        },
        "average_position": {
            "value": _latest(series, "avg_position"),
            "chart": _sparkline(position_values, invert=True),
        },
        "badges": {
            "value": _latest(series, "badges") or 0,
            "chart": _sparkline(badge_values),
        },
        "distribution": {
            "columns": _distribution_columns(series),
            "legend": distribution_legend,
            "total": sum(latest_distribution.values()) if latest_distribution else 0,
        },
        "series": series,
    }


def trend_points(series: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Flatten one metric into date/value pairs for the Trends tab table."""
    points: list[dict[str, Any]] = []
    for entry in series:
        value = entry.get(key)
        if value is not None:
            points.append({"date": entry["date"], "value": value})
    return points


def summarise_change(points: list[dict[str, Any]]) -> dict[str, Any]:
    """First-to-last delta for a metric, used by the Trends summary tiles."""
    if len(points) < 2:
        return {"start": None, "end": None, "delta": None, "direction": "flat"}
    start, end = points[0]["value"], points[-1]["value"]
    delta = round(end - start, 1)
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    return {"start": start, "end": end, "delta": delta, "direction": direction}


def bucket_dates(series: list[dict[str, Any]]) -> list[date]:
    return [point["date"] for point in series]
