"""View models for the ranking matrix.
Builds a fully resolved grid for exactly one page of keywords."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from apps.common.dates import DateWindow, format_column_label
from apps.common.heatmap import RankCell, build_cell
from apps.rankings import repositories as rank_repo


@dataclass(slots=True)
class MatrixColumn:
    """One date column heading in the matrix."""

    value: date
    label: str
    iso: str


@dataclass(slots=True)
class MatrixRow:
    """One keyword row: business metrics plus its resolved rank cells."""

    keyword: str
    keyword_lower: str
    kw_sales: int
    sales_trend_pct: float
    conversion_pct: float
    search_volume: int
    current_rank: int | None
    is_tracked: bool
    cells: list[RankCell]

    @property
    def trend_direction(self) -> str:
        if self.sales_trend_pct > 0:
            return "up"
        if self.sales_trend_pct < 0:
            return "down"
        return "flat"


def build_columns(window: DateWindow) -> list[MatrixColumn]:
    return [
        MatrixColumn(value=value, label=format_column_label(value, window.interval), iso=value.isoformat())
        for value in window.buckets()
    ]


def build_matrix(
    *,
    project_id: int,
    asin: str,
    keywords: list[dict[str, Any]],
    window: DateWindow,
) -> tuple[list[MatrixColumn], list[MatrixRow]]:
    """Assemble the matrix for the current keyword page and date window."""
    columns = build_columns(window)
    if not keywords:
        return columns, []

    keyword_lowers = [kw["keyword_lower"] for kw in keywords]
    grid = rank_repo.matrix_rows(
        project_id=project_id, asin=asin, keyword_lowers=keyword_lowers, window=window
    )
    checked = rank_repo.tracked_dates(project_id=project_id, asin=asin, window=window)
    checked_buckets = {window.bucket_for(value) for value in checked}

    rows: list[MatrixRow] = []
    for keyword in keywords:
        observations = grid.get(keyword["keyword_lower"], {})
        cells: list[RankCell] = []
        for column in columns:
            observation = observations.get(column.value)
            if observation is None:
                # A column the platform checked but this keyword is absent from
                # means "not ranked"; a column never checked means "not tracked".
                rank = -1 if column.value in checked_buckets else None
                cells.append(build_cell(rank, date_label=column.label))
            else:
                cells.append(
                    build_cell(
                        observation.get("rank"),
                        is_amazon_choice=observation.get("is_amazon_choice", False),
                        date_label=column.label,
                    )
                )
        rows.append(
            MatrixRow(
                keyword=keyword.get("keyword", ""),
                keyword_lower=keyword.get("keyword_lower", ""),
                kw_sales=int(keyword.get("kw_sales") or 0),
                sales_trend_pct=float(keyword.get("sales_trend_pct") or 0.0),
                conversion_pct=float(keyword.get("conversion_pct") or 0.0),
                search_volume=int(keyword.get("search_volume") or 0),
                current_rank=keyword.get("current_rank"),
                is_tracked=bool(keyword.get("is_tracked", True)),
                cells=cells,
            )
        )
    return columns, rows
