from __future__ import annotations

import pytest

from aistation.errors import AiStationError
from aistation.modeling import OperationResult
from aistation.modeling import Image, JobVolume, Node, Pod, Task, User


def test_user_from_api(load_json_fixture) -> None:
    payload = load_json_fixture("login_response.json")["resData"]
    user = User.from_api(payload)

    assert user.account == "test-user"
    assert user.user_name == "Test User"
    assert user.group_id == "group-test-001"
    assert user.token == "token-test-user-001"


def test_node_from_api(load_json_fixture) -> None:
    payload = load_json_fixture("node_list_page1.json")["resData"]["data"][0]
    node = Node.from_api(payload)

    assert node.node_name == "gpu-node-a1"
    assert node.cards_total == 8
    assert node.cards_used == 1
    assert node.cards_free == 7
    assert node.task_users == ["user-a"]


def test_image_from_api(load_json_fixture) -> None:
    payload = load_json_fixture("images_list_page1.json")["resData"]["data"][0]
    image = Image.from_api(payload)

    assert image.full_ref == "registry.example.invalid/ml/pytorch:latest"
    assert image.share == 2
    assert image.make_type == 0


def test_task_from_api(load_json_fixture) -> None:
    payload = load_json_fixture("task_example.json")["resData"]["data"][0]
    task = Task.from_api(payload)

    assert task.name == "synthetic-training-task"
    assert task.project_id == "group-test-001"
    assert task.resource_group_name == "GPU-POOL-B"
    assert task.job_volume[0].volume_mount == "/workspace"


def test_pod_from_api(load_json_fixture) -> None:
    payload = load_json_fixture("pod_instance.json")["resData"]["data"][0]
    pod = Pod.from_api(payload)

    assert pod.pod_name == "worker-test-001"
    assert pod.ports[0].node_port == 30080
    assert pod.external_urls == ["198.51.100.24:30080"]


def test_job_volume_to_api_round_trip() -> None:
    volume = JobVolume(
        file_model=9,
        function_model=1,
        volume_mount="/data",
        storage_name="ssdwork",
        bucket="bucket-a",
        origin_path="/datasets/demo",
        dataset_cache_type="LOCAL_CACHE",
        file_type="DIR",
        is_unzip=True,
        volume_mount_alias="dataset",
        storage_type="NFS",
    )

    payload = volume.to_api()
    restored = JobVolume.from_api(payload)

    assert payload["originPath"] == "/datasets/demo"
    assert payload["isUnzip"] is True
    assert restored.volume_mount == "/data"
    assert restored.storage_name == "ssdwork"


def test_operation_result_require_entity_and_unwrap() -> None:
    result = OperationResult[Task](action="create", resource_type="task", target_id="task-1")

    with pytest.raises(AiStationError) as exc_info:
        result.require_entity()

    assert exc_info.value.err_code == "SDK_RESULT_UNRESOLVED"

    task = Task.from_api(
        {
            "id": "task-1",
            "name": "demo",
            "status": "Running",
            "userId": "u1",
            "userName": "alice",
            "projectId": "g1",
            "projectName": "project",
            "resGroupId": "group-1",
            "resGroupName": "GPU-POOL",
            "jobType": "pytorch",
            "image": "registry.example.invalid/ml/pytorch:latest",
            "imageType": "pytorch",
            "command": "sleep 30",
            "config": {"worker": {"nodeNum": 1, "cpuNum": 1, "acceleratorCardNum": 0, "memory": 1}},
        }
    )
    resolved = OperationResult[Task](action="create", resource_type="task", entity=task)

    assert resolved.require_entity().id == "task-1"
    assert resolved.unwrap().name == "demo"
