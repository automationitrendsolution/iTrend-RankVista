"""Cache helpers that never let a cache outage break correctness.
Every call falls back to computing the value when Redis is unreachable."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from django.core.cache import cache

logger = logging.getLogger("rankvista.cache")

T = TypeVar("T")

_MISS = object()


def cache_get(key: str, default: Any = None) -> Any:
    try:
        return cache.get(key, default)
    except Exception as exc:
        logger.debug("Cache read unavailable (%s)", type(exc).__name__)
        return default


def cache_set(key: str, value: Any, timeout: int) -> None:
    try:
        cache.set(key, value, timeout)
    except Exception as exc:
        logger.debug("Cache write unavailable (%s)", type(exc).__name__)


def cache_delete(key: str) -> None:
    try:
        cache.delete(key)
    except Exception as exc:
        logger.debug("Cache delete unavailable (%s)", type(exc).__name__)


def cached_call(key: str, timeout: int, producer: Callable[[], T]) -> T:
    """Return a cached value, computing and storing it on a miss.
    A backend error degrades performance but never correctness."""
    value = cache_get(key, _MISS)
    if value is not _MISS:
        return value  # type: ignore[return-value]
    computed = producer()
    cache_set(key, computed, timeout)
    return computed


def is_available() -> bool:
    """Report whether the configured cache backend answers a round-trip."""
    try:
        cache.set("rv:healthcheck", "1", 5)
        return cache.get("rv:healthcheck") == "1"
    except Exception:
        return False
