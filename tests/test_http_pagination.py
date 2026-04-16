from __future__ import annotations

import json
import os
from pathlib import Path

import responses

from aistation._http import paginate
from aistation.client import AiStationClient
from aistation.config import AuthData, Config
from aistation.transport import build_session


def test_build_session_clears_proxy_env(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy")

    session = build_session()

    assert session.trust_env is False
    assert session.verify is False
    assert "HTTPS_PROXY" not in os.environ
    assert "HTTP_PROXY" not in os.environ


@responses.activate
def test_paginate_yields_all_pages() -> None:
    calls: list[int] = []

    def callback(request):
        del request
        page = len(calls) + 1
        calls.append(page)
        body = {
            "flag": True,
            "resData": {
                "total": 3,
                "pageSize": 1,
                "currentPage": page,
                "totalPages": 3,
                "data": [{"page": page}],
            },
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(body))

    responses.add_callback(
        responses.GET,
        "https://example.test/api/iresource/v1/node",
        callback=callback,
    )

    items = list(
        paginate(build_session(), "https://example.test", "/api/iresource/v1/node", page_size=1, timeout=1)
    )

    assert items == [{"page": 1}, {"page": 2}, {"page": 3}]
    assert calls == [1, 2, 3]
    assert [call.request.url for call in responses.calls] == [
        "https://example.test/api/iresource/v1/node?pageSize=1&pageNum=1",
        "https://example.test/api/iresource/v1/node?pageSize=1&pageNum=2",
        "https://example.test/api/iresource/v1/node?pageSize=1&pageNum=3",
    ]


@responses.activate
def test_paginate_uses_train_policy_page_param() -> None:
    calls: list[int] = []

    def callback(request):
        del request
        page = len(calls) + 1
        calls.append(page)
        body = {
            "flag": True,
            "resData": {
                "total": 2,
                "pageSize": 1,
                "currentPage": page,
                "totalPages": 2,
                "data": [{"page": page}],
            },
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(body))

    responses.add_callback(
        responses.GET,
        "https://example.test/api/iresource/v1/train",
        callback=callback,
    )

    items = list(
        paginate(build_session(), "https://example.test", "/api/iresource/v1/train", page_size=1, timeout=1)
    )

    assert items == [{"page": 1}, {"page": 2}]
    assert [call.request.url for call in responses.calls] == [
        "https://example.test/api/iresource/v1/train?pageSize=1&page=1",
        "https://example.test/api/iresource/v1/train?pageSize=1&page=2",
    ]


@responses.activate
def test_client_retries_once_after_token_expired(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("aistation.auth.sm2_encrypt_password", lambda password, public_key: "cipher")

    responses.add(
        responses.GET,
        "https://example.test/api/ibase/v1/system/secret",
        json={"flag": True, "resData": "04" + "11" * 64},
        status=200,
    )
    responses.add(
        responses.POST,
        "https://example.test/api/ibase/v1/login",
        json={
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
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://example.test/api/iresource/v1/config/shm",
        json={
            "flag": False,
            "errCode": "IBASE_IAUTH_TOKEN_NOT_FOUND",
            "errMessage": "expired",
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://example.test/api/iresource/v1/config/shm",
        json={"flag": True, "resData": 1},
        status=200,
    )

    client = AiStationClient(
        "https://example.test",
        config=Config(),
        auth=AuthData(account="alice", password="secret", token="stale"),
        auth_path=tmp_path / "auth.json",
    )
    client.ensure_auth()

    result = client.get("/api/iresource/v1/config/shm")

    assert result == 1
    assert client.session.headers["X-Auth-Token"] == "new-token"
    assert len(responses.calls) == 4


def test_client_list_all_uses_fast_path_then_falls_back(monkeypatch, tmp_path: Path) -> None:
    client = AiStationClient(
        "https://example.test",
        config=Config(),
        auth=AuthData(account="alice", password="secret", token="tok"),
        auth_path=tmp_path / "auth.json",
    )
    client.ensure_auth()

    captured: dict[str, object] = {}

    def fake_get(path: str, params=None, timeout=None):
        captured["path"] = path
        captured["params"] = params
        captured["timeout"] = timeout
        return {"total": 3, "data": [{"id": "only-one"}]}

    def fake_paginate(path: str, *, params=None, page_size=50, page_param="page"):
        captured["fallback"] = (path, params, page_size, page_param)
        yield {"id": "one"}
        yield {"id": "two"}
        yield {"id": "three"}

    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(client, "paginate", fake_paginate)

    rows = client.list_all("/api/iresource/v1/train", params={"statusFlag": 0})

    assert rows == [{"id": "one"}, {"id": "two"}, {"id": "three"}]
    assert captured["params"] == {"statusFlag": 0, "page": -1, "pageSize": -1}
    assert captured["fallback"] == ("/api/iresource/v1/train", {"statusFlag": 0}, 50, "page")
