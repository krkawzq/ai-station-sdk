from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from ...config import Config
from ...errors import AiStationError, TokenExpired, TransportError
from ...transport.envelope import check_flag
from ...transport.runtime import is_retryable_http_status, timeout_for


async def raw_request(
    session: httpx.AsyncClient,
    base_url: str,
    config: Config,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": timeout or config.default_timeout}
    if params is not None:
        kwargs["params"] = params
    if json is not None:
        kwargs["json"] = json
    try:
        response = await session.request(method, f"{base_url}{path}", **kwargs)
    except httpx.RequestError as exc:
        raise TransportError(str(exc), path=path) from exc
    if is_retryable_http_status(response.status_code):
        text = response.text
        summary = " ".join(text.strip().split())[:160]
        message = f"transient HTTP {response.status_code} from {path}"
        if summary:
            message = f"{message}: {summary}"
        raise TransportError(message, path=path)
    try:
        body = response.json()
    except ValueError as exc:
        raise AiStationError(f"invalid JSON response from {path}", path=path) from exc
    if not isinstance(body, dict):
        raise AiStationError(f"unexpected response payload from {path}", path=path)
    return body


async def request_with_retry(
    *,
    raw_request_fn: Callable[..., Awaitable[dict[str, Any]]],
    reauth_fn: Callable[[], Awaitable[Any]] | None,
    prime_token_header_fn: Callable[[], None],
    config: Config,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> Any:
    prime_token_header_fn()
    effective_timeout = timeout or timeout_for(config, path)
    max_retries = max(0, int(getattr(config, "max_retries", 0)))

    last_transport_err: TransportError | None = None
    for attempt in range(max_retries + 1):
        try:
            body = await raw_request_fn(
                method,
                path,
                params=params,
                json=json,
                timeout=effective_timeout,
            )
            return check_flag(body, path)
        except TokenExpired:
            if reauth_fn is None:
                raise
            await reauth_fn()
            body = await raw_request_fn(
                method,
                path,
                params=params,
                json=json,
                timeout=effective_timeout,
            )
            return check_flag(body, path)
        except TransportError as exc:
            last_transport_err = exc
            if attempt < max_retries:
                await asyncio.sleep(min(2 ** attempt, 8))
                continue
            raise
    assert last_transport_err is not None
    raise last_transport_err
