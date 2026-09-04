"""Editable project metadata stored in MongoDB.
The warehouse account is read-only, so user edits live in an overlay merged over source rows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, IndexModel
from pymongo.errors import PyMongoError

from apps.common.mongo import get_collection

logger = logging.getLogger("rankvista.overlay")

COLLECTION = "project_overlay"

OVERLAY_FIELDS = ("name", "marketplace", "image_url", "tags", "status", "primary_asin")


def ensure_indexes() -> None:
    try:
        get_collection(COLLECTION).create_indexes(
            [
                IndexModel([("project_id", ASCENDING)], name="uk_overlay_project", unique=True),
                IndexModel([("status", ASCENDING)], name="ix_overlay_status"),
            ]
        )
    except PyMongoError as exc:
        logger.warning("Could not ensure overlay indexes: %s", type(exc).__name__)


def get_many(project_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Overlay documents for a page of projects, keyed by project id."""
    if not project_ids:
        return {}
    try:
        cursor = get_collection(COLLECTION).find(
            {"project_id": {"$in": project_ids}}, {"_id": 0}
        )
        return {doc["project_id"]: doc for doc in cursor}
    except PyMongoError as exc:
        logger.warning("Overlay read failed: %s", type(exc).__name__)
        return {}


def get_one(project_id: str) -> dict[str, Any]:
    try:
        return get_collection(COLLECTION).find_one({"project_id": project_id}, {"_id": 0}) or {}
    except PyMongoError:
        return {}


def upsert(project_id: str, data: dict[str, Any], *, owner_id: Any = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    changes = {key: value for key, value in data.items() if key in OVERLAY_FIELDS}
    changes["updated_at"] = now
    if "name" in changes:
        changes["name_lower"] = changes["name"].lower()
    try:
        get_collection(COLLECTION).update_one(
            {"project_id": project_id},
            {
                "$set": changes,
                "$setOnInsert": {"project_id": project_id, "created_at": now, "owner_id": owner_id},
            },
            upsert=True,
        )
    except PyMongoError as exc:
        logger.error("Overlay write failed: %s", type(exc).__name__)
        raise
    return get_one(project_id)


def touch_last_opened(project_id: str) -> None:
    try:
        get_collection(COLLECTION).update_one(
            {"project_id": project_id},
            {
                "$set": {"last_opened_at": datetime.now(timezone.utc)},
                "$setOnInsert": {"project_id": project_id},
            },
            upsert=True,
        )
    except PyMongoError:
        logger.debug("Could not record last_opened for %s", project_id)


def archived_ids() -> set[str]:
    """Project ids hidden from the default listing."""
    try:
        cursor = get_collection(COLLECTION).find({"status": "archived"}, {"_id": 0, "project_id": 1})
        return {doc["project_id"] for doc in cursor}
    except PyMongoError:
        return set()


def recent_order() -> dict[str, datetime]:
    """Last-opened timestamps used by the default project sort."""
    try:
        cursor = get_collection(COLLECTION).find(
            {"last_opened_at": {"$exists": True}}, {"_id": 0, "project_id": 1, "last_opened_at": 1}
        )
        return {doc["project_id"]: doc["last_opened_at"] for doc in cursor}
    except PyMongoError:
        return {}
