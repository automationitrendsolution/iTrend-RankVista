"""Centralised constants shared across the platform."""

from __future__ import annotations

# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------
DEFAULT_PAGE_SIZE = 10
PAGE_SIZE_CHOICES = (10, 25, 50, 250)
MAX_PAGE_SIZE = 250

# --------------------------------------------------------------------------
# Marketplaces
# --------------------------------------------------------------------------
MARKETPLACES: dict[str, dict[str, str]] = {
    "US": {"code": "US", "label": "United States", "flag": "\U0001F1FA\U0001F1F8", "domain": "amazon.com"},
    "CA": {"code": "CA", "label": "Canada", "flag": "\U0001F1E8\U0001F1E6", "domain": "amazon.ca"},
    "MX": {"code": "MX", "label": "Mexico", "flag": "\U0001F1F2\U0001F1FD", "domain": "amazon.com.mx"},
    "BR": {"code": "BR", "label": "Brazil", "flag": "\U0001F1E7\U0001F1F7", "domain": "amazon.com.br"},
    "UK": {"code": "UK", "label": "United Kingdom", "flag": "\U0001F1EC\U0001F1E7", "domain": "amazon.co.uk"},
    "DE": {"code": "DE", "label": "Germany", "flag": "\U0001F1E9\U0001F1EA", "domain": "amazon.de"},
    "FR": {"code": "FR", "label": "France", "flag": "\U0001F1EB\U0001F1F7", "domain": "amazon.fr"},
    "IT": {"code": "IT", "label": "Italy", "flag": "\U0001F1EE\U0001F1F9", "domain": "amazon.it"},
    "ES": {"code": "ES", "label": "Spain", "flag": "\U0001F1EA\U0001F1F8", "domain": "amazon.es"},
    "NL": {"code": "NL", "label": "Netherlands", "flag": "\U0001F1F3\U0001F1F1", "domain": "amazon.nl"},
    "SE": {"code": "SE", "label": "Sweden", "flag": "\U0001F1F8\U0001F1EA", "domain": "amazon.se"},
    "PL": {"code": "PL", "label": "Poland", "flag": "\U0001F1F5\U0001F1F1", "domain": "amazon.pl"},
    "TR": {"code": "TR", "label": "Turkey", "flag": "\U0001F1F9\U0001F1F7", "domain": "amazon.com.tr"},
    "AE": {"code": "AE", "label": "United Arab Emirates", "flag": "\U0001F1E6\U0001F1EA", "domain": "amazon.ae"},
    "SA": {"code": "SA", "label": "Saudi Arabia", "flag": "\U0001F1F8\U0001F1E6", "domain": "amazon.sa"},
    "IN": {"code": "IN", "label": "India", "flag": "\U0001F1EE\U0001F1F3", "domain": "amazon.in"},
    "JP": {"code": "JP", "label": "Japan", "flag": "\U0001F1EF\U0001F1F5", "domain": "amazon.co.jp"},
    "AU": {"code": "AU", "label": "Australia", "flag": "\U0001F1E6\U0001F1FA", "domain": "amazon.com.au"},
    "SG": {"code": "SG", "label": "Singapore", "flag": "\U0001F1F8\U0001F1EC", "domain": "amazon.sg"},
}

DEFAULT_MARKETPLACE = "US"


def marketplace(code: str | None) -> dict[str, str]:
    """Return marketplace metadata, falling back to a neutral placeholder."""
    if not code:
        code = DEFAULT_MARKETPLACE
    return MARKETPLACES.get(
        code.upper(),
        {"code": code.upper(), "label": code.upper(), "flag": "\U0001F3F3", "domain": ""},
    )


# --------------------------------------------------------------------------
# Ranking semantics
# --------------------------------------------------------------------------
RANK_NOT_RANKED = -1  # tracked on this date but absent from search results
RANK_NOT_TRACKED = None  # keyword was not being tracked on this date
RANK_CHECKING = -2  # a check is currently in flight

MAX_RANK_POSITION = 306  # Amazon organic search depth ceiling used by the platform

RANK_DISTRIBUTION_BUCKETS = (
    {"key": "1-3", "label": "1-3", "min": 1, "max": 3, "tone": "excellent"},
    {"key": "4-10", "label": "4-10", "min": 4, "max": 10, "tone": "good"},
    {"key": "11-50", "label": "11-50", "min": 11, "max": 50, "tone": "average"},
    {"key": "51-100", "label": "51-100", "min": 51, "max": 100, "tone": "weak"},
    {"key": "100+", "label": "100+", "min": 101, "max": MAX_RANK_POSITION, "tone": "poor"},
)

# Visibility is the share of tracked keywords ranking on Amazon page one.
VISIBILITY_RANK_CEILING = 10

# --------------------------------------------------------------------------
# Date interval / range controls
# --------------------------------------------------------------------------
INTERVAL_DAILY = "daily"
INTERVAL_WEEKLY = "weekly"
INTERVAL_MONTHLY = "monthly"
INTERVALS = (INTERVAL_DAILY, INTERVAL_WEEKLY, INTERVAL_MONTHLY)

DATE_RANGE_PRESETS = (
    {"key": "L7D", "label": "L7D", "days": 7},
    {"key": "L30D", "label": "L30D", "days": 30},
    {"key": "L60D", "label": "L60D", "days": 60},
    {"key": "L90D", "label": "L90D", "days": 90},
    {"key": "custom", "label": "Custom", "days": 0},
)
DEFAULT_DATE_RANGE = "L30D"
MAX_MATRIX_COLUMNS = 120  # hard ceiling on rendered date columns

# --------------------------------------------------------------------------
# Sorting
# --------------------------------------------------------------------------
PROJECT_SORT_OPTIONS = (
    {"key": "last_opened", "label": "Last opened", "field": "last_opened_at", "direction": -1},
    {"key": "recent", "label": "Recently created", "field": "created_at", "direction": -1},
    {"key": "name_asc", "label": "Name A-Z", "field": "name_lower", "direction": 1},
    {"key": "name_desc", "label": "Name Z-A", "field": "name_lower", "direction": -1},
    {"key": "asins_desc", "label": "Most ASINs", "field": "asin_count", "direction": -1},
    {"key": "keywords_desc", "label": "Most keywords", "field": "keyword_count", "direction": -1},
)
DEFAULT_PROJECT_SORT = "last_opened"

# --------------------------------------------------------------------------
# Cache keys / TTLs (seconds)
# --------------------------------------------------------------------------
CACHE_TTL_SHORT = 60
CACHE_TTL_MEDIUM = 300
CACHE_TTL_LONG = 1800

CACHE_KEY_USAGE_COUNTS = "rv:usage:counts:v1"
CACHE_KEY_PROJECT_SUMMARY = "rv:project:summary:v1:{project_id}"
CACHE_KEY_RANK_OVERVIEW = "rv:rank:overview:v1:{project_id}:{asin}:{start}:{end}:{interval}"
