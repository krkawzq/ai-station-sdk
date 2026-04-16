from __future__ import annotations

import pytest

from aistation.config import Config
from aistation.errors import TransportError
from aistation.transport.runtime import raw_request, request_with_retry


class _StubResponse:
    def __init__(self, status_code: int, *, payload: object | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _StubSession:
    def __init__(self, response: object | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if self._exc is not None:
            raise self._exc
        return self._response


def test_raw_request_maps_transient_http_to_transport_error() -> None:
    session = _StubSession(response=_StubResponse(503, text="<html>busy</html>"))

    with pytest.raises(TransportError) as exc_info:
        raw_request(
            session,  # type: ignore[arg-type]
            "https://example.test",
            Config(),
            "GET",
            "/api/test",
        )

    assert "503" in str(exc_info.value)


def test_request_with_retry_retries_transport_error(monkeypatch) -> None:
    sleep_calls: list[float] = []
    attempts = 0

    def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    def fake_raw_request(method: str, path: str, *, params=None, json=None, timeout=None):
        nonlocal attempts
        del method, path, params, json, timeout
        attempts += 1
        if attempts < 3:
            raise TransportError("temporary")
        return {"flag": True, "resData": {"attempt": attempts}}

    monkeypatch.setattr("aistation.transport.runtime.time.sleep", fake_sleep)

    result = request_with_retry(
        raw_request_fn=fake_raw_request,
        reauth_fn=None,
        prime_token_header_fn=lambda: None,
        config=Config(max_retries=2),
        method="GET",
        path="/api/test",
    )

    assert result == {"attempt": 3}
    assert sleep_calls == [1, 2]
