from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TypeVar

from .errors import AmbiguousMatchError, NotFoundError

T = TypeVar("T")


def resolve_many(
    query: str,
    items: Iterable[T],
    *,
    key_fns: Sequence[Callable[[T], str]],
) -> list[T]:
    needle = query.strip().lower()
    if not needle:
        return []

    haystack = list(items)
    exact = _match(needle, haystack, key_fns, mode="exact")
    if exact:
        return exact
    suffix = _match(needle, haystack, key_fns, mode="suffix")
    if suffix:
        return suffix
    return _match(needle, haystack, key_fns, mode="contains")


def resolve_one(
    query: str,
    items: Iterable[T],
    *,
    key_fns: Sequence[Callable[[T], str]],
    label_fn: Callable[[T], str],
    resource_type: str,
) -> T:
    matches = resolve_many(query, items, key_fns=key_fns)
    if not matches:
        raise NotFoundError(resource_type, query)
    if len(matches) > 1:
        raise AmbiguousMatchError(
            resource_type,
            query,
            matches=[label_fn(item) for item in matches[:8]],
        )
    return matches[0]


def _match(
    needle: str,
    items: list[T],
    key_fns: Sequence[Callable[[T], str]],
    *,
    mode: str,
) -> list[T]:
    matches: list[T] = []
    seen: set[int] = set()
    for item in items:
        keys = [_normalize(key_fn(item)) for key_fn in key_fns]
        if not any(_matches(needle, key, mode=mode) for key in keys):
            continue
        marker = id(item)
        if marker in seen:
            continue
        seen.add(marker)
        matches.append(item)
    return matches


def _normalize(value: str) -> str:
    return value.strip().lower()


def _matches(needle: str, haystack: str, *, mode: str) -> bool:
    if not haystack:
        return False
    if mode == "exact":
        return haystack == needle
    if mode == "suffix":
        return haystack.endswith(needle)
    return needle in haystack
