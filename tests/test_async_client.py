from __future__ import annotations

import asyncio

import pytest

from aistation.aio.client import AsyncAiStationClient
from aistation.config import AuthData, Config
from aistation.enums import AuthMode, ReauthPolicy
from aistation.errors import AiStationError, AuthError

from .helpers import make_user


@pytest.mark.asyncio
async def test_async_client_defaults_to_local_auth_and_config(monkeypatch) -> None:
    auth = AuthData(
        base_url="https://example.test",
        account="alice",
        token="cached-token",
    )
    config = Config(default_timeout=9.0, verify_ssl=True)

    monkeypatch.setattr("aistation.aio.client.load_auth", lambda path=None: auth)
    monkeypatch.setattr("aistation.aio.client.load_config", lambda path=None: config)

    client = AsyncAiStationClient()
    try:
        assert client.base_url == "https://example.test"
        assert client.config.default_timeout == 9.0
        assert client.session.headers["X-Auth-Token"] == "cached-token"
        assert client.user is not None
        assert client.user.account == "alice"
        assert client.auth_mode is AuthMode.AUTO
        assert client.reauth_policy is ReauthPolicy.IF_POSSIBLE
        assert client.is_authenticated is True
        status = client.auth_status()
        assert status.has_token is True
        assert status.request_ready is True
        assert status.user_loaded is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_client_auto_logs_in_on_prepare(monkeypatch) -> None:
    auth = AuthData(
        base_url="https://example.test",
        account="alice",
        password="secret",
    )
    calls: list[str] = []

    async def fake_login(**kwargs):
        calls.append("login")
        kwargs["auth"].token = "fresh-token"
        kwargs["session"].headers["X-Auth-Token"] = "fresh-token"
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.aio.client.async_auth_flow.login", fake_login)

    client = AsyncAiStationClient(auth=auth, config=Config(), auth_mode=AuthMode.LOGIN_IF_POSSIBLE)
    try:
        assert calls == []
        user = await client.prepare_auth()

        assert calls == ["login"]
        assert user is not None
        assert client.user is not None
        assert client.user.token == "fresh-token"
        assert client.auth.token == "fresh-token"
        assert client.session.headers["X-Auth-Token"] == "fresh-token"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_require_user_respects_reauth_policy(monkeypatch) -> None:
    client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.TOKEN_ONLY,
    )

    async def fake_refresh_user():
        raise AuthError("expired")

    monkeypatch.setattr(client, "refresh_user", fake_refresh_user)

    try:
        with pytest.raises(AuthError) as exc_info:
            await client.require_user()

        assert exc_info.value.err_code == "SDK_REAUTH_DISABLED"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_request_retry_wires_reauth_policy() -> None:
    calls: list[dict[str, object]] = []

    async def fake_request_with_retry(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    auto_client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
        ),
        config=Config(),
    )
    token_only_client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.TOKEN_ONLY,
    )

    try:
        from aistation.aio import client as async_client_mod

        original = async_client_mod.async_runtime.request_with_retry
        async_client_mod.async_runtime.request_with_retry = fake_request_with_retry
        try:
            await auto_client.get("/api/test")
            await token_only_client.get("/api/test")
        finally:
            async_client_mod.async_runtime.request_with_retry = original

        assert calls[0]["reauth_fn"] is not None
        assert calls[1]["reauth_fn"] is None
    finally:
        await auto_client.close()
        await token_only_client.close()


@pytest.mark.asyncio
async def test_async_login_reuses_fresh_cached_auth_without_network(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_login(**kwargs):
        calls.append("login")
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.aio.client.async_auth_flow.login", fake_login)

    client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )
    try:
        user = await client.login()

        assert calls == []
        assert user.token == "cached-token"
        assert client.session.headers["X-Auth-Token"] == "cached-token"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_client_context_manager_refreshes_stale_token_and_closes(monkeypatch) -> None:
    auth = AuthData(
        base_url="https://example.test",
        account="alice",
        password="secret",
        token="stale-token",
        token_saved_at="2026-01-01T00:00:00",
    )
    config = Config(token_ttl_hours=1)
    calls: list[str] = []
    closed: list[str] = []

    monkeypatch.setattr("aistation.aio.client.load_auth", lambda path=None: auth)
    monkeypatch.setattr("aistation.aio.client.load_config", lambda path=None: config)

    async def fake_login(**kwargs):
        calls.append("login")
        kwargs["auth"].token = "fresh-token"
        kwargs["auth"].token_saved_at = "2026-01-02T00:00:00"
        kwargs["session"].headers["X-Auth-Token"] = "fresh-token"
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.aio.client.async_auth_flow.login", fake_login)

    client = AsyncAiStationClient()

    async def fake_aclose() -> None:
        closed.append("closed")

    monkeypatch.setattr(client.session, "aclose", fake_aclose)

    async with client as current:
        assert current is client
        assert calls == ["login"]
        assert current.auth.token == "fresh-token"
        assert current.session.headers["X-Auth-Token"] == "fresh-token"

    assert closed == ["closed"]


@pytest.mark.asyncio
async def test_async_ensure_auth_deduplicates_concurrent_login(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_login(**kwargs):
        calls.append("login")
        await asyncio.sleep(0)
        kwargs["auth"].token = "fresh-token"
        kwargs["session"].headers["X-Auth-Token"] = "fresh-token"
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.aio.client.async_auth_flow.login", fake_login)

    client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )
    try:
        first, second = await asyncio.gather(client.ensure_auth(), client.ensure_auth())

        assert calls == ["login"]
        assert first.token == "fresh-token"
        assert second.token == "fresh-token"
        assert client.auth.token == "fresh-token"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_reauth_login_forces_network_login(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_login(**kwargs):
        calls.append("login")
        kwargs["auth"].token = "fresh-token"
        kwargs["session"].headers["X-Auth-Token"] = "fresh-token"
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.aio.client.async_auth_flow.login", fake_login)

    client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
            token="cached-token",
        ),
        config=Config(),
    )
    try:
        user = await client._reauth_login()

        assert calls == ["login"]
        assert user.token == "fresh-token"
        assert client.auth.token == "fresh-token"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_require_user_can_refresh_profile_from_cached_token(monkeypatch) -> None:
    client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )

    async def fake_get(path, params=None, timeout=None):
        del path, params, timeout
        return {
            "userId": "u1",
            "account": "alice",
            "userName": "Alice",
            "groupId": "g1",
            "roleType": 2,
            "userType": 0,
            "isFirstLogin": False,
        }

    monkeypatch.setattr(client, "get", fake_get)

    try:
        user = await client.require_user()

        assert user.token == "cached-token"
        assert user.group_id == "g1"
        assert client.user is user
        assert client.session.headers["X-Auth-Token"] == "cached-token"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_client_list_all_uses_fast_path_then_falls_back(monkeypatch) -> None:
    client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            token="tok",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )
    captured: dict[str, object] = {}

    async def fake_get(path: str, params=None, timeout=None):
        captured["path"] = path
        captured["params"] = params
        captured["timeout"] = timeout
        return {"total": 3, "data": [{"id": "only-one"}]}

    async def fake_paginate(path: str, *, params=None, page_size=50, page_param="page", max_pages=None):
        captured["fallback"] = (path, params, page_size, page_param, max_pages)
        yield {"id": "one"}
        yield {"id": "two"}
        yield {"id": "three"}

    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(client, "paginate", fake_paginate)

    try:
        rows = await client.list_all("/api/iresource/v1/train", params={"statusFlag": 0})

        assert rows == [{"id": "one"}, {"id": "two"}, {"id": "three"}]
        assert captured["params"] == {"statusFlag": 0, "page": -1, "pageSize": -1}
        assert captured["fallback"] == (
            "/api/iresource/v1/train",
            {"statusFlag": 0},
            50,
            "page",
            None,
        )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_paginate_raises_when_max_pages_exceeded(monkeypatch) -> None:
    client = AsyncAiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )

    async def fake_get(path: str, params=None, timeout=None):
        del path, timeout
        return {
            "data": [{"page": params["page"]}],
            "totalPages": 3,
        }

    monkeypatch.setattr(client, "get", fake_get)

    try:
        with pytest.raises(AiStationError) as exc_info:
            [row async for row in client.paginate("/api/iresource/v1/train", page_size=1, max_pages=2)]

        assert exc_info.value.err_code == "SDK_MAX_PAGES_EXCEEDED"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_async_invalidate_caches_clears_task_cache(monkeypatch) -> None:
    client = AsyncAiStationClient(
        auth=AuthData(base_url="https://example.test"),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )
    calls: list[str] = []

    monkeypatch.setattr(client.nodes, "invalidate_cache", lambda: calls.append("nodes"))
    monkeypatch.setattr(client.images, "invalidate_cache", lambda: calls.append("images"))
    monkeypatch.setattr(client.tasks, "invalidate_cache", lambda: calls.append("tasks"))
    monkeypatch.setattr(client.workplatforms, "invalidate_cache", lambda: calls.append("workplatforms"))

    try:
        client.invalidate_caches()
        assert calls == ["nodes", "images", "tasks", "workplatforms"]
    finally:
        await client.close()
