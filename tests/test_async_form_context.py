from __future__ import annotations

import pytest

from aistation.aio.form_context import enumerate_form_context
from aistation.errors import PermissionDenied

from .helpers import make_image, make_user


class _DummyImages:
    def __init__(self) -> None:
        self.calls: list[dict | None] = []

    async def list(self, *, share=None):
        self.calls.append({"share": share})
        return [make_image()]


class _DummyGroups:
    async def list(self):
        raise PermissionDenied("denied", err_code="IBASE_NO_PERMISSION", err_message="权限不足")


class _DummyClient:
    def __init__(self) -> None:
        self.images = _DummyImages()
        self.groups = _DummyGroups()

    async def require_user(self):
        return make_user()

    async def get(self, path: str):
        if path == "/api/iresource/v1/image-type":
            return [{"id": "1", "name": "pytorch"}]
        if path == "/api/iresource/v1/base/timeout-task-type":
            return [{"typeCode": "1", "typeName": "训练任务", "platform": "train"}]
        if path == "/api/iresource/v1/config/shm":
            return 1
        if path == "/api/iresource/v1/train/start-file":
            return {"startScriptList": [{"path": "/workspace/run.sh"}]}
        raise AssertionError(path)


@pytest.mark.asyncio
async def test_async_enumerate_form_context_collects_missing_endpoints() -> None:
    client = _DummyClient()

    ctx = await enumerate_form_context(client)  # type: ignore[arg-type]

    assert ctx.user.account == "alice"
    assert [item.name for item in ctx.image_types] == ["pytorch"]
    assert [item.type_name for item in ctx.task_types] == ["训练任务"]
    assert ctx.start_scripts == [{"path": "/workspace/run.sh"}]
    assert ctx.shm_editable is True
    assert ctx.images[0].full_ref == "registry.example.invalid/ml/pytorch:latest"
    assert ctx.resource_groups == []
    assert ctx.missing == ["resource-groups: denied (IBASE_NO_PERMISSION)"]


@pytest.mark.asyncio
async def test_async_enumerate_form_context_can_limit_images() -> None:
    client = _DummyClient()

    await enumerate_form_context(client, include_all_images=False)  # type: ignore[arg-type]

    assert client.images.calls[-1] == {"share": 2}
