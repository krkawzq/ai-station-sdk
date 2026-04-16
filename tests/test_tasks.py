from __future__ import annotations

import json

import pytest

from aistation.client import AiStationClient
from aistation.config import AuthData, Config
from aistation.errors import AmbiguousMatchError
from aistation.modeling import User
from aistation.specs import TaskSpec

from .helpers import make_group, make_image, make_task


class _DummyGroups:
    def resolve(self, name_or_id: str):
        class _Group:
            group_id = "group-cpu"

        assert name_or_id in {"CPU", "group-cpu"}
        return _Group()

    def resolve_id(self, name_or_id: str) -> str:
        assert name_or_id in {"CPU", "group-cpu"}
        return "group-cpu"


class _TestClient(AiStationClient):
    def __init__(self) -> None:
        super().__init__(
            "https://example.test",
            config=Config(image_registry_prefix="registry.example.invalid"),
            auth=AuthData(account="alice", password="secret"),
        )
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
        self.groups = _DummyGroups()  # type: ignore[assignment]

    def post(self, path: str, json: dict | None = None, *, timeout=None):
        del timeout
        self.posts.append((path, json))
        if path == "/api/iresource/v1/train/check-resources":
            return {"checked": True}
        if path == "/api/iresource/v1/train":
            return {"taskId": "created-1"}
        return {"ok": True}

    def get(self, path: str, params: dict | None = None, *, timeout=None):
        del timeout
        key = (path, json.dumps(params, sort_keys=True) if params is not None else None)
        if key in self.get_map:
            return self.get_map[key]
        if path.endswith("/read-log"):
            return {"content": "log-lines"}
        return {"data": []}

    def list_all(self, path: str, *, params=None, timeout=None):
        del path, params, timeout
        self.list_all_calls += 1
        return list(self.list_all_rows)

    def _request_with_retry(self, method: str, path: str, *, params=None, json=None, timeout=None):
        del params, timeout
        self.retries.append((method, path, json))
        return {"ok": True, "path": path}


def _build_client() -> _TestClient:
    return _TestClient()


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


def test_build_payload_matches_current_contract() -> None:
    client = _build_client()
    spec = TaskSpec(
        name="HoldCPU1",
        resource_group="CPU",
        image="pytorch/pytorch:21.10-py3",
        command="sleep 30",
        cards=0,
        cpu=1,
        card_kind="CPU",
    )

    result = client.tasks.create(spec, dry_run=True)
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
    assert payload["command"] == "sleep 30"
    assert payload["shmSize"] == 4
    assert payload["ports"] == ""
    assert payload["distFlag"] is False
    assert payload["mpiFlag"] is False
    assert payload["isElastic"] is False
    assert payload["mountDir"] == "/alice"
    assert payload["jobVolume"] == [
        {
            "fileModel": 2,
            "functionModel": 2,
            "volumeMount": "/alice",
            "storageName": "master",
            "bucket": "",
        }
    ]
    assert json.loads(payload["config"]) == {
        "worker": {
            "nodeNum": 1,
            "cpuNum": 1,
            "acceleratorCardNum": 0,
            "memory": 0,
            "minNodeNum": -1,
        }
    }


def test_create_idempotent_returns_existing_task_without_post() -> None:
    client = _build_client()
    existing = make_task(name="HoldCPU2", status="Running")
    client.list_all_rows = [_task_to_api_dict(existing)]
    spec = TaskSpec(
        name="HoldCPU2",
        resource_group="CPU",
        image="pytorch/pytorch:21.10-py3",
        command="sleep 30",
        cards=0,
        cpu=1,
        card_kind="CPU",
    )

    result = client.tasks.create(spec)

    assert result.reused is True
    assert result.entity is not None
    assert result.entity.name == "HoldCPU2"
    assert client.posts == []


def test_build_payload_converts_env_and_dataset_fields() -> None:
    client = _build_client()
    spec = TaskSpec(
        name="MpiTask1",
        resource_group="CPU",
        image="other/dev:latest",
        command="python train.py",
        distributed="mpi",
        is_elastic=True,
        min_nodes=2,
        env={"ENV_A": "1"},
        log_path="/alice/logs",
        datasets=[
            {
                "file_model": 9,
                "volume_mount": "/data",
                "storage_name": "ssdwork",
                "origin_path": "/datasets/x",
                "dataset_cache_type": "LOCAL_CACHE",
                "file_type": "DIR",
                "is_unzip": True,
            }
        ],
    )

    result = client.tasks.create(spec, dry_run=True, validate=False)
    payload = result.payload

    assert payload["type"] == "mpi"
    assert payload["distFlag"] is True
    assert payload["mpiFlag"] is True
    assert json.loads(payload["config"])["worker"]["minNodeNum"] == 2
    assert payload["env"] == [{"name": "ENV_A", "value": "1"}]
    assert payload["jobVolume"][0]["functionModel"] == 1
    assert payload["jobVolume"][0]["isUnzip"] is True
    assert payload["jobVolume"][-1]["functionModel"] == 3


def test_check_resources_delete_stop_pods_and_logs() -> None:
    client = _build_client()
    client.get_map[("/api/iresource/v1/train/job-pod-instance", json.dumps({"id": "task-1"}, sort_keys=True))] = {
        "data": [
            {
                "podId": "pod-1",
                "podName": "pod-one",
                "podNameChanged": "pod-one",
                "podStatus": "Running",
                "nodeName": "gpu-node-1",
                "nodeIp": "198.51.100.10",
                "podIp": "203.0.113.10",
                "gpuIds": "GPU-1",
                "gpuNames": "gpu-node-1_0",
                "podGpuType": "Synthetic-A100-80GB",
                "ports": [{"port": 8080, "targetPort": 8080, "nodePort": 30080}],
                "restartCount": 0,
                "switchType": "IB",
                "createDateTime": 1,
            }
        ]
    }
    spec = TaskSpec(
        name="CheckTask1",
        resource_group="CPU",
        image="pytorch/pytorch:21.10-py3",
        command="sleep 30",
        cards=0,
        cpu=1,
        card_kind="CPU",
    )

    checked = client.tasks.check_resources(spec)
    pods = client.tasks.pods("task-1")
    log_text = client.tasks.read_log("task-1")
    deleted = client.tasks.delete(["task-1", "task-2"])
    stopped = client.tasks.stop("task-3")

    assert checked.action == "check_resources"
    assert checked.raw == {"checked": True}
    assert pods[0].external_urls == ["198.51.100.10:30080"]
    assert log_text == "log-lines"
    assert deleted.action == "delete"
    assert deleted.raw["ok"] is True
    assert deleted.target_ids == ["task-1", "task-2"]
    assert stopped.action == "stop"
    assert stopped.raw["ok"] is True
    assert stopped.target_id == "task-3"
    assert client.retries == [
        ("DELETE", "/api/iresource/v1/train", {"jobIdList": ["task-1", "task-2"]}),
        ("POST", "/api/iresource/v1/train/task-3/stop", None),
    ]


def test_create_returns_operation_result_and_wait_helper(monkeypatch) -> None:
    client = _build_client()
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

    monkeypatch.setattr(
        "aistation.tasks.wait_running",
        lambda client_, task_id, timeout, interval: make_task(task_id=task_id, name="HoldCPU3", status="Running"),
    )
    monkeypatch.setattr(
        "aistation.tasks.wait_pods",
        lambda client_, task_id, timeout, interval: [],
    )

    result = client.tasks.create(spec, idempotent=False)
    waited = client.tasks.create_and_wait(spec, idempotent=False, wait_for_pods=True)

    assert result.created is True
    assert result.entity is not None
    assert result.entity.id == "created-1"
    assert waited.waited is True
    assert waited.entity is not None
    assert waited.entity.status == "Running"
    assert waited.extras["pods"] == []


def test_task_resolve_and_ambiguity() -> None:
    client = _build_client()
    client.list_all_rows = [
        _task_to_api_dict(make_task(task_id="task-1", name="AlphaTask", status="Running")),
        _task_to_api_dict(make_task(task_id="task-2", name="BetaTask", status="Succeeded")),
    ]

    resolved = client.tasks.resolve("betatask")
    matched = client.tasks.resolve_many("task-1")

    assert resolved.id == "task-2"
    assert matched[0].name == "AlphaTask"

    client.list_all_rows = [
        _task_to_api_dict(make_task(task_id="task-1", name="SameTask", status="Running")),
        _task_to_api_dict(make_task(task_id="task-2", name="SameTask", status="Succeeded")),
    ]

    with pytest.raises(AmbiguousMatchError):
        client.tasks.resolve("SameTask", refresh=True)


def test_task_list_cache_refresh_and_object_refs() -> None:
    client = _build_client()
    task = make_task(task_id="task-1", name="CacheTask")
    client.list_all_rows = [_task_to_api_dict(task)]

    first = client.tasks.list()
    second = client.tasks.list()

    assert first[0].id == "task-1"
    assert second[0].id == "task-1"
    assert client.list_all_calls == 1

    client.list_all_rows = []
    assert client.tasks.list()[0].id == "task-1"
    assert client.tasks.list(refresh=True) == []

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

    dry_run = client.tasks.create(spec, dry_run=True)
    stopped = client.tasks.stop(task)
    deleted = client.tasks.delete([task])

    assert dry_run.payload["resGroupId"] == "group-cpu"
    assert dry_run.payload["image"] == "registry.example.invalid/pytorch/pytorch:21.10-py3"
    assert stopped.target_id == "task-1"
    assert deleted.target_ids == ["task-1"]


def test_task_create_retries_read_after_write(monkeypatch) -> None:
    client = _build_client()
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

    def fake_get(path: str, params: dict | None = None, *, timeout=None):
        key = json.dumps(params, sort_keys=True) if params is not None else None
        if path == "/api/iresource/v1/train" and key == json.dumps(
            {"id": "created-1", "statusFlag": 0, "page": 1, "pageSize": 1},
            sort_keys=True,
        ):
            attempts["count"] += 1
            if attempts["count"] < 3:
                return {"data": []}
            return {"data": [_task_to_api_dict(created)]}
        return original_get(path, params, timeout=timeout)

    client.get = fake_get  # type: ignore[method-assign]
    monkeypatch.setattr("aistation._consistency.time.sleep", lambda _: None)

    result = client.tasks.create(spec, idempotent=False)

    assert result.entity is not None
    assert result.entity.id == "created-1"
    assert attempts["count"] == 3
