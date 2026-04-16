from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from aistation.cli.main import app
from aistation.config import AuthData, Config

from .helpers import (
    make_group,
    make_image,
    make_node,
    make_pod,
    make_task,
    make_user,
    make_workplatform,
)


runner = CliRunner()


class _FakeGroupsAPI:
    def list(self) -> list[Any]:
        return [make_group()]

    def resolve_id(self, name_or_id: str) -> str:
        return "group-1"


class _FakeNodesAPI:
    def list(self, *, group_id: str | None = None) -> list[Any]:
        return [make_node(group_id=group_id or "group-1")]


class _FakeImagesAPI:
    def list(self, *, image_type: str | None = None, share: int | None = None) -> list[Any]:
        image = make_image(image_type=image_type or "pytorch", share=share or 2)
        return [image]


class _FakeTasksAPI:
    def list(self, *, status_flag: int = 0) -> list[Any]:
        status = "Running" if status_flag == 0 else "Finished"
        return [make_task(status=status)]

    def get(self, task_id: str) -> Any:
        return make_task(task_id=task_id, status="Running")

    def pods(self, task_id: str) -> list[Any]:
        return [make_pod()]

    def read_log(self, task_id: str, *, pod_name: str | None = None) -> str:
        suffix = f":{pod_name}" if pod_name else ""
        return f"log for {task_id}{suffix}"


class _FakeWorkPlatformsAPI:
    def list(self, *, include_halted: bool = False) -> list[Any]:
        status = "Halt" if include_halted else "Running"
        return [make_workplatform(status=status)]

    def list_history(self, *, page: int = 1, page_size: int = 20) -> list[Any]:
        return [make_workplatform(wp_id=f"wp-history-{page}", status="Stopped")]

    def get(self, wp_id: str) -> Any:
        return make_workplatform(wp_id=wp_id)


class _FakeClient:
    def __init__(self) -> None:
        self._user = make_user()
        self.groups = _FakeGroupsAPI()
        self.nodes = _FakeNodesAPI()
        self.images = _FakeImagesAPI()
        self.tasks = _FakeTasksAPI()
        self.workplatforms = _FakeWorkPlatformsAPI()

    def require_user(self) -> Any:
        return self._user

    def login(
        self,
        account: str | None = None,
        password: str | None = None,
        *,
        captcha: str | None = None,
    ) -> Any:
        return self._user

    def ping(self) -> dict[str, Any]:
        return {
            "reachable": True,
            "token_valid": True,
            "error": None,
        }


@pytest.fixture
def fake_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient()

    monkeypatch.setattr("aistation.cli.query.make_client", lambda **kwargs: client)
    monkeypatch.setattr("aistation.cli.tasks.make_client", lambda **kwargs: client)
    monkeypatch.setattr("aistation.cli.envs.make_client", lambda **kwargs: client)
    monkeypatch.setattr("aistation.cli.status.make_client", lambda **kwargs: client)
    monkeypatch.setattr("aistation.cli.auth.make_client", lambda **kwargs: client)

    monkeypatch.setattr(
        "aistation.cli.auth.load_auth",
        lambda path=None: AuthData(
            base_url="https://aistation.example.invalid",
            account="alice",
            password="",
            token="token-1",
            token_saved_at="2026-01-01T00:00:00Z",
        ),
    )
    monkeypatch.setattr("aistation.cli.auth.save_auth", lambda data, path=None: None)
    monkeypatch.setattr(
        "aistation.cli.auth._resolve_credentials",
        lambda account, password, interactive: ("alice", "secret"),
    )
    monkeypatch.setattr(
        "aistation.cli.main.load_config",
        lambda path=None: Config(default_timeout=9.0, verify_ssl=True),
    )


def _invoke_json(args: list[str]) -> Any:
    result = runner.invoke(app, args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.mark.usefixtures("fake_cli")
@pytest.mark.parametrize(
    ("args", "path", "expected"),
    [
        (["gpus", "--json"], ("0", "group_name"), "GPU-POOL-A"),
        (["nodes", "--json"], ("0", "node_name"), "gpu-node-1"),
        (["images", "--json"], ("0", "name"), "registry.example.invalid/ml/pytorch"),
        (["tasks", "--json"], ("0", "id"), "task-1"),
        (["task", "--json", "task-1"], ("task", "id"), "task-1"),
        (["task-logs", "--json", "task-1"], ("log",), "log for task-1"),
        (["envs", "--json"], ("0", "wp_id"), "wp-1"),
        (["env", "--json", "wp-1"], ("wp_id",), "wp-1"),
        (["envs-history", "--json"], ("0", "wp_id"), "wp-history-1"),
        (["status", "--json"], ("user", "account"), "alice"),
        (["whoami", "--json"], ("account",), "alice"),
        (["ping", "--json"], ("reachable",), True),
        (["config", "--json"], ("default_timeout",), 9.0),
        (["version", "--json"], ("version",), "0.1.0"),
        (["logout", "--json"], ("logged_out",), True),
        (["login", "--json"], ("account",), "alice"),
    ],
)
def test_display_commands_accept_local_json(
    args: list[str],
    path: tuple[str, ...],
    expected: Any,
) -> None:
    payload = _invoke_json(args)
    current = payload
    for key in path:
        current = current[int(key)] if key.isdigit() else current[key]
    assert current == expected


@pytest.mark.usefixtures("fake_cli")
def test_local_json_flag_beats_quiet() -> None:
    payload = _invoke_json(["--quiet", "tasks", "--json"])
    assert payload[0]["id"] == "task-1"


@pytest.mark.usefixtures("fake_cli")
def test_global_json_flag_beats_quiet() -> None:
    payload = _invoke_json(["--json", "--quiet", "tasks"])
    assert payload[0]["id"] == "task-1"


@pytest.mark.usefixtures("fake_cli")
@pytest.mark.parametrize(
    ("args", "required_keys", "forbidden_keys"),
    [
        (
            ["gpus", "--json", "--short"],
            {"group_id", "group_name", "free_cards", "total_cards"},
            {"raw", "node_names", "total_cpu"},
        ),
        (
            ["tasks", "--json", "--short"],
            {"id", "name", "status", "cards"},
            {"config", "raw", "job_volume"},
        ),
        (
            ["task", "--json", "--short", "task-1"],
            {"id", "name", "status", "cards"},
            {"config", "raw", "job_volume"},
        ),
        (
            ["envs", "--json", "--short"],
            {"wp_id", "wp_name", "wp_status", "cpu", "cards"},
            {"raw", "env", "models", "volumes"},
        ),
        (
            ["config", "--json", "--short"],
            {"default_timeout", "verify_ssl", "image_registry_prefix"},
            {"log_level"},
        ),
    ],
)
def test_short_json_only_keeps_key_fields(
    args: list[str],
    required_keys: set[str],
    forbidden_keys: set[str],
) -> None:
    payload = _invoke_json(args)
    item = payload["task"] if isinstance(payload, dict) and "task" in payload else payload
    if isinstance(item, list):
        item = item[0]
    assert required_keys.issubset(item.keys())
    assert forbidden_keys.isdisjoint(item.keys())


@pytest.mark.usefixtures("fake_cli")
def test_global_short_flag_works_with_global_json() -> None:
    payload = _invoke_json(["--json", "--short", "tasks"])
    assert payload[0]["cards"] == 1
    assert "config" not in payload[0]
