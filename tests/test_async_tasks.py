from __future__ import annotations

import json

import pytest

from aistation.aio.tasks import AsyncTasksAPI
from aistation.config import Config
from aistation.errors import AmbiguousMatchError
from aistation.modeling import User
from aistation.specs import TaskSpec

from .helpers import make_group, make_image, make_task


class _DummyGroups:
    async def resolve(self, name_or_id: str):
        class _Group:
            group_id = "group-cpu"

        assert name_or_id in {"CPU", "group-cpu"}
        return _Group()


class _DummyNodes:
    def invalidate_cache(self) -> None:
        return None


class _DummyClient:
    def __init__(self) -> None:
        self.config = Config(image_registry_prefix="registry.example.invalid")
        self.posts: list[tuple[str, dict | None]] = []
        self.retries: list[tuple[str, str, dict | None]] = []
        self.list_all_rows: list[dict] = []
        self.list_all_calls = 0
        self.get_map: dict[tuple[str, str | None], object] = {}
        self.user = User(
            user_id="u1",
            account="alice",
            user_name="Alice",
            group_id="project-1",
            role_type=2,
            user_type=0,
            token="tok",
            is_first_login=False,
        )
        self.groups = _DummyGroups()
        self.nodes = _DummyNodes()

    async def require_user(self):
        return self.user

    async def post(self, path: str, json: dict | None = None, *, timeout=None):
        del timeout
        self.posts.append((path, json))
        if path == "/api/iresource/v1/train/check-resources":
            return {"checked": True}
        if path == "/api/iresource/v1/train":
            return {"taskId": "created-1"}
        return {"ok": True}

    async def get(self, path: str, params: dict | None = None, *, timeout=None):
        del timeout
        key = (path, json.dumps(params, sort_keys=True) if params is not None else None)
        if key in self.get_map:
            return self.get_map[key]
        if path.endswith("/read-log"):
            return {"content": "log-lines"}
        return {"data": []}

    async def list_all(self, path: str, *, params=None, timeout=None):
        del path, params, timeout
        self.list_all_calls += 1
        return list(self.list_all_rows)

    async def _request_with_retry(self, method: str, path: str, *, params=None, json=None, timeout=None):
        del params, timeout
        self.retries.append((method, path, json))
        return {"ok": True, "path": path}


def _task_to_api_dict(task):
    return {
        "id": task.id,
        "name": task.name,
        "status": task.status,
        "userId": task.user_id,
        "userName": task.user_name,
        "projectId": task.project_id,
        "projectName": task.project_name,
        "resGroupId": task.resource_group_id,
        "resGroupName": task.resource_group_name,
        "jobType": task.job_type,
        "image": task.image,
        "imageType": task.image_type,
        "imageFlag": task.image_flag,
        "command": task.command,
        "startScript": task.start_script,
        "execDir": task.exec_dir,
        "mountDir": task.mount_dir,
        "scriptDir": task.script_dir,
        "logOut": task.log_out,
        "logPersistence": task.log_persistence,
        "config": json.loads(task.config),
        "gpuInfo": {},
        "podInfo": {},
        "switchType": task.switch_type,
        "distFlag": task.dist_flag,
        "mpiFlag": task.mpi_flag,
        "isElastic": task.is_elastic,
        "shmSize": task.shm_size,
        "ports": task.ports,
        "emergencyFlag": task.emergency_flag,
        "taskType": task.task_type,
        "taskTypeName": task.task_type_name,
        "createDateTime": task.create_time_ms,
        "startDateTime": task.start_time_ms,
        "runTime": task.run_time_s,
        "nodeName": task.node_name,
        "jobVolume": [volume.to_api() for volume in task.job_volume],
        "statusReason": task.status_reason,
    }


@pytest.mark.asyncio
async def test_async_task_build_payload_matches_current_contract() -> None:
    client = _DummyClient()
    api = AsyncTasksAPI(client)  # type: ignore[arg-type]
    spec = TaskSpec(
        name="HoldCPU1",
        resource_group="CPU",
        image="pytorch/pytorch:21.10-py3",
        command="sleep 30",
        cards=0,
        cpu=1,
        card_kind="CPU",
    )

    result = await api.create(spec, dry_run=True)
    payload = result.payload

    assert result.entity is None
    assert result.created is False
    assert payload["name"] == "HoldCPU1"
    assert payload["projectId"] == "project-1"
    assert payload["resGroupId"] == "group-cpu"
    assert payload["image"] == "registry.example.invalid/pytorch/pytorch:21.10-py3"
    assert payload["imageType"] == "pytorch"
    assert payload["type"] == "pytorch"
    assert payload["acceleratorCardKind"] == "CPU"


@pytest.mark.asyncio
async def test_async_task_create_returns_operation_result_and_wait_helper(monkeypatch) -> None:
    client = _DummyClient()
    api = AsyncTasksAPI(client)  # type: ignore[arg-type]
    created = make_task(task_id="created-1", name="HoldCPU3", status="Pending")
    client.get_map[
        (
            "/api/iresource/v1/train",
            json.dumps({"id": "created-1", "statusFlag": 0, "page": 1, "pageSize": 1}, sort_keys=True),
        )
    ] = {"data": [_task_to_api_dict(created)]}
    spec = TaskSpec(
        name="HoldCPU3",
        resource_group="CPU",
        image="pytorch/pytorch:21.10-py3",
        command="sleep 30",
        cards=0,
        cpu=1,
        card_kind="CPU",
    )

    async def fake_wait_running(client_, task_id, timeout, interval):
        del client_, timeout, interval
        return make_task(task_id=task_id, name="HoldCPU3", status="Running")

    async def fake_wait_pods(client_, task_id, timeout, interval):
        del client_, task_id, timeout, interval
        return []

    monkeypatch.setattr("aistation.aio.tasks.wait_running", fake_wait_running)
    monkeypatch.setattr("aistation.aio.tasks.wait_pods", fake_wait_pods)

    result = await api.create(spec, idempotent=False)
    waited = await api.create_and_wait(spec, idempotent=False, wait_for_pods=True)

    assert result.created is True
    assert result.entity is not None
    assert result.entity.id == "created-1"
    assert waited.waited is True
    assert waited.entity is not None
    assert waited.entity.status == "Running"
    assert waited.extras["pods"] == []


@pytest.mark.asyncio
async def test_async_task_resolve_and_ambiguity() -> None:
    client = _DummyClient()
    api = AsyncTasksAPI(client)  # type: ignore[arg-type]
    client.list_all_rows = [
        _task_to_api_dict(make_task(task_id="task-1", name="AlphaTask", status="Running")),
        _task_to_api_dict(make_task(task_id="task-2", name="BetaTask", status="Succeeded")),
    ]

    resolved = await api.resolve("betatask")
    matched = await api.resolve_many("task-1")

    assert resolved.id == "task-2"
    assert matched[0].name == "AlphaTask"

    client.list_all_rows = [
        _task_to_api_dict(make_task(task_id="task-1", name="SameTask", status="Running")),
        _task_to_api_dict(make_task(task_id="task-2", name="SameTask", status="Succeeded")),
    ]

    with pytest.raises(AmbiguousMatchError):
        await api.resolve("SameTask", refresh=True)


@pytest.mark.asyncio
async def test_async_task_list_cache_refresh_and_object_refs() -> None:
    client = _DummyClient()
    api = AsyncTasksAPI(client)  # type: ignore[arg-type]
    task = make_task(task_id="task-1", name="CacheTask")
    client.list_all_rows = [_task_to_api_dict(task)]

    first = await api.list()
    second = await api.list()

    assert first[0].id == "task-1"
    assert second[0].id == "task-1"
    assert client.list_all_calls == 1

    client.list_all_rows = []
    assert (await api.list())[0].id == "task-1"
    assert await api.list(refresh=True) == []

    group = make_group(group_id="group-cpu", group_name="CPU")
    image = make_image(name="registry.example.invalid/pytorch/pytorch", tag="21.10-py3")
    spec = TaskSpec(
        name="ObjectInput1",
        resource_group=group,
        image=image,
        command="sleep 30",
        cards=0,
        cpu=1,
        card_kind="CPU",
    )

    dry_run = await api.create(spec, dry_run=True)
    stopped = await api.stop(task)
    deleted = await api.delete([task])

    assert dry_run.payload["resGroupId"] == "group-cpu"
    assert dry_run.payload["image"] == "registry.example.invalid/pytorch/pytorch:21.10-py3"
    assert stopped.target_id == "task-1"
    assert deleted.target_ids == ["task-1"]


@pytest.mark.asyncio
async def test_async_task_create_retries_read_after_write(monkeypatch) -> None:
    client = _DummyClient()
    api = AsyncTasksAPI(client)  # type: ignore[arg-type]
    spec = TaskSpec(
        name="RetryTask1",
        resource_group="CPU",
        image="pytorch/pytorch:21.10-py3",
        command="sleep 30",
        cards=0,
        cpu=1,
        card_kind="CPU",
    )
    created = make_task(task_id="created-1", name="RetryTask1", status="Pending")
    attempts = {"count": 0}
    original_get = client.get

    async def fake_get(path: str, params: dict | None = None, *, timeout=None):
        key = json.dumps(params, sort_keys=True) if params is not None else None
        if path == "/api/iresource/v1/train" and key == json.dumps(
            {"id": "created-1", "statusFlag": 0, "page": 1, "pageSize": 1},
            sort_keys=True,
        ):
            attempts["count"] += 1
            if attempts["count"] < 3:
                return {"data": []}
            return {"data": [_task_to_api_dict(created)]}
        return await original_get(path, params, timeout=timeout)

    client.get = fake_get  # type: ignore[method-assign]

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("aistation._consistency.asyncio.sleep", fake_sleep)

    result = await api.create(spec, idempotent=False)

    assert result.entity is not None
    assert result.entity.id == "created-1"
    assert attempts["count"] == 3
