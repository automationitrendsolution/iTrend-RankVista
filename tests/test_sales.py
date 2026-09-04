"""Niche sales aggregation: bucketing, year selection and warehouse outages."""

from __future__ import annotations

import pytest
from django.test import override_settings

from apps.analytics import sales
from apps.common.sourcedb import SourceUnavailable

TABLES = {"2025": "2025Windshield", "2026": "2026Windshield"}


def _settings(tables=None):
    return {**sales.settings.SOURCE_DB, "SALES_TABLES": TABLES if tables is None else tables}


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    """Bypass Redis so each test sees its own stubbed warehouse."""
    monkeypatch.setattr(sales, "cached_call", lambda key, ttl, produce: produce())


def test_available_years_are_sorted():
    with override_settings(SOURCE_DB=_settings()):
        assert sales.available_years() == ["2025", "2026"]


def test_backtick_in_a_table_name_is_rejected():
    """The table name is interpolated, so an escape attempt must not reach SQL."""
    with override_settings(SOURCE_DB=_settings({"2025": "bad`name"})):
        assert sales._table("2025") is None


def test_no_configured_tables_reports_no_data():
    with override_settings(SOURCE_DB=_settings({})):
        result = sales.niche_sales()
        assert result["has_data"] is False
        assert result["years"] == []


def test_monthly_buckets_land_on_their_month(monkeypatch):
    monkeypatch.setattr(
        sales.sourcedb, "fetch_all",
        lambda sql, params=None: [{"bucket": 1, "units": 10}, {"bucket": 12, "units": 20}],
    )
    with override_settings(SOURCE_DB=_settings({"2025": "t"})):
        result = sales.niche_sales()
    values = result["years"][0]["values"]
    assert len(values) == 12
    assert values[0] == 10 and values[11] == 20
    assert values[5] is None
    assert result["labels"][0] == "Jan"
    assert result["years"][0]["total"] == 30


def test_weekly_buckets_use_iso_weeks(monkeypatch):
    seen = {}

    def fake(sql, params=None):
        seen["sql"] = sql
        return [{"bucket": 53, "units": 7}]

    monkeypatch.setattr(sales.sourcedb, "fetch_all", fake)
    with override_settings(SOURCE_DB=_settings({"2025": "t"})):
        result = sales.niche_sales(interval="weekly")
    assert "WEEK(Date, 3)" in seen["sql"]
    assert len(result["labels"]) == sales.WEEK_COUNT
    assert result["years"][0]["values"][52] == 7


def test_unknown_interval_falls_back_to_monthly(monkeypatch):
    monkeypatch.setattr(sales.sourcedb, "fetch_all", lambda sql, params=None: [])
    with override_settings(SOURCE_DB=_settings({"2025": "t"})):
        assert sales.niche_sales(interval="hourly")["interval"] == "monthly"


def test_asins_are_bound_as_parameters(monkeypatch):
    seen = {}

    def fake(sql, params=None):
        seen["sql"], seen["params"] = sql, params
        return [{"bucket": 3, "units": 5}]

    monkeypatch.setattr(sales.sourcedb, "fetch_all", fake)
    with override_settings(SOURCE_DB=_settings({"2025": "t"})):
        sales.niche_sales(asins=("B01", "B02"))
    assert seen["params"] == ["B01", "B02"]
    assert seen["sql"].count("%s") == 2
    # Registry and sales tables disagree on collation, so the filter pins one.
    assert "COLLATE utf8mb4_general_ci" in seen["sql"]


def test_a_year_with_no_rows_is_dropped(monkeypatch):
    def fake(sql, params=None):
        return [{"bucket": 1, "units": 4}] if "a2025" in sql else []

    monkeypatch.setattr(sales.sourcedb, "fetch_all", fake)
    with override_settings(SOURCE_DB=_settings({"2025": "a2025", "2026": "a2026"})):
        result = sales.niche_sales()
    assert [row["year"] for row in result["years"]] == ["2025"]


def test_warehouse_outage_degrades_to_an_empty_chart(monkeypatch):
    def boom(sql, params=None):
        raise SourceUnavailable("warehouse down")

    monkeypatch.setattr(sales.sourcedb, "fetch_all", boom)
    with override_settings(SOURCE_DB=_settings({"2025": "t"})):
        result = sales.niche_sales()
    assert result["has_data"] is False
    assert result["years"] == []
