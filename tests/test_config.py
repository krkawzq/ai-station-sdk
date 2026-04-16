from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from aistation.config import AuthData, Config, load_auth, load_config, save_auth


def test_save_and_load_auth_round_trip(tmp_path: Path) -> None:
    auth_path = tmp_path / "cfg" / "auth.json"
    auth = AuthData(
        base_url="https://example.test",
        account="alice",
        password="secret",
        token="tok",
        token_saved_at="2026-04-16T12:00:00",
    )

    save_auth(auth, auth_path)
    loaded = load_auth(auth_path)

    assert loaded == auth
    assert stat.S_IMODE(os.stat(auth_path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(auth_path.parent).st_mode) == 0o700


def test_load_auth_uses_environment_overrides(tmp_path: Path, monkeypatch) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps({"base_url": "https://old", "account": "old", "password": "old"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AISTATION_ACCOUNT", "new-account")
    monkeypatch.setenv("AISTATION_PASSWORD", "new-password")
    monkeypatch.setenv("AI_STATION_URL", "https://new-url")

    loaded = load_auth(auth_path)

    assert loaded.account == "new-account"
    assert loaded.password == "new-password"
    assert loaded.base_url == "https://new-url"


def test_load_config_defaults_and_file(tmp_path: Path) -> None:
    missing = load_config(tmp_path / "missing.json")
    assert missing == Config()

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"default_timeout": 3.0, "image_registry_prefix": "registry.local"}),
        encoding="utf-8",
    )
    loaded = load_config(config_path)
    assert loaded.default_timeout == 3.0
    assert loaded.image_registry_prefix == "registry.local"
