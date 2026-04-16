from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from aistation.cli.main import app
from aistation.config import AuthData, Config
from aistation.modeling.runtime import OperationResult

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
        assert name_or_id in {"group-1", "GPU-POOL-A"}
        return "group-1"


class _FakeNodesAPI:
    def list(self, *, group_id: str | None = None) -> list[Any]:
        return [make_node(group_id=group_id or "group-1")]


class _FakeImagesAPI:
    def list(self, *, image_type: str | None = None, share: int | None = None) -> list[Any]:
        image = make_image(image_type=image_type or "pytorch", share=share or 2)
        return [image]


class _FakeTasksAPI:
    def __init__(self) -> None:
        self.last_create_spec: Any | None = None
        self.last_delete_targets: list[str] = []
        self.last_stop_target: str | None = None

    def list(self, *, status_flag: int = 0) -> list[Any]:
        status = "Running" if status_flag == 0 else "Finished"
        suffix = "running" if status_flag == 0 else "finished"
        return [make_task(task_id=f"task-{suffix}-1", name=f"Task{suffix.title()}One", status=status)]

    def get(self, task_id: str | Any) -> Any:
        resolved = getattr(task_id, "id", task_id)
        return make_task(task_id=resolved, name="TaskOne", status="Running")

    def resolve(self, query: str, *, include_finished: bool = True) -> Any:
        del include_finished
        if query in {"task-1", "task", "TaskOne", "task-running-1", "TaskRunningOne"}:
            return make_task(task_id="task-1", name="TaskOne", status="Running")
        return make_task(task_id=query, name=f"Resolved-{query}", status="Running")

    def pods(self, task_id: str | Any) -> list[Any]:
        del task_id
        return [make_pod()]

    def read_log(self, task_id: str | Any, *, pod_name: str | None = None) -> str:
        resolved = getattr(task_id, "id", task_id)
        suffix = f":{pod_name}" if pod_name else ""
        return f"log for {resolved}{suffix}"

    def wait_running(self, task_id: str | Any, *, timeout: float = 600.0, interval: float = 5.0) -> Any:
        del timeout, interval
        resolved = getattr(task_id, "id", task_id)
        return make_task(task_id=resolved, name="TaskOne", status="Running")

    def wait_pods(self, task_id: str | Any, *, timeout: float = 120.0, interval: float = 3.0) -> list[Any]:
        del task_id, timeout, interval
        return [make_pod(node_port=30081)]

    def create(
        self,
        spec: Any,
        *,
        dry_run: bool = False,
        validate: bool = True,
        precheck: bool = True,
        idempotent: bool = True,
    ) -> OperationResult[Any]:
        del validate, precheck, idempotent
        self.last_create_spec = spec
        payload = {"name": spec.name, "resource_group": spec.resource_group, "image": spec.image}
        if dry_run:
            return OperationResult(action="create", resource_type="task", payload=payload, raw=payload)
        entity = make_task(task_id="task-created-1", name=spec.name, status="Running")
        return OperationResult(
            action="create",
            resource_type="task",
            entity=entity,
            payload=payload,
            raw={"taskId": entity.id},
            target_id=entity.id,
            target_ids=[entity.id],
            created=True,
        )

    def create_and_wait(
        self,
        spec: Any,
        *,
        validate: bool = True,
        precheck: bool = True,
        idempotent: bool = True,
        timeout: float = 600.0,
        interval: float = 5.0,
        wait_for_pods: bool = False,
        pod_timeout: float = 120.0,
        pod_interval: float = 3.0,
    ) -> OperationResult[Any]:
        del validate, precheck, idempotent, timeout, interval, pod_timeout, pod_interval
        self.last_create_spec = spec
        entity = make_task(task_id="task-created-1", name=spec.name, status="Running")
        result = OperationResult(
            action="create",
            resource_type="task",
            entity=entity,
            payload={"name": spec.name},
            raw={"taskId": entity.id},
            target_id=entity.id,
            target_ids=[entity.id],
            created=True,
            waited=True,
        )
        if wait_for_pods:
            result.extras["pods"] = [make_pod(node_port=30081)]
        return result

    def delete(self, task_id: str | Any | list[str | Any]) -> OperationResult[Any]:
        if isinstance(task_id, list):
            resolved = [getattr(item, "id", item) for item in task_id]
        else:
            resolved = [getattr(task_id, "id", task_id)]
        self.last_delete_targets = resolved
        return OperationResult(
            action="delete",
            resource_type="task",
            raw={"ok": True},
            target_id=resolved[0],
            target_ids=resolved,
        )

    def stop(self, task_id: str | Any) -> OperationResult[Any]:
        resolved = getattr(task_id, "id", task_id)
        self.last_stop_target = resolved
        return OperationResult(
            action="stop",
            resource_type="task",
            raw={"ok": True},
            target_id=resolved,
            target_ids=[resolved],
        )


class _FakeWorkPlatformsAPI:
    def __init__(self) -> None:
        self.last_create_spec: Any | None = None
        self.last_delete_target: str | None = None

    def list(self, *, include_halted: bool = False) -> list[Any]:
        status = "Halt" if include_halted else "Running"
        return [make_workplatform(status=status)]

    def list_history(self, *, page: int = 1, page_size: int = 20) -> list[Any]:
        del page_size
        return [make_workplatform(wp_id=f"wp-history-{page}", status="Stopped")]

    def get(self, wp_id: str | Any) -> Any:
        resolved = getattr(wp_id, "wp_id", wp_id)
        return make_workplatform(wp_id=resolved)

    def resolve(
        self,
        query: str | Any,
        *,
        include_halted: bool = True,
        search_history: bool = True,
    ) -> Any:
        del include_halted, search_history
        resolved = getattr(query, "wp_id", query)
        if resolved in {"wp-1", "DevBoxOne", "env"}:
            return make_workplatform(wp_id="wp-1", name="DevBoxOne", status="Running")
        return make_workplatform(wp_id=str(resolved), name=f"Resolved-{resolved}", status="Running")

    def jupyter_url(self, wp_id: str | Any) -> dict[str, Any]:
        resolved = getattr(wp_id, "wp_id", wp_id)
        return {"url": f"https://example.test/jupyter/{resolved}"}

    def shell_url(self, wp_id: str | Any, *, pod_id: str | None = None) -> dict[str, Any]:
        resolved = getattr(wp_id, "wp_id", wp_id)
        suffix = f"/{pod_id}" if pod_id else ""
        return {"url": f"https://example.test/shell/{resolved}{suffix}"}

    def wait_ready(self, wp_id: str | Any, *, timeout: float = 600.0, interval: float = 5.0) -> Any:
        del timeout, interval
        resolved = getattr(wp_id, "wp_id", wp_id)
        return make_workplatform(wp_id=resolved, status="Running")

    def create(
        self,
        spec: Any,
        *,
        dry_run: bool = False,
        idempotent: bool = True,
    ) -> OperationResult[Any]:
        del idempotent
        self.last_create_spec = spec
        payload = {"wpName": spec.name, "group": spec.resource_group, "image": spec.image}
        if dry_run:
            return OperationResult(action="create", resource_type="workplatform", payload=payload, raw=payload)
        entity = make_workplatform(wp_id="wp-created-1", name=spec.name, status="Running")
        return OperationResult(
            action="create",
            resource_type="workplatform",
            entity=entity,
            payload=payload,
            raw={"wpId": entity.wp_id},
            target_id=entity.wp_id,
            target_ids=[entity.wp_id],
            created=True,
        )

    def create_and_wait_ready(
        self,
        spec: Any,
        *,
        idempotent: bool = True,
        timeout: float = 600.0,
        interval: float = 5.0,
    ) -> OperationResult[Any]:
        del idempotent, timeout, interval
        self.last_create_spec = spec
        entity = make_workplatform(wp_id="wp-created-1", name=spec.name, status="Running")
        return OperationResult(
            action="create",
            resource_type="workplatform",
            entity=entity,
            payload={"wpName": spec.name},
            raw={"wpId": entity.wp_id},
            target_id=entity.wp_id,
            target_ids=[entity.wp_id],
            created=True,
            waited=True,
        )

    def delete(self, wp_id: str | Any) -> OperationResult[Any]:
        resolved = getattr(wp_id, "wp_id", wp_id)
        self.last_delete_target = resolved
        return OperationResult(
            action="delete",
            resource_type="workplatform",
            raw={"ok": True},
            target_id=resolved,
            target_ids=[resolved],
        )


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
        del account, password, captcha
        return self._user

    def ping(self) -> dict[str, Any]:
        return {
            "reachable": True,
            "token_valid": True,
            "error": None,
        }


@pytest.fixture
def fake_cli(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
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
    return client


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
        (["task", "list", "--json"], ("items", "0", "id"), "task-running-1"),
        (["task", "get", "task-1", "--json"], ("item", "id"), "task-1"),
        (["task", "resolve", "TaskOne", "--json"], ("item", "id"), "task-1"),
        (["task", "pods", "task-1", "--json"], ("items", "0", "pod_id"), "pod-1"),
        (["task", "logs", "task-1", "--json"], ("log",), "log for task-1"),
        (["task", "wait", "task-1", "--json"], ("item", "status"), "Running"),
        (["env", "list", "--json"], ("items", "0", "wp_id"), "wp-1"),
        (["env", "get", "wp-1", "--json"], ("item", "wp_id"), "wp-1"),
        (["env", "resolve", "DevBoxOne", "--json"], ("item", "wp_id"), "wp-1"),
        (["env", "history", "--json"], ("items", "0", "wp_id"), "wp-history-1"),
        (["env", "urls", "wp-1", "--json"], ("jupyter", "url"), "https://example.test/jupyter/wp-1"),
        (["env", "wait", "wp-1", "--json"], ("item", "wp_id"), "wp-1"),
        (["status", "--json"], ("user", "account"), "alice"),
        (["whoami", "--json"], ("account",), "alice"),
        (["ping", "--json"], ("reachable",), True),
        (["config", "--json"], ("default_timeout",), 9.0),
        (["version", "--json"], ("version",), "0.3.0"),
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
    payload = _invoke_json(["--quiet", "task", "list", "--json"])
    assert payload["items"][0]["id"] == "task-running-1"


@pytest.mark.usefixtures("fake_cli")
def test_global_json_flag_beats_quiet() -> None:
    payload = _invoke_json(["--json", "--quiet", "task", "list"])
    assert payload["items"][0]["id"] == "task-running-1"


@pytest.mark.usefixtures("fake_cli")
@pytest.mark.parametrize(
    ("args", "required_keys", "forbidden_keys", "path"),
    [
        (
            ["task", "list", "--json", "--short"],
            {"id", "name", "status", "cards"},
            {"config", "raw", "job_volume"},
            ("items", "0"),
        ),
        (
            ["task", "get", "task-1", "--json", "--short"],
            {"id", "name", "status", "cards"},
            {"config", "raw", "job_volume"},
            ("item",),
        ),
        (
            ["env", "list", "--json", "--short"],
            {"wp_id", "wp_name", "wp_status", "cpu", "cards"},
            {"raw", "env", "models", "volumes"},
            ("items", "0"),
        ),
        (
            ["env", "get", "wp-1", "--json", "--short"],
            {"wp_id", "wp_name", "wp_status", "cpu", "cards"},
            {"raw", "env", "models", "volumes"},
            ("item",),
        ),
        (
            ["config", "--json", "--short"],
            {"default_timeout", "verify_ssl", "image_registry_prefix"},
            {"log_level"},
            (),
        ),
    ],
)
def test_short_json_only_keeps_key_fields(
    args: list[str],
    required_keys: set[str],
    forbidden_keys: set[str],
    path: tuple[str, ...],
) -> None:
    payload = _invoke_json(args)
    item = payload
    for key in path:
        item = item[int(key)] if key.isdigit() else item[key]
    assert required_keys.issubset(item.keys())
    assert forbidden_keys.isdisjoint(item.keys())


@pytest.mark.usefixtures("fake_cli")
def test_global_short_flag_works_with_global_json() -> None:
    payload = _invoke_json(["--json", "--short", "task", "list"])
    assert payload["items"][0]["cards"] == 1
    assert "config" not in payload["items"][0]


def test_task_create_from_flags(fake_cli: _FakeClient) -> None:
    payload = _invoke_json(
        [
            "task",
            "create",
            "--json",
            "--short",
            "--name",
            "TaskFromFlags",
            "--group",
            "GPU-POOL-A",
            "--image",
            "registry.example.invalid/ml/pytorch:latest",
            "--command",
            "python train.py",
            "--cards",
            "2",
            "--cpu",
            "16",
            "--memory-gb",
            "64",
            "--port",
            "8080",
            "--env",
            "MODE=train",
            "--dataset-json",
            '{"file_model": 2, "function_model": 1, "volume_mount": "/data", "storage_name": "master"}',
            "--wait-pods",
        ]
    )

    assert payload["item"]["name"] == "TaskFromFlags"
    assert payload["pod_count"] == 1
    spec = fake_cli.tasks.last_create_spec
    assert spec is not None
    assert spec.name == "TaskFromFlags"
    assert spec.resource_group == "GPU-POOL-A"
    assert spec.cards == 2
    assert spec.cpu == 16
    assert spec.memory_gb == 64
    assert spec.ports == [8080]
    assert spec.env == {"MODE": "train"}
    assert spec.datasets[0]["volume_mount"] == "/data"


def test_task_create_from_file_with_cli_overrides(tmp_path: Path, fake_cli: _FakeClient) -> None:
    task_file = tmp_path / "task.yaml"
    task_file.write_text(
        """
task:
  name: FileTask
  resource_group: GPU-POOL-A
  image: registry.example.invalid/ml/pytorch:latest
  command: python file_train.py
  cards: 1
  cpu: 8
  memory_gb: 32
  env:
    SOURCE: file
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = _invoke_json(
        [
            "task",
            "create",
            "--json",
            "--short",
            "--file",
            str(task_file),
            "--cpu",
            "12",
            "--env",
            "EXTRA=1",
        ]
    )

    assert payload["item"]["name"] == "FileTask"
    spec = fake_cli.tasks.last_create_spec
    assert spec is not None
    assert spec.cpu == 12
    assert spec.env == {"SOURCE": "file", "EXTRA": "1"}


def test_task_delete_and_stop(fake_cli: _FakeClient) -> None:
    delete_payload = _invoke_json(["task", "delete", "--json", "task-1", "TaskOne"])
    stop_payload = _invoke_json(["task", "stop", "--json", "task-1"])

    assert delete_payload["count"] == 1
    assert fake_cli.tasks.last_delete_targets == ["task-1"]
    assert stop_payload["target_id"] == "task-1"
    assert fake_cli.tasks.last_stop_target == "task-1"


def test_env_create_from_flags_and_urls(fake_cli: _FakeClient) -> None:
    create_payload = _invoke_json(
        [
            "env",
            "create",
            "--json",
            "--short",
            "--name",
            "EnvFromFlags",
            "--group",
            "DEV-POOL",
            "--image",
            "registry.example.invalid/ml/dev:latest",
            "--command",
            "sleep infinity",
            "--cpu",
            "8",
            "--memory-gb",
            "32",
            "--port",
            "8888",
            "--env",
            "MODE=lab",
            "--wait",
        ]
    )
    urls_payload = _invoke_json(["env", "urls", "wp-1", "--json"])

    assert create_payload["item"]["wp_name"] == "EnvFromFlags"
    spec = fake_cli.workplatforms.last_create_spec
    assert spec is not None
    assert spec.cpu == 8
    assert spec.memory_gb == 32
    assert spec.ports == [8888]
    assert spec.env == {"MODE": "lab"}
    assert urls_payload["shell"]["url"] == "https://example.test/shell/wp-1"


def test_env_create_from_file_and_delete(tmp_path: Path, fake_cli: _FakeClient) -> None:
    env_file = tmp_path / "env.yaml"
    env_file.write_text(
        """
env:
  name: FileEnv
  resource_group: DEV-POOL
  image: registry.example.invalid/ml/dev:latest
  command: sleep infinity
  cpu: 4
  memory_gb: 16
  env:
    SOURCE: file
""".strip()
        + "\n",
        encoding="utf-8",
    )

    create_payload = _invoke_json(
        [
            "env",
            "create",
            "--json",
            "--short",
            "--file",
            str(env_file),
            "--env",
            "EXTRA=1",
        ]
    )
    delete_payload = _invoke_json(["env", "delete", "--json", "wp-1"])

    assert create_payload["item"]["wp_name"] == "FileEnv"
    spec = fake_cli.workplatforms.last_create_spec
    assert spec is not None
    assert spec.env == {"SOURCE": "file", "EXTRA": "1"}
    assert delete_payload["target_id"] == "wp-1"
    assert fake_cli.workplatforms.last_delete_target == "wp-1"


@pytest.mark.usefixtures("fake_cli")
@pytest.mark.parametrize(
    ("args", "field", "code"),
    [
        (["task", "list", "--json", "--status", "weird"], "--status", "SDK_CLI_BAD_SPEC_INPUT"),
        (
            [
                "task",
                "create",
                "--json",
                "--name",
                "BadTask",
                "--group",
                "GPU-POOL-A",
                "--image",
                "registry.example.invalid/ml/pytorch:latest",
                "--command",
                "python train.py",
                "--port",
                "70000",
            ],
            "--port",
            "SDK_CLI_BAD_SPEC_INPUT",
        ),
        (["task", "wait", "--json", "task-1", "--timeout", "0"], "--timeout", "SDK_CLI_BAD_SPEC_INPUT"),
        (["env", "history", "--json", "--page", "0"], "--page", "SDK_CLI_BAD_SPEC_INPUT"),
        (["env", "wait", "--json", "wp-1", "--interval", "-1"], "--interval", "SDK_CLI_BAD_SPEC_INPUT"),
    ],
)
def test_cli_validation_errors_are_structured(
    args: list[str],
    field: str,
    code: str,
) -> None:
    result = runner.invoke(app, args, catch_exceptions=False)
    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["error"]["code"] == code
    assert payload["error"]["field"] == field
