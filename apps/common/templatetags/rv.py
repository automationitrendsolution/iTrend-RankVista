"""Presentation-only template helpers.
Nothing here performs a database query; formatting only."""

from __future__ import annotations

from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.common.constants import marketplace as marketplace_meta
from apps.common.pagination import querystring as build_querystring

register = template.Library()


@register.simple_tag
def asset(path: str) -> str:
    """Static URL stamped with the file mtime so edits land without a hard reload.
    Production hashes filenames already, so the stamp is only added in DEBUG."""
    url = static(path)
    if not settings.DEBUG:
        return url
    for root in settings.STATICFILES_DIRS:
        candidate = Path(root) / path
        if candidate.exists():
            return f"{url}?v={int(candidate.stat().st_mtime)}"
    return url


@register.simple_tag(takes_context=True)
def qs(context, **overrides) -> str:
    """Current query string with overrides applied, for shareable links."""
    request = context.get("request")
    if request is None:
        return ""
    return build_querystring(request, **overrides)


@register.filter
def flag(code: str | None) -> str:
    """Marketplace code for the chip. Emoji flags fall back to letters on Windows."""
    return marketplace_meta(code)["code"]


@register.filter
def marketplace_label(code: str | None) -> str:
    return marketplace_meta(code)["label"]


@register.filter
def compact_number(value) -> str:
    """Render large counts as 1.2K / 3.4M so table columns stay narrow."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M".replace(".0M", "M")
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}K".replace(".0K", "K")
    return f"{int(number)}"


@register.filter
def percent(value, decimals: int = 1) -> str:
    try:
        return f"{float(value):.{decimals}f}%"
    except (TypeError, ValueError):
        return "-"


@register.filter
def trend_class(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "rv-trend--flat"
    if number > 0:
        return "rv-trend--up"
    if number < 0:
        return "rv-trend--down"
    return "rv-trend--flat"


@register.filter
def rank_display(value) -> str:
    if value is None:
        return "-"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "-"
    return str(number) if number > 0 else "-"


@register.simple_tag
def sort_indicator(current: str, field: str) -> str:
    """Arrow glyph marking the active sort column."""
    if current == field:
        return mark_safe('<span class="rv-sort rv-sort--asc" aria-hidden="true"></span>')
    if current == f"-{field}":
        return mark_safe('<span class="rv-sort rv-sort--desc" aria-hidden="true"></span>')
    return mark_safe('<span class="rv-sort" aria-hidden="true"></span>')


@register.simple_tag
def initials_badge(user) -> str:
    return format_html('<span class="rv-avatar">{}</span>', getattr(user, "initials", "?"))


@register.filter
def dict_get(mapping, key):
    """Look up a dynamic key inside a dict from a template."""
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return None


@register.filter
def get(mapping, key):
    """Look up a dynamic key in a dict from a template."""
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return None
