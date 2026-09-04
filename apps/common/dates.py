"""Date-range and interval handling for every time-series screen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from django.http import HttpRequest

from apps.common.constants import (
    DATE_RANGE_PRESETS,
    DEFAULT_DATE_RANGE,
    INTERVAL_DAILY,
    INTERVAL_MONTHLY,
    INTERVAL_WEEKLY,
    INTERVALS,
    MAX_MATRIX_COLUMNS,
)

PRESET_DAYS = {p["key"]: p["days"] for p in DATE_RANGE_PRESETS}


def utc_midnight(value: date) -> datetime:
    """Normalise a date to a timezone-aware UTC midnight datetime."""
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class DateWindow:
    """A resolved, inclusive date range plus the bucketing interval."""

    start: date
    end: date
    interval: str = INTERVAL_DAILY
    preset: str = DEFAULT_DATE_RANGE

    @property
    def start_dt(self) -> datetime:
        return utc_midnight(self.start)

    @property
    def end_dt(self) -> datetime:
        """Exclusive upper bound, so Mongo range queries stay half-open."""
        return utc_midnight(self.end) + timedelta(days=1)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def label(self) -> str:
        return f"{self.start.strftime('%b %-d')} - {self.end.strftime('%b %-d, %Y')}"

    def dates(self) -> list[date]:
        """Every calendar day in the window, oldest first."""
        return [self.start + timedelta(days=offset) for offset in range(self.days)]

    def buckets(self) -> list[date]:
        """Representative dates for the interval, newest first and column-capped.
        Weekly buckets to the ISO Monday, monthly to the first of the month."""
        if self.interval == INTERVAL_WEEKLY:
            seen: dict[date, None] = {}
            for day in self.dates():
                seen.setdefault(day - timedelta(days=day.weekday()), None)
            values = list(seen)
        elif self.interval == INTERVAL_MONTHLY:
            seen = {}
            for day in self.dates():
                seen.setdefault(day.replace(day=1), None)
            values = list(seen)
        else:
            values = self.dates()

        values.sort(reverse=True)
        return values[:MAX_MATRIX_COLUMNS]

    def bucket_for(self, value: date) -> date:
        if self.interval == INTERVAL_WEEKLY:
            return value - timedelta(days=value.weekday())
        if self.interval == INTERVAL_MONTHLY:
            return value.replace(day=1)
        return value


def resolve_window(
    request: HttpRequest,
    *,
    default_preset: str = DEFAULT_DATE_RANGE,
    default_interval: str = INTERVAL_DAILY,
) -> DateWindow:
    """Build a DateWindow from query parameters, clamping anything invalid."""
    interval = (request.GET.get("interval") or default_interval).lower()
    if interval not in INTERVALS:
        interval = default_interval

    preset = request.GET.get("range") or default_preset
    end = today_utc()

    custom_start = parse_date(request.GET.get("start"))
    custom_end = parse_date(request.GET.get("end"))

    if custom_start and custom_end:
        preset = "custom"
        start, end = custom_start, custom_end
        if start > end:
            start, end = end, start
    else:
        days = PRESET_DAYS.get(preset)
        if not days:
            preset = default_preset
            days = PRESET_DAYS[default_preset]
        start = end - timedelta(days=days - 1)

    # Guard against absurd custom ranges reaching the aggregation pipeline.
    max_span = timedelta(days=730)
    if end - start > max_span:
        start = end - max_span

    return DateWindow(start=start, end=end, interval=interval, preset=preset)


def format_window_label(window: DateWindow) -> str:
    """Human label for the date picker, e.g. 'Aug 5 - Sep 3, 2026'."""
    start = f"{window.start.strftime('%b')} {window.start.day}"
    end = f"{window.end.strftime('%b')} {window.end.day}, {window.end.year}"
    return f"{start} - {end}"


def format_column_label(value: date, interval: str) -> str:
    """Short column heading used by the ranking matrix header."""
    if interval == INTERVAL_MONTHLY:
        return value.strftime("%b %y")
    if interval == INTERVAL_WEEKLY:
        return f"W{value.isocalendar().week:02d}"
    return f"{value.day:02d} {value.strftime('%b')}"
