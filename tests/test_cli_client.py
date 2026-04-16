from __future__ import annotations

from types import SimpleNamespace

import pytest

from aistation.cli._client import make_client
from aistation.config import AuthData, Config
from aistation.errors import InvalidCredentials, TokenExpired


class _FakeSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


class _FakeClient:
    def __init__(self, *, auth: AuthData, base_url: str) -> None:
        self.auth = auth
        self.base_url = base_url
        self.config = Config()
        self.session = _FakeSession()
        self.ensure_auth_calls = 0

    def ensure_auth(self) -> None:
        self.ensure_auth_calls += 1

    def auth_status(self) -> SimpleNamespace:
        return SimpleNamespace(token_stale=True)


def test_make_client_requires_cached_token_without_live_login(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(
        auth=AuthData(base_url="https://example.test", account="", password="", token=""),
        base_url="https://example.test",
    )
    monkeypatch.setattr("aistation.cli._client.AiStationClient.from_config", lambda **kwargs: fake)

    with pytest.raises(TokenExpired):
        make_client(require_token=True)

    assert fake.ensure_auth_calls == 0


def test_make_client_requires_saved_credentials_for_live_login(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(
        auth=AuthData(base_url="https://example.test", account="", password="", token=""),
        base_url="https://example.test",
    )
    monkeypatch.setattr("aistation.cli._client.AiStationClient.from_config", lambda **kwargs: fake)

    with pytest.raises(InvalidCredentials) as exc_info:
        make_client(require_token=True, allow_live_login=True)

    assert exc_info.value.err_code == "SDK_CLI_NOT_LOGGED_IN"
    assert fake.ensure_auth_calls == 0


def test_make_client_refreshes_stale_token_when_live_login_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(
        auth=AuthData(base_url="https://example.test", account="alice", password="secret", token="tok"),
        base_url="https://example.test",
    )
    monkeypatch.setattr("aistation.cli._client.AiStationClient.from_config", lambda **kwargs: fake)

    client = make_client(require_token=True, allow_live_login=True)

    assert client is fake
    assert fake.session.headers["X-Auth-Token"] == "tok"
    assert fake.ensure_auth_calls == 1
