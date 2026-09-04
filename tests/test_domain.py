"""Heat-map tones, date windows, log redaction and cache degradation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.test import RequestFactory

from apps.common.constants import RANK_CHECKING, RANK_NOT_RANKED
from apps.common.dates import DateWindow, format_column_label, resolve_window
from apps.common.heatmap import build_cell, distribution_bucket, rank_tone
from apps.common.logging_filters import redact

rf = RequestFactory()


# ------------------------------------------------------------------ heatmap
@pytest.mark.parametrize(
    "rank,expected",
    [(1, "r1"), (3, "r1"), (4, "r2"), (9, "r4"), (12, "r5"), (25, "r7"), (75, "r9"), (250, "r10")],
)
def test_rank_tones_are_ordered(rank, expected):
    assert rank_tone(rank) == expected


def test_special_rank_states():
    assert rank_tone(None) == "untracked"
    assert rank_tone(RANK_NOT_RANKED) == "unranked"
    assert rank_tone(RANK_CHECKING) == "checking"
    assert rank_tone(0) == "unranked"


def test_cell_labels():
    assert build_cell(7).label == "7"
    assert build_cell(RANK_NOT_RANKED).label == "-"
    assert build_cell(None).label == ""
    assert build_cell(RANK_CHECKING).label == "⋯"


def test_amazon_choice_only_marks_ranked_cells():
    assert build_cell(2, is_amazon_choice=True).is_amazon_choice
    assert not build_cell(RANK_NOT_RANKED, is_amazon_choice=True).is_amazon_choice
    assert not build_cell(None, is_amazon_choice=True).is_amazon_choice


@pytest.mark.parametrize(
    "rank,bucket",
    [(1, "1-3"), (3, "1-3"), (4, "4-10"), (10, "4-10"), (11, "11-50"), (50, "11-50"),
     (51, "51-100"), (100, "51-100"), (101, "100+"), (400, "100+")],
)
def test_distribution_buckets(rank, bucket):
    assert distribution_bucket(rank) == bucket


def test_unranked_has_no_distribution_bucket():
    assert distribution_bucket(None) is None
    assert distribution_bucket(RANK_NOT_RANKED) is None


# -------------------------------------------------------------------- dates
def test_default_window_is_thirty_days():
    window = resolve_window(rf.get("/"))
    assert window.days == 30
    assert window.interval == "daily"


def test_preset_windows():
    assert resolve_window(rf.get("/?range=L7D")).days == 7
    assert resolve_window(rf.get("/?range=L90D")).days == 90


def test_invalid_preset_and_interval_fall_back():
    window = resolve_window(rf.get("/?range=NOPE&interval=hourly"))
    assert window.days == 30
    assert window.interval == "daily"


def test_custom_range_and_reversed_dates():
    window = resolve_window(rf.get("/?start=2026-01-10&end=2026-01-01"))
    assert window.start == date(2026, 1, 1)
    assert window.end == date(2026, 1, 10)
    assert window.preset == "custom"


def test_absurd_custom_range_is_clamped():
    window = resolve_window(rf.get("/?start=1990-01-01&end=2026-01-01"))
    assert window.days <= 731


def test_daily_buckets_are_newest_first():
    window = DateWindow(start=date(2026, 1, 1), end=date(2026, 1, 5))
    assert window.buckets() == [date(2026, 1, 5), date(2026, 1, 4), date(2026, 1, 3),
                                date(2026, 1, 2), date(2026, 1, 1)]


def test_weekly_buckets_collapse_to_iso_monday():
    window = DateWindow(start=date(2026, 1, 1), end=date(2026, 1, 21), interval="weekly")
    buckets = window.buckets()
    assert len(buckets) == 4
    assert all(value.weekday() == 0 for value in buckets)


def test_monthly_buckets_collapse_to_first_of_month():
    window = DateWindow(start=date(2026, 1, 1), end=date(2026, 3, 31), interval="monthly")
    buckets = window.buckets()
    assert len(buckets) == 3
    assert all(value.day == 1 for value in buckets)


def test_column_count_is_capped():
    window = DateWindow(start=date(2024, 1, 1), end=date(2026, 1, 1))
    assert len(window.buckets()) <= 120


def test_end_bound_is_exclusive_next_midnight():
    window = DateWindow(start=date(2026, 1, 1), end=date(2026, 1, 5))
    assert window.end_dt.date() == date(2026, 1, 6)
    assert window.end_dt.hour == 0


def test_column_labels_by_interval():
    assert format_column_label(date(2026, 9, 3), "daily") == "03 Sep"
    assert format_column_label(date(2026, 9, 1), "monthly") == "Sep 26"
    assert format_column_label(date(2026, 8, 31), "weekly").startswith("W")


# ------------------------------------------------------------------ logging
def test_redaction_hides_credentials():
    assert "hunter2" not in redact('password="hunter2"')
    assert "abc123" not in redact("api_key=abc123")
    assert "tok_live" not in redact("token: tok_live_9")
    assert "s3cret" not in redact("mongodb://user:s3cret@cluster.example.com/db")


def test_redaction_keeps_surrounding_context():
    result = redact("mongodb://user:s3cret@cluster.example.com/db")
    assert "cluster.example.com" in result
    assert "[redacted]" in result


def test_redaction_leaves_safe_text_alone():
    assert redact("Loaded 25 projects in 42ms") == "Loaded 25 projects in 42ms"


# -------------------------------------------------------------------- cache
def test_cached_call_survives_a_broken_backend(monkeypatch):
    from apps.common import cache as cache_helpers

    def boom(*args, **kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(cache_helpers.cache, "get", boom)
    monkeypatch.setattr(cache_helpers.cache, "set", boom)

    calls = []

    def producer():
        calls.append(1)
        return {"projects": 7}

    assert cache_helpers.cached_call("rv:test:key", 60, producer) == {"projects": 7}
    assert len(calls) == 1
