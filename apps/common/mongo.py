"""MongoDB connection management.
One process-wide client is shared by every repository; PyMongo pools internally."""

from __future__ import annotations

import logging
import threading
from typing import Any

from django.conf import settings
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

logger = logging.getLogger("rankvista.mongo")

_client: MongoClient | None = None
_lock = threading.Lock()


class MongoUnavailable(RuntimeError):
    """Raised when MongoDB cannot be reached or a query fails."""


def get_client() -> MongoClient:
    """Return the shared MongoClient, creating it on first use."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                cfg: dict[str, Any] = settings.MONGODB
                _client = MongoClient(
                    cfg["URI"],
                    serverSelectionTimeoutMS=cfg["TIMEOUT_MS"],
                    connectTimeoutMS=cfg["TIMEOUT_MS"],
                    tz_aware=True,
                    appname="itrend-rankvista",
                )
    return _client


def get_database() -> Database:
    return get_client()[settings.MONGODB["DATABASE"]]


def get_collection(logical_name: str) -> Collection:
    """Resolve a logical collection name through the env-configured mapping,
    so an existing database can be mounted without touching query code."""
    physical = settings.MONGODB["COLLECTIONS"].get(logical_name, logical_name)
    return get_database()[physical]


def ping() -> bool:
    """Return True when the server answers a ping, False otherwise."""
    try:
        get_client().admin.command("ping")
        return True
    except PyMongoError as exc:
        logger.warning("MongoDB ping failed: %s", type(exc).__name__)
        return False


def reset_client() -> None:
    """Drop the cached client. Used by tests and by long-lived workers."""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
        _client = None
