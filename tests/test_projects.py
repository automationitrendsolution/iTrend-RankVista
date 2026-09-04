"""Project, ASIN, keyword and ranking-matrix screens against a real MongoDB."""

from __future__ import annotations

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_project_list_renders(client_as_user, seeded_project):
    response = client_as_user.get(reverse("projects:list"))
    assert response.status_code == 200
    assert b"Test Snow Cover" in response.content


def test_usage_counters_are_aggregated(client_as_user, seeded_project):
    counters = client_as_user.get(reverse("projects:list")).context["counters"]
    assert counters["projects"] >= 1
    assert counters["asins"] >= 1
    assert counters["keywords"] >= 3


def test_project_search_matches_and_excludes(client_as_user, seeded_project):
    assert b"Test Snow Cover" in client_as_user.get(reverse("projects:list"), {"q": "snow"}).content
    response = client_as_user.get(reverse("projects:list"), {"q": "no-such-project-xyz"})
    assert b"Test Snow Cover" not in response.content
    assert b"No projects match" in response.content


def test_project_search_by_primary_asin(client_as_user, seeded_project):
    response = client_as_user.get(reverse("projects:list"), {"q": seeded_project["asin"]})
    assert b"Test Snow Cover" in response.content


def test_marketplace_filter(client_as_user, seeded_project):
    assert b"Test Snow Cover" in client_as_user.get(reverse("projects:list"), {"marketplace": "US"}).content
    assert b"Test Snow Cover" not in client_as_user.get(reverse("projects:list"), {"marketplace": "JP"}).content


def test_list_view_mode(client_as_user, seeded_project):
    response = client_as_user.get(reverse("projects:list"), {"view": "list"})
    assert response.status_code == 200
    assert response.context["view_mode"] == "list"


def test_sort_options_are_accepted(client_as_user, seeded_project):
    for sort in ("last_opened", "recent", "name_asc", "name_desc", "asins_desc", "keywords_desc"):
        assert client_as_user.get(reverse("projects:list"), {"sort": sort}).status_code == 200


def test_invalid_sort_falls_back(client_as_user, seeded_project):
    assert client_as_user.get(reverse("projects:list"), {"sort": "'; drop"}).status_code == 200


def test_regex_metacharacters_in_search_are_escaped(client_as_user, seeded_project):
    assert client_as_user.get(reverse("projects:list"), {"q": "snow(*"}).status_code == 200


def test_project_detail_redirects_to_asins(client_as_user, seeded_project):
    response = client_as_user.get(reverse("projects:detail", args=[seeded_project["project_id"]]))
    assert response.status_code == 302
    assert response.url.endswith("/asins/")


def test_unknown_project_returns_404(client_as_user, mongo_db):
    assert client_as_user.get(reverse("projects:detail", args=[123456789])).status_code == 404
    assert client_as_user.get(reverse("projects:ranks", args=[123456789])).status_code == 404


def test_asin_tab(client_as_user, seeded_project):
    response = client_as_user.get(reverse("projects:asins", args=[seeded_project["project_id"]]))
    assert response.status_code == 200
    assert seeded_project["asin"].encode() in response.content


def test_keyword_tab_lists_metrics(client_as_user, seeded_project):
    response = client_as_user.get(
        reverse("projects:keywords", args=[seeded_project["project_id"]]),
        {"asin": seeded_project["asin"]},
    )
    assert response.status_code == 200
    assert b"snow cover" in response.content
    assert response.context["summary"]["keywords"] == 3


def test_keyword_search_filter(client_as_user, seeded_project):
    response = client_as_user.get(
        reverse("projects:keywords", args=[seeded_project["project_id"]]),
        {"asin": seeded_project["asin"], "kq": "windshield"},
    )
    assert b"windshield cover" in response.content
    assert response.context["page_obj"].total == 1


def test_rank_range_filter(client_as_user, seeded_project):
    response = client_as_user.get(
        reverse("projects:ranks", args=[seeded_project["project_id"]]),
        {"asin": seeded_project["asin"], "rank_min": 1, "rank_max": 5},
    )
    assert response.context["page_obj"].total == 1


def test_matrix_builds_rows_and_columns(client_as_user, seeded_project):
    response = client_as_user.get(
        reverse("projects:ranks", args=[seeded_project["project_id"]]),
        {"asin": seeded_project["asin"]},
    )
    assert response.status_code == 200
    assert len(response.context["rows"]) == 3
    assert len(response.context["columns"]) == 30
    assert all(len(row.cells) == 30 for row in response.context["rows"])


def test_matrix_intervals(client_as_user, seeded_project):
    for interval, ceiling in (("daily", 30), ("weekly", 6), ("monthly", 3)):
        response = client_as_user.get(
            reverse("projects:ranks", args=[seeded_project["project_id"]]),
            {"asin": seeded_project["asin"], "interval": interval},
        )
        assert response.status_code == 200
        assert 0 < len(response.context["columns"]) <= ceiling


def test_matrix_pagination_bounds_rows(client_as_user, seeded_project):
    response = client_as_user.get(
        reverse("projects:ranks", args=[seeded_project["project_id"]]),
        {"asin": seeded_project["asin"], "size": 2},
    )
    assert len(response.context["rows"]) == 2
    assert response.context["page_obj"].num_pages == 2


def test_rank_overview_kpis(client_as_user, seeded_project):
    overview = client_as_user.get(
        reverse("projects:ranks", args=[seeded_project["project_id"]]),
        {"asin": seeded_project["asin"]},
    ).context["overview"]
    assert overview["has_data"]
    assert overview["average_position"]["value"] is not None
    assert overview["distribution"]["total"] > 0


def test_trends_tab(client_as_user, seeded_project):
    response = client_as_user.get(
        reverse("projects:trends", args=[seeded_project["project_id"]]),
        {"asin": seeded_project["asin"]},
    )
    assert response.status_code == 200
    assert len(response.context["metrics"]) == 4


def test_keyword_detail_drawer(client_as_user, seeded_project):
    response = client_as_user.get(
        reverse("projects:keyword_detail", args=[seeded_project["project_id"], "snow cover"]),
        {"asin": seeded_project["asin"]},
    )
    assert response.status_code == 200
    assert len(response.context["history"]) == 10
    assert response.context["best_rank"] == 2


def test_create_project(client_as_user, mongo_db):
    response = client_as_user.post(
        reverse("projects:create"),
        {
            "name": "Brand New Project",
            "marketplace": "UK",
            "primary_asin": "b0newasin1",
            "image_url": "",
            "tags": "winter, cover",
        },
    )
    assert response.status_code == 302

    from apps.projects import repositories as repo

    project_id = int(response.url.rstrip("/").split("/")[-1])
    project = repo.get_project(project_id)
    assert project["name"] == "Brand New Project"
    assert project["primary_asin"] == "B0NEWASIN1"
    assert project["tags"] == ["winter", "cover"]


def test_create_project_validates_asin(client_as_user, mongo_db):
    response = client_as_user.post(
        reverse("projects:create"),
        {"name": "Bad ASIN Project", "marketplace": "US", "primary_asin": "TOOSHORT"},
    )
    assert response.status_code == 200
    assert b"exactly 10 letters or digits" in response.content


def test_create_project_validates_name(client_as_user, mongo_db):
    response = client_as_user.post(
        reverse("projects:create"),
        {"name": "ab", "marketplace": "US", "primary_asin": "B0CF1NXT25"},
    )
    assert response.status_code == 200
    assert b"at least 3 characters" in response.content


def test_edit_project(client_as_user, seeded_project):
    response = client_as_user.post(
        reverse("projects:edit", args=[seeded_project["project_id"]]),
        {"name": "Renamed Project", "marketplace": "US", "primary_asin": seeded_project["asin"]},
    )
    assert response.status_code == 302

    from apps.projects import repositories as repo

    assert repo.get_project(seeded_project["project_id"])["name"] == "Renamed Project"


def test_archive_project_hides_it_but_keeps_ranking_history(client_as_user, seeded_project):
    from apps.projects import repositories as repo

    client_as_user.post(reverse("projects:archive", args=[seeded_project["project_id"]]))
    assert repo.get_project(seeded_project["project_id"])["status"] == "archived"
    assert repo.has_ranking_data(seeded_project["project_id"])
    assert b"Test Snow Cover" not in client_as_user.get(reverse("projects:list")).content


def test_archive_requires_post(client_as_user, seeded_project):
    response = client_as_user.get(reverse("projects:archive", args=[seeded_project["project_id"]]))
    assert response.status_code == 405


def test_htmx_request_returns_a_partial(client_as_user, seeded_project):
    response = client_as_user.get(reverse("projects:list"), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b"<html" not in response.content
