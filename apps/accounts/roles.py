"""Role resolution: reads the database, falls back to the built-in defaults.
Cached so an authorisation check never costs a query per request."""

from __future__ import annotations

from apps.accounts.models import ROLE_RANK, Role
from apps.common.cache import cache_delete, cached_call
from apps.common.constants import CACHE_TTL_MEDIUM

CACHE_KEY = "rv:roles:table:v1"

SYSTEM_DESCRIPTIONS = {
    Role.SUPER_ADMIN: "Full platform access, including user, department and role administration.",
    Role.ADMIN: "Full access to project, ASIN, keyword and ranking data. No platform administration.",
    Role.USER: "Read and analyse project data. Cannot administer the platform.",
}


def _defaults() -> dict[str, dict]:
    """The built-in roles, used before the database is seeded and as a fallback."""
    from apps.accounts.pages import PAGES

    table: dict[str, dict] = {}
    for code, label in Role.choices:
        table[code] = {
            "code": code,
            "label": label,
            "description": SYSTEM_DESCRIPTIONS.get(code, ""),
            "rank": ROLE_RANK.get(code, 0),
            "is_system": True,
            "is_active": True,
            "pages": {item.key for item in PAGES if item.allows(code)},
        }
    return table


def _load() -> dict[str, dict]:
    from apps.accounts.role_models import RoleDefinition

    try:
        rows = list(RoleDefinition.objects.filter(is_active=True).prefetch_related("permissions"))
    except Exception:
        # Before the first migration the table does not exist yet.
        return _defaults()

    if not rows:
        return _defaults()

    table: dict[str, dict] = {}
    for row in rows:
        table[row.code] = {
            "code": row.code,
            "label": row.label,
            "description": row.description,
            "rank": row.rank,
            "is_system": row.is_system,
            "is_active": row.is_active,
            "pages": {p.page_key for p in row.permissions.all() if p.allowed},
        }
    return table


def table() -> dict[str, dict]:
    """Every active role keyed by code. Cached; invalidated on any role write."""
    return cached_call(CACHE_KEY, CACHE_TTL_MEDIUM, _load)


def invalidate() -> None:
    cache_delete(CACHE_KEY)


def get(code: str) -> dict:
    return table().get(code) or _defaults().get(code) or {
        "code": code, "label": code, "description": "", "rank": 0,
        "is_system": False, "is_active": False, "pages": set(),
    }


def rank(code: str) -> int:
    return int(get(code).get("rank") or 0)


def can(code: str, page_key: str) -> bool:
    """Whether the role may open the given page."""
    return page_key in get(code).get("pages", set())


def choices() -> list[tuple[str, str]]:
    """Assignable roles for the user form, highest privilege first."""
    rows = sorted(table().values(), key=lambda row: row["rank"], reverse=True)
    return [(row["code"], row["label"]) for row in rows]


def ordered() -> list[dict]:
    return sorted(table().values(), key=lambda row: row["rank"], reverse=True)
