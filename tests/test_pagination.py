"""Pagination primitives: clamping, page ranges and shareable query strings."""

from __future__ import annotations

from django.test import RequestFactory

from apps.common.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from apps.common.pagination import Page, parse_page_request, querystring

rf = RequestFactory()


def test_defaults_when_no_parameters():
    """Tables open at 10 rows; larger pages are opt-in."""
    page_req = parse_page_request(rf.get("/projects/"))
    assert page_req.number == 1
    assert page_req.size == DEFAULT_PAGE_SIZE == 10
    assert page_req.offset == 0


def test_parses_valid_parameters():
    page_req = parse_page_request(rf.get("/projects/?page=3&size=50"))
    assert page_req.number == 3
    assert page_req.size == 50
    assert page_req.offset == 100


def test_clamps_malformed_and_out_of_range_values():
    assert parse_page_request(rf.get("/?page=abc&size=xyz")).number == 1
    assert parse_page_request(rf.get("/?page=-4")).number == 1
    assert parse_page_request(rf.get("/?size=0")).size == 1
    assert parse_page_request(rf.get("/?size=99999")).size == MAX_PAGE_SIZE


def test_page_arithmetic():
    page = Page(items=list(range(25)), total=225, number=3, size=25)
    assert page.num_pages == 9
    assert page.start_index == 51
    assert page.end_index == 75
    assert page.has_previous and page.has_next
    assert page.previous_number == 2 and page.next_number == 4
    assert not page.is_empty


def test_empty_page():
    page = Page(items=[], total=0, number=1, size=25)
    assert page.is_empty
    assert page.num_pages == 1
    assert page.start_index == 0 and page.end_index == 0
    assert not page.has_previous and not page.has_next


def test_last_page_is_partial():
    page = Page(items=list(range(5)), total=105, number=5, size=25)
    assert page.num_pages == 5
    assert page.end_index == 105
    assert not page.has_next


def test_short_page_range_has_no_ellipsis():
    page = Page(items=[], total=100, number=2, size=25)
    assert page.page_range == [1, 2, 3, 4]


def test_long_page_range_collapses_with_ellipsis():
    page = Page(items=[], total=500, number=10, size=25)
    page_range = page.page_range
    assert page_range[0] == 1
    assert page_range[-1] == 20
    assert None in page_range
    assert 10 in page_range


def test_page_beyond_the_end_stays_navigable():
    page = Page(items=[], total=50, number=99, size=25)
    assert page.num_pages == 2
    assert page.has_previous
    assert not page.has_next


def test_querystring_preserves_and_overrides_filters():
    request = rf.get("/projects/?q=snow&sort=name_asc&page=2")
    result = querystring(request, page=5)
    assert result.startswith("/projects/?")
    assert "q=snow" in result and "sort=name_asc" in result and "page=5" in result


def test_querystring_drops_none_values():
    request = rf.get("/projects/?q=snow&page=2")
    result = querystring(request, q=None)
    assert "q=" not in result and "page=2" in result


def test_querystring_falls_back_to_the_path():
    """An empty string would render href="", which resolves to the directory."""
    assert querystring(rf.get("/projects/")) == "/projects/"
    assert querystring(rf.get("/projects/?q=x"), q=None) == "/projects/"
