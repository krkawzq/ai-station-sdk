from __future__ import annotations

import pytest

from aistation.client import AiStationClient
from aistation.config import AuthData, Config
from aistation.enums import AuthMode, ReauthPolicy
from aistation.errors import AiStationError, AuthError

from .helpers import make_user


def test_client_defaults_to_local_auth_and_config(monkeypatch) -> None:
    auth = AuthData(
        base_url="https://example.test",
        account="alice",
        token="cached-token",
    )
    config = Config(default_timeout=9.0, verify_ssl=True)

    monkeypatch.setattr("aistation.client.load_auth", lambda path=None: auth)
    monkeypatch.setattr("aistation.client.load_config", lambda path=None: config)

    client = AiStationClient()

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


def test_client_auto_logs_in_when_credentials_exist(monkeypatch) -> None:
    auth = AuthData(
        base_url="https://example.test",
        account="alice",
        password="secret",
    )
    config = Config()
    calls: list[str] = []

    monkeypatch.setattr("aistation.client.load_auth", lambda path=None: auth)
    monkeypatch.setattr("aistation.client.load_config", lambda path=None: config)

    def fake_login(**kwargs):
        calls.append("login")
        kwargs["auth"].token = "fresh-token"
        kwargs["session"].headers["X-Auth-Token"] = "fresh-token"
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.client.auth_flow.login", fake_login)

    client = AiStationClient()

    assert calls == ["login"]
    assert client.user is not None
    assert client.user.token == "fresh-token"
    assert client.auth.token == "fresh-token"
    assert client.session.headers["X-Auth-Token"] == "fresh-token"


def test_login_if_possible_mode_logs_in_for_injected_auth(monkeypatch) -> None:
    calls: list[str] = []

    def fake_login(**kwargs):
        calls.append("login")
        kwargs["auth"].token = "fresh-token"
        kwargs["session"].headers["X-Auth-Token"] = "fresh-token"
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.client.auth_flow.login", fake_login)

    client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
        ),
        config=Config(),
        auth_mode=AuthMode.LOGIN_IF_POSSIBLE,
    )

    assert calls == ["login"]
    assert client.auth_mode is AuthMode.LOGIN_IF_POSSIBLE
    assert client.auth.token == "fresh-token"


def test_auto_mode_refreshes_stale_token_from_disk(monkeypatch) -> None:
    auth = AuthData(
        base_url="https://example.test",
        account="alice",
        password="secret",
        token="stale-token",
        token_saved_at="2026-01-01T00:00:00",
    )
    calls: list[str] = []

    monkeypatch.setattr("aistation.client.load_auth", lambda path=None: auth)
    monkeypatch.setattr("aistation.client.load_config", lambda path=None: Config(token_ttl_hours=1))

    def fake_login(**kwargs):
        calls.append("login")
        kwargs["auth"].token = "fresh-token"
        kwargs["auth"].token_saved_at = "2026-01-02T00:00:00"
        kwargs["session"].headers["X-Auth-Token"] = "fresh-token"
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.client.auth_flow.login", fake_login)

    client = AiStationClient()

    assert calls == ["login"]
    assert client.auth.token == "fresh-token"
    assert client.session.headers["X-Auth-Token"] == "fresh-token"


def test_token_only_mode_keeps_stale_token_without_eager_login(monkeypatch) -> None:
    calls: list[str] = []

    def fake_login(**kwargs):
        calls.append("login")
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.client.auth_flow.login", fake_login)

    client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
            token="stale-token",
            token_saved_at="2026-01-01T00:00:00",
        ),
        config=Config(token_ttl_hours=1),
        auth_mode=AuthMode.TOKEN_ONLY,
    )

    assert calls == []
    assert client.user is not None
    assert client.user.token == "stale-token"
    assert client.session.headers["X-Auth-Token"] == "stale-token"
    assert client.reauth_policy is ReauthPolicy.NEVER
    assert client.auth_status().needs_login is True


def test_auth_status_can_be_request_ready_without_cached_token() -> None:
    client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
        ),
        config=Config(),
    )

    status = client.auth_status()

    assert status.has_token is False
    assert status.can_login is True
    assert status.request_ready is True
    assert status.needs_login is False


def test_require_user_can_refresh_profile_from_cached_token(monkeypatch) -> None:
    client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )
    calls: list[str] = []

    def fake_refresh_user():
        calls.append("refresh")
        client.user = make_user(account="alice", token="cached-token")
        return client.user

    monkeypatch.setattr(client, "refresh_user", fake_refresh_user)

    user = client.require_user()

    assert calls == ["refresh"]
    assert user.group_id == "project-1"
    assert client.session.headers["X-Auth-Token"] == "cached-token"


def test_require_user_respects_reauth_policy(monkeypatch) -> None:
    client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.TOKEN_ONLY,
    )

    monkeypatch.setattr(client, "refresh_user", lambda: (_ for _ in ()).throw(AuthError("expired")))

    with pytest.raises(AuthError) as exc_info:
        client.require_user()

    assert exc_info.value.err_code == "SDK_REAUTH_DISABLED"


def test_refresh_user_merges_cached_token_into_profile(monkeypatch) -> None:
    client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )

    monkeypatch.setattr(
        client,
        "get",
        lambda path, params=None, timeout=None: {
            "userId": "u1",
            "account": "alice",
            "userName": "Alice",
            "groupId": "g1",
            "roleType": 2,
            "userType": 0,
            "isFirstLogin": False,
        },
    )

    user = client.refresh_user()

    assert user.token == "cached-token"
    assert user.group_id == "g1"
    assert client.user is user


def test_client_context_manager_closes_session(monkeypatch) -> None:
    client = AiStationClient(
        auth=AuthData(base_url="https://example.test"),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )
    calls: list[str] = []

    monkeypatch.setattr(client.session, "close", lambda: calls.append("closed"))

    with client as current:
        assert current is client

    assert calls == ["closed"]


def test_request_retry_wires_reauth_policy(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_request_with_retry(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr("aistation.client.runtime.request_with_retry", fake_request_with_retry)

    auto_client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
        ),
        config=Config(),
    )
    token_only_client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            password="secret",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.TOKEN_ONLY,
    )

    auto_client.get("/api/test")
    token_only_client.get("/api/test")

    assert calls[0]["reauth_fn"] is not None
    assert calls[1]["reauth_fn"] is None


def test_login_reuses_fresh_cached_auth_without_network(monkeypatch) -> None:
    calls: list[str] = []

    def fake_login(**kwargs):
        calls.append("login")
        return make_user(token="fresh-token")

    monkeypatch.setattr("aistation.client.auth_flow.login", fake_login)

    client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )

    user = client.login()

    assert calls == []
    assert user.token == "cached-token"
    assert client.session.headers["X-Auth-Token"] == "cached-token"


def test_paginate_raises_when_max_pages_exceeded(monkeypatch) -> None:
    client = AiStationClient(
        auth=AuthData(
            base_url="https://example.test",
            account="alice",
            token="cached-token",
        ),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )

    def fake_get(path: str, params=None, timeout=None):
        del path, timeout
        return {
            "data": [{"page": params["page"]}],
            "totalPages": 3,
        }

    monkeypatch.setattr(client, "get", fake_get)

    with pytest.raises(AiStationError) as exc_info:
        list(client.paginate("/api/iresource/v1/train", page_size=1, max_pages=2))

    assert exc_info.value.err_code == "SDK_MAX_PAGES_EXCEEDED"


def test_invalidate_caches_clears_task_cache(monkeypatch) -> None:
    client = AiStationClient(
        auth=AuthData(base_url="https://example.test"),
        config=Config(),
        auth_mode=AuthMode.MANUAL,
    )
    calls: list[str] = []

    monkeypatch.setattr(client.nodes, "invalidate_cache", lambda: calls.append("nodes"))
    monkeypatch.setattr(client.images, "invalidate_cache", lambda: calls.append("images"))
    monkeypatch.setattr(client.tasks, "invalidate_cache", lambda: calls.append("tasks"))
    monkeypatch.setattr(client.workplatforms, "invalidate_cache", lambda: calls.append("workplatforms"))

    client.invalidate_caches()

    assert calls == ["nodes", "images", "tasks", "workplatforms"]
