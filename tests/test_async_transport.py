from __future__ import annotations

import os

import httpx
import pytest

from aistation.aio.transport.auth_flow import login
from aistation.aio.transport.runtime import raw_request, request_with_retry
from aistation.aio.transport.session import build_async_session
from aistation.config import AuthData, Config
from aistation.errors import AiStationError, AuthError, InvalidCredentials, TokenExpired, TransportError


class _StubAsyncSession:
    def __init__(self, response: object | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    async def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if self._exc is not None:
            raise self._exc
        return self._response


@pytest.mark.asyncio
async def test_build_async_session_clears_proxy_env(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy")

    session = build_async_session()
    try:
        assert session.trust_env is False
        assert "HTTPS_PROXY" not in os.environ
        assert "HTTP_PROXY" not in os.environ
    finally:
        await session.aclose()


@pytest.mark.asyncio
async def test_async_raw_request_returns_body_and_forwards_request_args() -> None:
    session = _StubAsyncSession(response=httpx.Response(200, json={"flag": True, "resData": {"ok": True}}))

    body = await raw_request(
        session,  # type: ignore[arg-type]
        "https://example.test",
        Config(default_timeout=9.0),
        "POST",
        "/api/test",
        params={"page": 1},
        json={"name": "demo"},
    )

    assert body == {"flag": True, "resData": {"ok": True}}
    assert session.calls == [
        (
            "POST",
            "https://example.test/api/test",
            {
                "timeout": 9.0,
                "params": {"page": 1},
                "json": {"name": "demo"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_async_raw_request_maps_transport_and_payload_errors() -> None:
    request = httpx.Request("GET", "https://example.test/api/test")

    with pytest.raises(TransportError):
        await raw_request(
            _StubAsyncSession(exc=httpx.ConnectError("boom", request=request)),  # type: ignore[arg-type]
            "https://example.test",
            Config(),
            "GET",
            "/api/test",
        )

    with pytest.raises(AiStationError):
        await raw_request(
            _StubAsyncSession(response=httpx.Response(200, content=b"not-json")),  # type: ignore[arg-type]
            "https://example.test",
            Config(),
            "GET",
            "/api/test",
        )

    with pytest.raises(AiStationError):
        await raw_request(
            _StubAsyncSession(response=httpx.Response(200, json=[1, 2, 3])),  # type: ignore[arg-type]
            "https://example.test",
            Config(),
            "GET",
            "/api/test",
        )


@pytest.mark.asyncio
async def test_async_request_with_retry_reauths_after_token_expired() -> None:
    calls: list[str] = []
    reauth_calls: list[str] = []
    prime_calls: list[str] = []
    responses = [
        {
            "flag": False,
            "errCode": "IBASE_IAUTH_TOKEN_NOT_FOUND",
            "errMessage": "expired",
        },
        {
            "flag": True,
            "resData": {"ok": True},
        },
    ]

    async def fake_raw_request(method: str, path: str, *, params=None, json=None, timeout=None):
        del params, json, timeout
        calls.append(f"{method}:{path}")
        return responses.pop(0)

    async def fake_reauth() -> None:
        reauth_calls.append("reauth")

    def fake_prime() -> None:
        prime_calls.append("prime")

    result = await request_with_retry(
        raw_request_fn=fake_raw_request,
        reauth_fn=fake_reauth,
        prime_token_header_fn=fake_prime,
        config=Config(),
        method="GET",
        path="/api/test",
    )

    assert result == {"ok": True}
    assert calls == ["GET:/api/test", "GET:/api/test"]
    assert reauth_calls == ["reauth"]
    assert prime_calls == ["prime"]


@pytest.mark.asyncio
async def test_async_request_with_retry_retries_transport_errors(monkeypatch) -> None:
    sleep_calls: list[float] = []
    attempts = 0

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    async def fake_raw_request(method: str, path: str, *, params=None, json=None, timeout=None):
        nonlocal attempts
        del method, path, params, json, timeout
        attempts += 1
        if attempts < 3:
            raise TransportError("temporary")
        return {"flag": True, "resData": {"attempt": attempts}}

    monkeypatch.setattr("aistation.aio.transport.runtime.asyncio.sleep", fake_sleep)

    result = await request_with_retry(
        raw_request_fn=fake_raw_request,
        reauth_fn=None,
        prime_token_header_fn=lambda: None,
        config=Config(max_retries=2),
        method="GET",
        path="/api/test",
    )

    assert result == {"attempt": 3}
    assert sleep_calls == [1, 2]


@pytest.mark.asyncio
async def test_async_request_with_retry_raises_token_expired_without_reauth() -> None:
    async def fake_raw_request(method: str, path: str, *, params=None, json=None, timeout=None):
        del method, path, params, json, timeout
        return {
            "flag": False,
            "errCode": "IBASE_IAUTH_TOKEN_NOT_FOUND",
            "errMessage": "expired",
        }

    with pytest.raises(TokenExpired):
        await request_with_retry(
            raw_request_fn=fake_raw_request,
            reauth_fn=None,
            prime_token_header_fn=lambda: None,
            config=Config(),
            method="GET",
            path="/api/test",
        )


@pytest.mark.asyncio
async def test_async_raw_request_maps_transient_http_to_transport_error() -> None:
    session = _StubAsyncSession(response=httpx.Response(503, content=b"<html>busy</html>"))

    with pytest.raises(TransportError) as exc_info:
        await raw_request(
            session,  # type: ignore[arg-type]
            "https://example.test",
            Config(),
            "GET",
            "/api/test",
        )

    assert "503" in str(exc_info.value)


@pytest.mark.asyncio
async def test_async_auth_flow_login_updates_auth_and_persists(monkeypatch, tmp_path) -> None:
    saved: list[tuple[AuthData, object]] = []
    captured_payloads: list[dict[str, object]] = []

    async def fake_raw_get(path: str, params=None, timeout=None):
        del params, timeout
        assert path == "/api/ibase/v1/system/secret"
        return {"flag": True, "resData": "04" + "11" * 64}

    async def fake_raw_post(path: str, payload=None, timeout=None):
        del timeout
        assert path == "/api/ibase/v1/login"
        captured_payloads.append(payload)
        return {
            "flag": True,
            "resData": {
                "token": "new-token",
                "userId": "u1",
                "account": "alice",
                "userName": "Alice",
                "groupId": "g1",
                "userType": 0,
                "roleType": 2,
                "isFirstLogin": False,
            },
        }

    def fake_encrypt(password: str, public_key: str) -> str:
        assert password == "secret"
        assert public_key.startswith("04")
        return "cipher"

    def fake_save_auth(auth: AuthData, path) -> None:
        saved.append((auth, path))

    monkeypatch.setattr("aistation.aio.transport.auth_flow.auth_mod.sm2_encrypt_password", fake_encrypt)
    monkeypatch.setattr("aistation.aio.transport.auth_flow.save_auth", fake_save_auth)

    auth = AuthData()
    async with httpx.AsyncClient(trust_env=False) as session:
        user = await login(
            base_url="https://example.test",
            session=session,
            auth=auth,
            auth_path=tmp_path / "auth.json",
            raw_get=fake_raw_get,
            raw_post=fake_raw_post,
            account="alice",
            password="secret",
            captcha="1234",
        )

    assert user.token == "new-token"
    assert auth.base_url == "https://example.test"
    assert auth.account == "alice"
    assert auth.password == "secret"
    assert auth.token == "new-token"
    assert auth.token_saved_at
    assert captured_payloads[0]["password"] == "cipher"
    assert captured_payloads[0]["captcha"] == "1234"
    assert saved[0][0] is auth


@pytest.mark.asyncio
async def test_async_auth_flow_login_validates_credentials_and_secret_payload() -> None:
    async with httpx.AsyncClient(trust_env=False) as session:
        with pytest.raises(InvalidCredentials):
            await login(
                base_url="https://example.test",
                session=session,
                auth=AuthData(),
                auth_path=None,
                raw_get=lambda *args, **kwargs: None,  # type: ignore[arg-type]
                raw_post=lambda *args, **kwargs: None,  # type: ignore[arg-type]
            )

        async def fake_raw_get(path: str, params=None, timeout=None):
            del path, params, timeout
            return {"flag": True, "resData": {"not": "a-string"}}

        async def fake_raw_post(path: str, payload=None, timeout=None):
            del path, payload, timeout
            raise AssertionError("raw_post should not be called")

        with pytest.raises(AuthError):
            await login(
                base_url="https://example.test",
                session=session,
                auth=AuthData(account="alice", password="secret"),
                auth_path=None,
                raw_get=fake_raw_get,
                raw_post=fake_raw_post,
            )
