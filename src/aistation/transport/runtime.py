from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import requests  # type: ignore[import-untyped]

from ..config import Config
from ..errors import AiStationError, TokenExpired, TransportError
from .envelope import check_flag

RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def raw_request(
    session: requests.Session,
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
        response = session.request(method, f"{base_url}{path}", **kwargs)
    except requests.RequestException as exc:
        raise TransportError(str(exc), path=path) from exc
    if is_retryable_http_status(response.status_code):
        raise TransportError(
            _transient_http_message(path, response.status_code, response.text),
            path=path,
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise AiStationError(f"invalid JSON response from {path}", path=path) from exc
    if not isinstance(body, dict):
        raise AiStationError(f"unexpected response payload from {path}", path=path)
    return body


def request_with_retry(
    *,
    raw_request_fn: Callable[..., dict[str, Any]],
    reauth_fn: Callable[[], Any] | None,
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
            body = raw_request_fn(method, path, params=params, json=json, timeout=effective_timeout)
            return check_flag(body, path)
        except TokenExpired:
            if reauth_fn is None:
                raise
            reauth_fn()
            body = raw_request_fn(method, path, params=params, json=json, timeout=effective_timeout)
            return check_flag(body, path)
        except TransportError as exc:
            last_transport_err = exc
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise
    assert last_transport_err is not None
    raise last_transport_err


def is_retryable_http_status(status_code: int) -> bool:
    return status_code in RETRYABLE_HTTP_STATUSES


def _transient_http_message(path: str, status_code: int, text: str) -> str:
    summary = " ".join(text.strip().split())[:160]
    if summary:
        return f"transient HTTP {status_code} from {path}: {summary}"
    return f"transient HTTP {status_code} from {path}"


def timeout_for(config: Config, path: str) -> float:
    default = config.default_timeout
    if path == "/api/iresource/v1/train":
        return max(default, 45.0)
    if path.endswith("/train/check-resources"):
        return max(default, 30.0)
    return default
