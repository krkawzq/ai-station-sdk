from __future__ import annotations

import pytest

from aistation.aio.workplatform import AsyncWorkPlatformsAPI
from aistation.errors import AmbiguousMatchError
from aistation.specs import WorkPlatformSpec

from .helpers import make_group, make_image, make_user, make_workplatform


class _DummyClient:
    def __init__(self) -> None:
        self.user = make_user()
        self.get_calls: list[tuple[str, dict | None]] = []
        self.post_calls: list[tuple[str, dict | None]] = []
        self.put_calls: list[tuple[str, dict | None]] = []
        self.retry_calls: list[tuple[str, str, dict | None]] = []
        self.invalidations = 0

    async def require_user(self):
        return self.user

    @property
    def nodes(self):
        client = self

        class _Nodes:
            def invalidate_cache(self_nonlocal):
                client.invalidations += 1

        return _Nodes()

    @property
    def images(self):
        client = self

        class _Images:
            def invalidate_cache(self_nonlocal):
                client.invalidations += 1

        return _Images()

    async def get(self, path: str, params: dict | None = None, *, timeout=None):
        del timeout
        self.get_calls.append((path, params))
        if path == "/api/iresource/v1/work-platform/goto-train-job":
            return {
                "data": [
                    {
                        "wpId": "wp-1",
                        "wpName": "DevBoxOne",
                        "wpStatus": "Running",
                        "groupId": "group-dev",
                        "groupName": "DEV-POOL",
                        "image": "registry.example.invalid/ml/dev:latest",
                        "imageType": "INNER_IMAGE",
                        "frameWork": "other",
                    }
                ]
            }
        if path == "/api/iresource/v1/node-group":
            return {
                "data": [
                    {
                        "groupId": "group-dev",
                        "groupName": "DEV-POOL",
                        "acceleratorCardKind": "CPU",
                        "nodeCount": 2,
                        "acceleratorCardCount": 0,
                        "usedAcceleratorCardCount": 0,
                        "cpuCoreNum": 64,
                    }
                ]
            }
        if path == "/api/iresource/v1/work-platform/wp-new/detail":
            return {
                "wpId": "wp-new",
                "wpName": "NotebookOne",
                "wpStatus": "Running",
                "groupId": "group-dev",
                "groupName": "DEV-POOL",
                "image": "registry.example.invalid/ml/dev:latest",
                "imageType": "INNER_IMAGE",
                "frameWork": "other",
                "cpu": 2,
                "memory": 8,
                "acceleratorCard": 0,
                "acceleratorCardKind": "CPU",
                "command": "sleep 3600",
            }
        return {"data": []}

    async def post(self, path: str, json: dict | None = None, *, timeout=None):
        del timeout
        self.post_calls.append((path, json))
        if path == "/api/iresource/v1/work-platform/":
            return {"wpId": "wp-new"}
        return {"ok": True}

    async def delete(self, path: str, *, timeout=None):
        del timeout
        return {"deleted": path}

    async def put(self, path: str, json: dict | None = None, *, timeout=None):
        del timeout
        self.put_calls.append((path, json))
        return {"ok": True}

    async def _request_with_retry(self, method: str, path: str, *, params=None, json=None, timeout=None):
        del params, timeout
        self.retry_calls.append((method, path, json))
        return {"ok": True}


@pytest.mark.asyncio
async def test_async_workplatform_create_posts_and_fetches_detail() -> None:
    client = _DummyClient()
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]
    spec = WorkPlatformSpec(
        name="NotebookOne",
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
        command="sleep 3600",
    )

    result = await api.create(spec, idempotent=False)

    assert result.created is True
    assert result.entity is not None
    assert result.entity.wp_id == "wp-new"
    assert client.post_calls[0][0] == "/api/iresource/v1/work-platform/"
    assert client.invalidations == 1


@pytest.mark.asyncio
async def test_async_workplatform_resolve_and_wait_ready(monkeypatch) -> None:
    client = _DummyClient()
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]

    async def fake_wait_ready(client_, wp_id, timeout, interval):
        del client_, timeout, interval
        return await api.get(wp_id)

    monkeypatch.setattr("aistation.aio.workplatform.wait_workplatform_ready", fake_wait_ready)
    spec = WorkPlatformSpec(
        name="NotebookOne",
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
        command="sleep 3600",
    )

    resolved = await api.resolve("DevBoxOne", search_history=False)
    waited = await api.create_and_wait_ready(spec, idempotent=False, timeout=1.0, interval=0.0)

    assert resolved.wp_name == "DevBoxOne"
    assert waited.waited is True
    assert waited.entity is not None
    assert waited.entity.wp_id == "wp-new"


@pytest.mark.asyncio
async def test_async_workplatform_resolve_ambiguous() -> None:
    client = _DummyClient()
    original_get = client.get

    async def fake_history(path: str, params: dict | None = None, *, timeout=None):
        if path == "/api/iresource/v1/work-platform/goto-train-job":
            return {
                "data": [
                    {
                        "wpId": "wp-1",
                        "wpName": "SharedName",
                        "wpStatus": "Running",
                        "groupId": "group-dev",
                        "groupName": "DEV-POOL",
                        "image": "registry.example.invalid/ml/dev:latest",
                        "imageType": "INNER_IMAGE",
                        "frameWork": "other",
                    }
                ]
            }
        if path == "/api/iresource/v1/work-platform/history":
            return {
                "data": [
                    {
                        "wpId": "wp-2",
                        "wpName": "SharedName",
                        "wpStatus": "Stopped",
                        "groupId": "group-dev",
                        "groupName": "DEV-POOL",
                        "image": "registry.example.invalid/ml/dev:latest",
                        "imageType": "INNER_IMAGE",
                        "frameWork": "other",
                    }
                ]
            }
        return await original_get(path, params, timeout=timeout)

    client.get = fake_history  # type: ignore[method-assign]
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]

    with pytest.raises(AmbiguousMatchError):
        await api.resolve("SharedName")


@pytest.mark.asyncio
async def test_async_workplatform_toggle_collect_uses_client_put() -> None:
    client = _DummyClient()
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]

    toggled = await api.toggle_history_collect("wp-1", True)

    assert toggled.action == "toggle_history_collect"
    assert toggled.raw == {"ok": True}
    assert toggled.extras["collected"] is True
    assert client.put_calls == [
        (
            "/api/iresource/v1/work-platform/history-collect/",
            {"wpId": "wp-1", "isHistoryCollect": 1},
        )
    ]


@pytest.mark.asyncio
async def test_async_workplatform_resolve_by_name_skips_eager_detail() -> None:
    client = _DummyClient()
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]

    resolved = await api.resolve("DevBoxOne", search_history=False)

    assert resolved.wp_id == "wp-1"
    assert "/api/iresource/v1/work-platform/wp-1/detail" not in [path for path, _ in client.get_calls]


@pytest.mark.asyncio
async def test_async_workplatform_search_history_false_skips_history_requests() -> None:
    client = _DummyClient()
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]

    await api.resolve("DevBoxOne", search_history=False)

    assert "/api/iresource/v1/work-platform/history" not in [path for path, _ in client.get_calls]


@pytest.mark.asyncio
async def test_async_workplatform_search_history_true_only_fetches_history_once() -> None:
    client = _DummyClient()
    original_get = client.get
    history_calls = {"count": 0}

    async def fake_get(path: str, params: dict | None = None, *, timeout=None):
        if path == "/api/iresource/v1/work-platform/history":
            history_calls["count"] += 1
            return {
                "data": [
                    {
                        "wpId": "wp-2",
                        "wpName": "HistoryBox",
                        "wpStatus": "Stopped",
                        "groupId": "group-dev",
                        "groupName": "DEV-POOL",
                        "image": "registry.example.invalid/ml/dev:latest",
                        "imageType": "INNER_IMAGE",
                        "frameWork": "other",
                    }
                ]
            }
        return await original_get(path, params, timeout=timeout)

    client.get = fake_get  # type: ignore[method-assign]
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]

    resolved = await api.resolve("HistoryBox")

    assert resolved.wp_id == "wp-2"
    assert history_calls["count"] == 1


@pytest.mark.asyncio
async def test_async_workplatform_accepts_object_inputs_and_notebook_spec(monkeypatch) -> None:
    client = _DummyClient()
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]
    workplatform = make_workplatform()
    group = make_group(group_id="group-dev", group_name="DEV-POOL", card_kind="CPU")
    image = make_image(name="registry.example.invalid/ml/dev", tag="latest", image_type="other")

    monkeypatch.setattr("aistation.specs.uuid.uuid4", lambda: type("U", (), {"hex": "feedfacecafebeef"})())

    spec = WorkPlatformSpec.notebook(
        resource_group=group,
        image=image,
        env={"MODE": "lab"},
        ports=[8888],
    )
    cloned = WorkPlatformSpec.from_existing(workplatform)
    dry_run = await api.create(spec, dry_run=True, idempotent=False)
    deleted = await api.delete(workplatform)
    rebuilt = await api.rebuild_template(workplatform)
    jupyter = await api.jupyter_url(workplatform)

    assert spec.name == "notebookfeedface"
    assert cloned.resource_group == "DEV-POOL"
    assert dry_run.payload["groupId"] == "group-dev"
    assert dry_run.payload["image"] == "registry.example.invalid/ml/dev:latest"
    assert deleted.target_id == "wp-1"
    assert rebuilt == {"data": []}
    assert jupyter == {"data": []}


@pytest.mark.asyncio
async def test_async_workplatform_create_retries_detail_lookup(monkeypatch) -> None:
    client = _DummyClient()
    api = AsyncWorkPlatformsAPI(client)  # type: ignore[arg-type]
    spec = WorkPlatformSpec(
        name="NotebookOne",
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
        command="sleep 3600",
    )
    attempts = {"count": 0}
    original_get = client.get

    async def fake_get(path: str, params: dict | None = None, *, timeout=None):
        if path == "/api/iresource/v1/work-platform/wp-new/detail":
            attempts["count"] += 1
            if attempts["count"] < 3:
                return {}
        return await original_get(path, params, timeout=timeout)

    client.get = fake_get  # type: ignore[method-assign]

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("aistation._consistency.asyncio.sleep", fake_sleep)

    result = await api.create(spec, idempotent=False)

    assert result.entity is not None
    assert result.entity.wp_id == "wp-new"
    assert attempts["count"] == 3
