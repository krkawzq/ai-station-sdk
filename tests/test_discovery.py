from __future__ import annotations

from aistation.discovery import discover_payload_requirements
from aistation.specs import TaskSpec


class _DummyTasks:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def _build_payload(self, spec: TaskSpec) -> dict:
        return {
            "name": spec.name,
            "config": "{\"worker\":{\"memory\":2,\"acceleratorCardNum\":1}}",
        }

    def delete(self, task_id: str) -> None:
        self.deleted.append(task_id)


class _DummyClient:
    def __init__(self, responses: list[dict]) -> None:
        self.tasks = _DummyTasks()
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict | None]] = []
        self.user = None

    def _raw_request(self, method: str, path: str, *, json=None, timeout=None):
        del timeout
        self.calls.append((method, path, json))
        return self._responses.pop(0)


def test_discover_payload_requirements_fixes_missing_field_and_cleans_up() -> None:
    client = _DummyClient(
        [
            {
                "flag": False,
                "errCode": "IRESOURCE_NOT_NULL_ILLEGAL",
                "errMessage": "入参[网络类型(switchType)] 不满足规则：不能为空",
            },
            {
                "flag": True,
                "resData": {"id": "created-task-1"},
            },
        ]
    )
    spec = TaskSpec(
        name="ProbeTask1",
        resource_group="GPU-POOL-A",
        image="ml/pytorch:latest",
        command="sleep 30",
    )

    report = discover_payload_requirements(
        client,
        spec,
        dry_validate=False,
        auto_delete_created=True,
        name_prefix="probe",
    )

    assert report.success is True
    assert report.created_task_id == "created-task-1"
    assert report.missing_fields == ["switchType"]
    assert report.final_payload["switchType"] == "ib"
    assert report.steps[0].action == "fix_missing"
    assert client.tasks.deleted == ["created-task-1"]
