"""Server-side pagination primitives shared by every list view.
Pagination is always applied inside the query, never by slicing in Python."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.http import HttpRequest

from apps.common.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PAGE_SIZE_CHOICES


@dataclass(slots=True)
class Page:
    """A single page of results plus everything a template needs to render it."""

    items: list[Any]
    total: int
    number: int
    size: int

    @property
    def num_pages(self) -> int:
        if self.size <= 0:
            return 1
        return max(1, -(-self.total // self.size))

    @property
    def has_previous(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.num_pages

    @property
    def previous_number(self) -> int:
        return max(1, self.number - 1)

    @property
    def next_number(self) -> int:
        return min(self.num_pages, self.number + 1)

    @property
    def start_index(self) -> int:
        return 0 if self.total == 0 else (self.number - 1) * self.size + 1

    @property
    def end_index(self) -> int:
        return min(self.number * self.size, self.total)

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    @property
    def page_range(self) -> list[int | None]:
        """Condensed page list: 1 ... n-1 n n+1 ... last (None renders an ellipsis)."""
        total_pages = self.num_pages
        if total_pages <= 7:
            return list(range(1, total_pages + 1))

        current = self.number
        pages: list[int | None] = [1]
        window_start = max(2, current - 1)
        window_end = min(total_pages - 1, current + 1)

        if window_start > 2:
            pages.append(None)
        pages.extend(range(window_start, window_end + 1))
        if window_end < total_pages - 1:
            pages.append(None)
        pages.append(total_pages)
        return pages

    @property
    def size_choices(self) -> tuple[int, ...]:
        return PAGE_SIZE_CHOICES


@dataclass(slots=True)
class PageRequest:
    """Validated pagination parameters pulled from the query string."""

    number: int = 1
    size: int = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size

    def build(self, items: list[Any], total: int) -> Page:
        return Page(items=items, total=total, number=self.number, size=self.size)


def parse_page_request(
    request: HttpRequest,
    *,
    page_param: str = "page",
    size_param: str = "size",
    default_size: int = DEFAULT_PAGE_SIZE,
) -> PageRequest:
    """Read and clamp pagination parameters, tolerating malformed input."""
    try:
        number = int(request.GET.get(page_param, 1))
    except (TypeError, ValueError):
        number = 1
    try:
        size = int(request.GET.get(size_param, default_size))
    except (TypeError, ValueError):
        size = default_size

    number = max(1, number)
    size = max(1, min(size, MAX_PAGE_SIZE))
    return PageRequest(number=number, size=size)


def querystring(request: HttpRequest, **overrides: Any) -> str:
    """Rebuild the current query string with overrides applied.
    Keys set to None are dropped, which keeps shareable URLs clean."""
    params = request.GET.copy()
    for key, value in overrides.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""
