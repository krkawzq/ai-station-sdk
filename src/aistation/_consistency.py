from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .errors import NotFoundError

T = TypeVar("T")


def retry_not_found(
    read_fn: Callable[[], T],
    *,
    attempts: int = 3,
    delay: float = 0.5,
) -> T:
    last_error: NotFoundError | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return read_fn()
        except NotFoundError as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(delay * attempt)
    assert last_error is not None
    raise last_error


async def async_retry_not_found(
    read_fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    delay: float = 0.5,
) -> T:
    last_error: NotFoundError | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return await read_fn()
        except NotFoundError as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            await asyncio.sleep(delay * attempt)
    assert last_error is not None
    raise last_error
