"""Project, ASIN, keyword and matrix screens against the live read-only warehouse.
Assertions cover structure and invariants, never values that the upstream sync may change."""

from __future__ import annotations

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------- project grid
def test_project_list_renders(client_as_user, live_project):
    response = client_as_user.get(reverse("projects:list"))
    assert response.status_code == 200
    assert response.context["page_obj"].total > 0


def test_usage_counters_are_aggregated(client_as_user, live_project):
    counters = client_as_user.get(reverse("projects:list")).context["counters"]
    assert counters["projects"] > 0
    assert counters["asins"] > 0
    assert counters["keywords"] > 0


def test_pagination_bounds_the_page(client_as_user, live_project):
    page = client_as_user.get(reverse("projects:list"), {"size": 10}).context["page_obj"]
    assert len(page.items) <= 10
    assert page.size == 10
    if page.total > 10:
        assert page.num_pages > 1


def test_second_page_differs_from_first(client_as_user, live_project):
    first = client_as_user.get(reverse("projects:list"), {"size": 5}).context["page_obj"]
    if first.total <= 5:
        pytest.skip("Not enough projects to paginate.")
    second = client_as_user.get(reverse("projects:list"), {"size": 5, "page": 2}).context["page_obj"]
    assert {p["project_id"] for p in first.items} != {p["project_id"] for p in second.items}


def test_search_narrows_the_result_set(client_as_user, live_project):
    unfiltered = client_as_user.get(reverse("projects:list")).context["page_obj"].total
    response = client_as_user.get(reverse("projects:list"), {"q": live_project["project_id"]})
    filtered = response.context["page_obj"]
    assert 0 < filtered.total <= unfiltered
    assert any(p["project_id"] == live_project["project_id"] for p in filtered.items)


def test_search_with_no_match_is_empty(client_as_user, live_project):
    response = client_as_user.get(reverse("projects:list"), {"q": "zzz-no-such-project-zzz"})
    assert response.context["page_obj"].total == 0
    assert b"No projects match" in response.content


def test_regex_and_sql_metacharacters_are_safe(client_as_user, live_project):
    for term in ["snow(*", "'; DROP TABLE x; --", "%_%", '"quote"']:
        assert client_as_user.get(reverse("projects:list"), {"q": term}).status_code == 200


def test_every_sort_option_is_accepted(client_as_user, live_project):
    for sort in ("last_opened", "recent", "name_asc", "name_desc", "asins_desc", "keywords_desc"):
        response = client_as_user.get(reverse("projects:list"), {"sort": sort})
        assert response.status_code == 200, sort


def test_invalid_sort_falls_back(client_as_user, live_project):
    assert client_as_user.get(reverse("projects:list"), {"sort": "bogus"}).status_code == 200


def test_name_sort_is_ordered(client_as_user, live_project):
    items = client_as_user.get(reverse("projects:list"), {"sort": "name_asc"}).context["page_obj"].items
    names = [p["name"].lower() for p in items]
    assert names == sorted(names)


def test_list_and_grid_view_modes(client_as_user, live_project):
    assert client_as_user.get(reverse("projects:list"), {"view": "list"}).context["view_mode"] == "list"
    assert client_as_user.get(reverse("projects:list"), {"view": "bogus"}).context["view_mode"] == "grid"


def test_htmx_request_returns_a_partial(client_as_user, live_project):
    response = client_as_user.get(reverse("projects:list"), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b"<html" not in response.content


# ------------------------------------------------------------ project detail
def test_detail_redirects_to_asins(client_as_user, live_project):
    response = client_as_user.get(reverse("projects:detail", args=[live_project["project_id"]]))
    assert response.status_code == 302
    assert response.url.endswith("/asins/")


def test_unknown_project_returns_404(client_as_user, warehouse, db):
    for route in ("detail", "asins", "keywords", "ranks", "trends", "quickview"):
        response = client_as_user.get(reverse(f"projects:{route}", args=[987654321]))
        assert response.status_code == 404, route


def test_quickview_renders_a_modal(client_as_user, live_project):
    response = client_as_user.get(reverse("projects:quickview", args=[live_project["project_id"]]))
    assert response.status_code == 200
    assert b"rv-modal" in response.content
    assert b"<html" not in response.content


def test_asin_tab_lists_the_registry(client_as_user, live_project):
    response = client_as_user.get(reverse("projects:asins", args=[live_project["project_id"]]))
    assert response.status_code == 200
    assert response.context["page_obj"].total > 0
    assert live_project["asin"].encode() in response.content


def test_asin_search_narrows_results(client_as_user, live_project):
    response = client_as_user.get(
        reverse("projects:asins", args=[live_project["project_id"]]),
        {"q": live_project["asin"]},
    )
    assert response.context["page_obj"].total >= 1


# ------------------------------------------------------------------ keywords
def test_keyword_tab(client_as_user, live_project):
    response = client_as_user.get(
        reverse("projects:keywords", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    )
    assert response.status_code == 200
    assert response.context["page_obj"].total > 0
    assert response.context["summary"]["keywords"] > 0


def test_keyword_rows_carry_business_metrics(client_as_user, live_project):
    rows = client_as_user.get(
        reverse("projects:keywords", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    ).context["page_obj"].items
    assert rows
    for row in rows:
        assert {"keyword", "kw_sales", "sales_trend_pct", "conversion_pct"} <= set(row)


def test_keyword_search_filter(client_as_user, live_project):
    baseline = client_as_user.get(
        reverse("projects:keywords", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    ).context["page_obj"]
    term = baseline.items[0]["keyword"].split()[0]

    filtered = client_as_user.get(
        reverse("projects:keywords", args=[live_project["project_id"]]),
        {"asin": live_project["asin"], "kq": term},
    ).context["page_obj"]
    assert 0 < filtered.total <= baseline.total
    assert all(term.lower() in row["keyword"].lower() for row in filtered.items)


def test_rank_range_filter_respects_bounds(client_as_user, live_project):
    response = client_as_user.get(
        reverse("projects:ranks", args=[live_project["project_id"]]),
        {"asin": live_project["asin"], "rank_min": 1, "rank_max": 10},
    )
    assert response.status_code == 200
    for row in response.context["rows"]:
        assert row.current_rank is None or 1 <= row.current_rank <= 10


def test_tracked_filter(client_as_user, live_project):
    response = client_as_user.get(
        reverse("projects:keywords", args=[live_project["project_id"]]),
        {"asin": live_project["asin"], "tracked": "tracked"},
    )
    assert response.status_code == 200
    assert all(row["is_tracked"] for row in response.context["page_obj"].items)


# -------------------------------------------------------------- rank matrix
def test_matrix_shape(client_as_user, live_project):
    response = client_as_user.get(
        reverse("projects:ranks", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    )
    assert response.status_code == 200
    columns, rows = response.context["columns"], response.context["rows"]
    assert columns and rows
    assert all(len(row.cells) == len(columns) for row in rows)


def test_matrix_pagination_bounds_rows(client_as_user, live_project):
    response = client_as_user.get(
        reverse("projects:ranks", args=[live_project["project_id"]]),
        {"asin": live_project["asin"], "size": 10},
    )
    assert len(response.context["rows"]) <= 10


def test_matrix_intervals_change_column_count(client_as_user, live_project):
    counts = {}
    for interval in ("daily", "weekly", "monthly"):
        response = client_as_user.get(
            reverse("projects:ranks", args=[live_project["project_id"]]),
            {"asin": live_project["asin"], "interval": interval, "range": "L30D"},
        )
        assert response.status_code == 200
        counts[interval] = len(response.context["columns"])
    assert counts["daily"] >= counts["weekly"] >= counts["monthly"]


def test_matrix_columns_never_exceed_the_cap(client_as_user, live_project):
    from apps.common.constants import MAX_MATRIX_COLUMNS

    response = client_as_user.get(
        reverse("projects:ranks", args=[live_project["project_id"]]),
        {"asin": live_project["asin"], "start": "2020-01-01", "end": "2026-12-31"},
    )
    assert len(response.context["columns"]) <= MAX_MATRIX_COLUMNS


def test_matrix_cells_carry_a_tone(client_as_user, live_project):
    response = client_as_user.get(
        reverse("projects:ranks", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    )
    for row in response.context["rows"]:
        for cell in row.cells:
            assert cell.tone
            assert cell.css.startswith("rv-cell")


def test_window_is_clamped_to_available_data(client_as_user, live_project):
    from apps.rankings import repositories as rank_repo

    _, newest = rank_repo.available_range(
        project_id=live_project["project_id"], asin=live_project["asin"]
    )
    if not newest:
        pytest.skip("No rank history for this ASIN.")
    window = client_as_user.get(
        reverse("projects:ranks", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    ).context["window"]
    assert window.end <= newest


# ---------------------------------------------------------------- analytics
def test_rank_overview_kpis(client_as_user, live_project):
    overview = client_as_user.get(
        reverse("projects:ranks", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    ).context["overview"]
    assert overview["has_data"]
    assert 0 <= overview["visibility"]["value"] <= 100
    assert overview["distribution"]["legend"]


def test_trends_tab(client_as_user, live_project):
    response = client_as_user.get(
        reverse("projects:trends", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    )
    assert response.status_code == 200
    assert len(response.context["metrics"]) == 4


def test_keyword_history_drawer(client_as_user, live_project):
    keyword = client_as_user.get(
        reverse("projects:keywords", args=[live_project["project_id"]]),
        {"asin": live_project["asin"]},
    ).context["page_obj"].items[0]["keyword"]

    response = client_as_user.get(
        reverse("projects:keyword_detail", args=[live_project["project_id"], keyword]),
        {"asin": live_project["asin"]},
    )
    assert response.status_code == 200
    assert response.context["history"]


# ------------------------------------------------------------ write surface
def test_create_project_writes_to_the_overlay(client_as_user, warehouse, db):
    response = client_as_user.post(
        reverse("projects:create"),
        {
            "name": "Overlay Test Project",
            "marketplace": "UK",
            "primary_asin": "b0overlay1",
            "image_url": "",
            "tags": "winter, cover",
        },
    )
    assert response.status_code == 302

    from apps.projects import overlay

    project_id = response.url.rstrip("/").split("/")[-1]
    document = overlay.get_one(project_id)
    assert document["name"] == "Overlay Test Project"
    assert document["primary_asin"] == "B0OVERLAY1"
    assert document["tags"] == ["winter", "cover"]


def test_create_project_validates_asin(client_as_user, warehouse, db):
    response = client_as_user.post(
        reverse("projects:create"),
        {"name": "Bad ASIN Project", "marketplace": "US", "primary_asin": "TOOSHORT"},
    )
    assert response.status_code == 200
    assert b"exactly 10 letters or digits" in response.content


def test_create_project_validates_name(client_as_user, warehouse, db):
    response = client_as_user.post(
        reverse("projects:create"),
        {"name": "ab", "marketplace": "US", "primary_asin": "B0CF1NXT25"},
    )
    assert response.status_code == 200
    assert b"at least 3 characters" in response.content


def test_edit_project_overrides_the_derived_name(client_as_user, live_project):
    response = client_as_user.post(
        reverse("projects:edit", args=[live_project["project_id"]]),
        {
            "name": "Renamed By Test",
            "marketplace": "US",
            "primary_asin": live_project["asin"],
        },
    )
    assert response.status_code == 302

    from apps.projects import repositories as repo

    assert repo.get_project(live_project["project_id"])["name"] == "Renamed By Test"


def test_archive_hides_the_project_but_keeps_history(client_as_user, live_project):
    from apps.projects import repositories as repo

    project_id = live_project["project_id"]
    client_as_user.post(reverse("projects:archive", args=[project_id]))

    assert repo.get_project(project_id)["status"] == "archived"
    assert repo.has_ranking_data(project_id)

    listed = client_as_user.get(reverse("projects:list")).context["page_obj"].items
    assert all(p["project_id"] != project_id for p in listed)


def test_archive_requires_post(client_as_user, live_project):
    response = client_as_user.get(reverse("projects:archive", args=[live_project["project_id"]]))
    assert response.status_code == 405
