"""Readable project names derived from Amazon product titles.
The warehouse stores no project name, so the primary ASIN's title is condensed."""

from __future__ import annotations

import re

# Amazon titles pack the variant list after a dash, comma, pipe or bracket.
SPLIT_PATTERN = re.compile(r"\s+[-–—|]\s+|,\s+|\s*\(|\s*\[")
WHITESPACE = re.compile(r"\s+")

MAX_NAME_LENGTH = 62


def clean(title: str | None) -> str:
    return WHITESPACE.sub(" ", (title or "").strip())


def shorten(title: str | None, limit: int = MAX_NAME_LENGTH) -> str:
    """Condense a product title into a project-sized label.
    Keeps the leading clause, then trims on a word boundary."""
    text = clean(title)
    if not text:
        return ""

    head = SPLIT_PATTERN.split(text, maxsplit=1)[0].strip()
    # A very short leading clause (a bare brand) is less useful than more context.
    if len(head) < 18 and len(text) > len(head):
        head = text

    if len(head) <= limit:
        return head

    cut = head[:limit].rsplit(" ", 1)[0].rstrip(" ,-–—|")
    return f"{cut}…" if cut else head[:limit]
