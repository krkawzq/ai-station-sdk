"""Tiny in-memory TTL cache for hot reads.

Resource groups and images change rarely; images very rarely. Caching them
avoids hammering the server when a skill polls every few seconds.

Usage pattern inside an API class::

    self._cache: TTLCache[list[Node]] = TTLCache(ttl=60)
    ...
    def list(self, *, refresh: bool = False) -> list[Node]:
        if refresh or self._cache.expired():
            self._cache.set(self._fetch())
        return self._cache.get() or []
"""
from __future__ import annotations

import time
from typing import Generic, TypeVar

T = TypeVar("T")
_DEFAULT_SLOT = object()
_ALL_SLOTS = object()


class TTLCache(Generic[T]):
    """Small in-memory TTL cache with optional key-based entries."""

    __slots__ = ("_entries", "ttl")

    def __init__(self, ttl: float = 60.0) -> None:
        self.ttl: float = ttl
        self._entries: dict[object, tuple[T, float]] = {}

    def get(self, key: object = _DEFAULT_SLOT) -> T | None:
        if self.expired(key):
            return None
        entry = self._entries.get(key)
        return entry[0] if entry is not None else None

    def set(self, value: T, key: object = _DEFAULT_SLOT) -> None:
        self._entries[key] = (value, time.monotonic())

    def expired(self, key: object = _DEFAULT_SLOT) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return True
        _, stamp = entry
        if (time.monotonic() - stamp) >= self.ttl:
            self._entries.pop(key, None)
            return True
        return False

    def invalidate(self, key: object = _ALL_SLOTS) -> None:
        if key is _ALL_SLOTS:
            self._entries.clear()
            return
        self._entries.pop(key, None)

    def age(self, key: object = _DEFAULT_SLOT) -> float | None:
        """Seconds since last set, or None if never set."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        return time.monotonic() - entry[1]
