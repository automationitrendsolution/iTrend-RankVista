"""Multi-series line chart geometry.
Paths, gridlines and ticks are computed here so the browser only draws SVG."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

WIDTH = 1000
HEIGHT = 300
PAD_LEFT = 54
PAD_RIGHT = 16
PAD_TOP = 14
PAD_BOTTOM = 30

PLOT_W = WIDTH - PAD_LEFT - PAD_RIGHT
PLOT_H = HEIGHT - PAD_TOP - PAD_BOTTOM

# Distinct, accessible hues that stay apart in both themes.
SERIES_COLORS = (
    "#16a06a", "#2f6df0", "#e8912a", "#6f5cf0", "#e0518b", "#e8b93a",
    "#0fa3a3", "#c0522b",
)


@dataclass(slots=True)
class Series:
    """One plotted year."""

    name: str
    color: str
    path: str
    total: int
    points: list[dict[str, Any]] = field(default_factory=list)

    @property
    def hover(self) -> str:
        return json.dumps(self.points, separators=(",", ":"))


@dataclass(slots=True)
class LineChart:
    """Everything the template needs to render the chart."""

    series: list[Series] = field(default_factory=list)
    x_ticks: list[dict[str, Any]] = field(default_factory=list)
    y_ticks: list[dict[str, Any]] = field(default_factory=list)
    width: int = WIDTH
    height: int = HEIGHT
    plot_left: int = PAD_LEFT
    plot_right: int = WIDTH - PAD_RIGHT
    plot_top: int = PAD_TOP
    plot_bottom: int = HEIGHT - PAD_BOTTOM
    has_data: bool = False
    left_pct: float = round(PAD_LEFT / WIDTH * 100, 3)


def _nice_ceiling(value: float) -> float:
    """Round an axis maximum up to a readable 1/2/5 x 10^n step."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** (len(str(int(value))) - 1)
    for step in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
        candidate = step * magnitude
        if value <= candidate:
            return candidate
    return 10 * magnitude


def _format_tick(value: float) -> str:
    """Short axis label; trailing zeros are dropped so 1.25M does not read as 1.2M."""
    for divisor, suffix in ((1_000_000, "M"), (1_000, "K")):
        if value >= divisor:
            return f"{value / divisor:.2f}".rstrip("0").rstrip(".") + suffix
    return f"{value:.0f}"


def build(
    *,
    labels: list[str],
    series: list[dict[str, Any]],
    value_key: str = "values",
    name_key: str = "year",
) -> LineChart:
    """Turn per-series numeric lists into SVG paths on a shared axis."""
    if not labels or not series:
        return LineChart()

    peak = max(
        (value for row in series for value in row[value_key] if value is not None),
        default=0,
    )
    if peak <= 0:
        return LineChart()

    top = _nice_ceiling(peak)
    step_x = PLOT_W / max(1, len(labels) - 1)

    def x_at(index: int) -> float:
        return round(PAD_LEFT + index * step_x, 2)

    def y_at(value: float) -> float:
        return round(PAD_TOP + (1 - value / top) * PLOT_H, 2)

    built: list[Series] = []
    for position, row in enumerate(series):
        values = row[value_key]
        color = SERIES_COLORS[position % len(SERIES_COLORS)]

        commands: list[str] = []
        points: list[dict[str, Any]] = []
        drawing = False
        for index, value in enumerate(values):
            if value is None:
                # A gap breaks the line rather than inventing a data point.
                drawing = False
                continue
            x, y = x_at(index), y_at(value)
            commands.append(f"{'M' if not drawing else 'L'} {x} {y}")
            drawing = True
            points.append(
                {
                    "i": index,
                    "x": x,
                    "y": y,
                    "value": int(value),
                    "label": labels[index] if index < len(labels) else "",
                    "series": str(row[name_key]),
                }
            )

        if points:
            built.append(
                Series(
                    name=str(row[name_key]),
                    color=color,
                    path=" ".join(commands),
                    total=int(row.get("total") or sum(p["value"] for p in points)),
                    points=points,
                )
            )

    # Five horizontal guides read cleanly without crowding the plot.
    y_ticks = []
    for step in range(5):
        value = top * step / 4
        y = y_at(value)
        y_ticks.append(
            {"y": y, "pct": round(y / HEIGHT * 100, 3), "label": _format_tick(value)}
        )

    # Thin dense axes so week labels do not collide.
    stride = max(1, round(len(labels) / 12))
    x_ticks = [
        {"x": x_at(index), "pct": round(x_at(index) / WIDTH * 100, 3), "label": label}
        for index, label in enumerate(labels)
        if index % stride == 0
    ]

    return LineChart(series=built, x_ticks=x_ticks, y_ticks=y_ticks, has_data=bool(built))
