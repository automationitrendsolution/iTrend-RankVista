"""Read-only access to the MySQL warehouse that holds the live rank data.
Every query is parameterised and identifiers come from settings, never from user input."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import pymysql
from django.conf import settings
from pymysql.cursors import DictCursor

logger = logging.getLogger("rankvista.sourcedb")

_pool: list[pymysql.connections.Connection] = []
_lock = threading.Lock()
MAX_POOLED = 4


class SourceUnavailable(RuntimeError):
    """Raised when the warehouse cannot be reached or a query fails."""


def is_enabled() -> bool:
    return bool(settings.SOURCE_DB.get("ENABLED") and settings.SOURCE_DB.get("HOST"))


def table(name: str) -> str:
    """Resolve a logical table name to its configured physical name, backtick-quoted."""
    physical = settings.SOURCE_DB["TABLES"].get(name, name)
    if "`" in physical:
        raise ValueError("Invalid table name in configuration.")
    return f"`{physical}`"


def _connect() -> pymysql.connections.Connection:
    cfg = settings.SOURCE_DB
    return pymysql.connect(
        host=cfg["HOST"],
        port=cfg["PORT"],
        user=cfg["USER"],
        password=cfg["PASSWORD"],
        database=cfg["NAME"],
        connect_timeout=cfg["TIMEOUT"],
        read_timeout=cfg["READ_TIMEOUT"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


@contextmanager
def connection() -> Iterator[pymysql.connections.Connection]:
    """Borrow a pooled connection, reconnecting transparently when it has dropped."""
    if not is_enabled():
        raise SourceUnavailable("The rank data warehouse is not configured.")

    conn = None
    with _lock:
        if _pool:
            conn = _pool.pop()
    try:
        if conn is None:
            conn = _connect()
        else:
            conn.ping(reconnect=True)
    except pymysql.MySQLError as exc:
        logger.error("Warehouse connection failed: %s", type(exc).__name__)
        raise SourceUnavailable("The rank data warehouse is unreachable.") from exc

    try:
        yield conn
    finally:
        with _lock:
            if len(_pool) < MAX_POOLED:
                _pool.append(conn)
            else:
                try:
                    conn.close()
                except Exception:
                    pass


def fetch_all(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    except pymysql.MySQLError as exc:
        logger.error("Warehouse query failed: %s", type(exc).__name__)
        raise SourceUnavailable("The rank data could not be loaded.") from exc


def fetch_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    except pymysql.MySQLError as exc:
        logger.error("Warehouse query failed: %s", type(exc).__name__)
        raise SourceUnavailable("The rank data could not be loaded.") from exc


def scalar(sql: str, params: Sequence[Any] = (), default: Any = 0) -> Any:
    row = fetch_one(sql, params)
    if not row:
        return default
    value = next(iter(row.values()), default)
    return default if value is None else value


def ping() -> bool:
    if not is_enabled():
        return False
    try:
        with connection() as conn:
            conn.ping(reconnect=True)
        return True
    except Exception:
        return False


def reset_pool() -> None:
    """Close pooled connections. Used by tests and by long-lived workers."""
    global _pool
    with _lock:
        for conn in _pool:
            try:
                conn.close()
            except Exception:
                pass
        _pool = []
