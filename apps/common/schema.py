"""Canonical MongoDB schema. Additive only: indexes are created, never dropped.
Remap collection names via MONGODB_COLLECTION_* to mount an existing database."""

from __future__ import annotations

import logging
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import PyMongoError

from apps.common.mongo import get_collection

logger = logging.getLogger("rankvista.schema")

# Logical collection names, resolved to physical names via settings.MONGODB.
PROJECTS = "projects"
ASINS = "asins"
KEYWORDS = "keywords"
RANKINGS = "rankings"

ALL_COLLECTIONS = (PROJECTS, ASINS, KEYWORDS, RANKINGS)

# Document shapes: the contract the repositories rely on.
SCHEMA: dict[str, dict[str, str]] = {
    PROJECTS: {
        "project_id": "int - stable public identifier used in URLs",
        "name": "str - display name",
        "name_lower": "str - lowercase copy for case-insensitive search and sort",
        "marketplace": "str - marketplace code, e.g. US",
        "primary_asin": "str - headline ASIN shown on the project card",
        "image_url": "str - product image for the card",
        "asin_count": "int - denormalised count of tracked ASINs",
        "keyword_count": "int - denormalised count of tracked keywords",
        "status": "str - active | archived",
        "owner_id": "int|null - Django user id that owns the project",
        "tags": "list[str] - free-form labels used by filters",
        "created_at": "datetime (UTC)",
        "updated_at": "datetime (UTC)",
        "last_opened_at": "datetime (UTC) - drives the default sort",
    },
    ASINS: {
        "project_id": "int - parent project",
        "asin": "str - Amazon ASIN",
        "title": "str - product title",
        "image_url": "str - product image",
        "marketplace": "str - marketplace code",
        "brand": "str - brand name",
        "price": "float - last observed price",
        "is_primary": "bool - headline ASIN of the project",
        "status": "str - active | paused",
        "tracked_keyword_count": "int - denormalised keyword count",
        "created_at": "datetime (UTC)",
        "updated_at": "datetime (UTC)",
    },
    KEYWORDS: {
        "project_id": "int - parent project",
        "asin": "str - ASIN the keyword is tracked against",
        "keyword": "str - search phrase",
        "keyword_lower": "str - lowercase copy for search and uniqueness",
        "search_volume": "int - monthly search volume",
        "kw_sales": "int - estimated keyword sales, last 4 weeks",
        "sales_trend_pct": "float - keyword sales trend %, last 4 weeks",
        "conversion_pct": "float - keyword conversion %, last 4 weeks",
        "is_tracked": "bool - whether rank checks run for this keyword",
        "current_rank": "int|null - most recent organic rank",
        "best_rank": "int|null - best organic rank observed",
        "created_at": "datetime (UTC)",
        "updated_at": "datetime (UTC)",
    },
    RANKINGS: {
        "project_id": "int - parent project",
        "asin": "str - ranked ASIN",
        "keyword_lower": "str - lowercase keyword, joins to keywords.keyword_lower",
        "keyword": "str - original keyword casing",
        "date": "datetime (UTC midnight) - the observation day",
        "rank": "int - organic position; -1 not ranked, -2 check in progress",
        "is_amazon_choice": "bool - Amazon's Choice badge held that day",
        "is_sponsored": "bool - sponsored placement observed that day",
        "page": "int - search results page the ASIN appeared on",
    },
}

# Indexes tuned for the exact access patterns the screens issue.
INDEXES: dict[str, list[IndexModel]] = {
    PROJECTS: [
        IndexModel([("project_id", ASCENDING)], name="uk_project_id", unique=True),
        IndexModel([("owner_id", ASCENDING), ("last_opened_at", DESCENDING)], name="ix_owner_recent"),
        IndexModel([("status", ASCENDING), ("name_lower", ASCENDING)], name="ix_status_name"),
        IndexModel([("marketplace", ASCENDING)], name="ix_marketplace"),
        IndexModel([("name_lower", ASCENDING)], name="ix_name_lower"),
    ],
    ASINS: [
        IndexModel([("project_id", ASCENDING), ("asin", ASCENDING)], name="uk_project_asin", unique=True),
        IndexModel([("project_id", ASCENDING), ("is_primary", DESCENDING)], name="ix_project_primary"),
        IndexModel([("project_id", ASCENDING), ("status", ASCENDING)], name="ix_project_status"),
    ],
    KEYWORDS: [
        IndexModel(
            [("project_id", ASCENDING), ("asin", ASCENDING), ("keyword_lower", ASCENDING)],
            name="uk_project_asin_keyword",
            unique=True,
        ),
        IndexModel(
            [("project_id", ASCENDING), ("asin", ASCENDING), ("kw_sales", DESCENDING)],
            name="ix_project_asin_sales",
        ),
        IndexModel(
            [("project_id", ASCENDING), ("asin", ASCENDING), ("current_rank", ASCENDING)],
            name="ix_project_asin_rank",
        ),
        IndexModel([("project_id", ASCENDING), ("is_tracked", ASCENDING)], name="ix_project_tracked"),
    ],
    RANKINGS: [
        IndexModel(
            [
                ("project_id", ASCENDING),
                ("asin", ASCENDING),
                ("keyword_lower", ASCENDING),
                ("date", DESCENDING),
            ],
            name="uk_rank_observation",
            unique=True,
        ),
        IndexModel(
            [("project_id", ASCENDING), ("asin", ASCENDING), ("date", DESCENDING)],
            name="ix_project_asin_date",
        ),
    ],
}


def ensure_indexes(*, verbose: bool = False) -> dict[str, list[str]]:
    """Create the platform indexes. Idempotent and non-destructive."""
    created: dict[str, list[str]] = {}
    for logical, models in INDEXES.items():
        try:
            names = get_collection(logical).create_indexes(models)
            created[logical] = names
            if verbose:
                logger.info("Indexes ensured on %s: %s", logical, ", ".join(names))
        except PyMongoError as exc:
            logger.warning("Could not ensure indexes on %s: %s", logical, type(exc).__name__)
            created[logical] = []
    return created


def describe() -> dict[str, Any]:
    """Return the documented schema, for the inspect_db command and docs."""
    return {
        "collections": {name: dict(fields) for name, fields in SCHEMA.items()},
        "indexes": {
            name: [model.document["name"] for model in models] for name, models in INDEXES.items()
        },
    }
