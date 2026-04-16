from __future__ import annotations

from aistation.errors import PermissionDenied
from aistation.form_context import enumerate_form_context

from .helpers import make_image, make_user


class _DummyImages:
    def __init__(self) -> None:
        self.calls: list[dict | None] = []

    def list(self, *, share=None):
        self.calls.append({"share": share})
        return [make_image()]


class _DummyGroups:
    def list(self):
        raise PermissionDenied("denied", err_code="IBASE_NO_PERMISSION", err_message="权限不足")


class _DummyClient:
    def __init__(self) -> None:
        self.images = _DummyImages()
        self.groups = _DummyGroups()

    def require_user(self):
        return make_user()

    def get(self, path: str):
        if path == "/api/iresource/v1/image-type":
            return [{"id": "1", "name": "pytorch"}]
        if path == "/api/iresource/v1/base/timeout-task-type":
            return [{"typeCode": "1", "typeName": "训练任务", "platform": "train"}]
        if path == "/api/iresource/v1/config/shm":
            return 1
        if path == "/api/iresource/v1/train/start-file":
            return {"startScriptList": [{"path": "/workspace/run.sh"}]}
        raise AssertionError(path)


def test_enumerate_form_context_collects_missing_endpoints() -> None:
    client = _DummyClient()

    ctx = enumerate_form_context(client)

    assert ctx.user.account == "alice"
    assert [item.name for item in ctx.image_types] == ["pytorch"]
    assert [item.type_name for item in ctx.task_types] == ["训练任务"]
    assert ctx.start_scripts == [{"path": "/workspace/run.sh"}]
    assert ctx.shm_editable is True
    assert ctx.images[0].full_ref == "registry.example.invalid/ml/pytorch:latest"
    assert ctx.resource_groups == []
    assert ctx.missing == ["resource-groups: denied (IBASE_NO_PERMISSION)"]


def test_enumerate_form_context_can_limit_images() -> None:
    client = _DummyClient()

    enumerate_form_context(client, include_all_images=False)

    assert client.images.calls[-1] == {"share": 2}
