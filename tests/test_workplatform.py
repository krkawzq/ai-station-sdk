from __future__ import annotations

import pytest

from aistation.errors import AmbiguousMatchError
from aistation.specs import WorkPlatformSpec
from aistation.workplatform import WorkPlatformsAPI

from .helpers import make_group, make_image, make_user, make_workplatform


class _DummyClient:
    def __init__(self) -> None:
        self.user = make_user()
        self.get_calls: list[tuple[str, dict | None]] = []
        self.post_calls: list[tuple[str, dict | None]] = []
        self.put_calls: list[tuple[str, dict | None]] = []
        self.retry_calls: list[tuple[str, str, dict | None]] = []
        self.invalidations = 0

    def require_user(self):
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

    def get(self, path: str, params: dict | None = None, *, timeout=None):
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

    def post(self, path: str, json: dict | None = None, *, timeout=None):
        del timeout
        self.post_calls.append((path, json))
        if path == "/api/iresource/v1/work-platform/":
            return {"wpId": "wp-new"}
        return {"ok": True}

    def delete(self, path: str, *, timeout=None):
        del timeout
        return {"deleted": path}

    def put(self, path: str, json: dict | None = None, *, timeout=None):
        del timeout
        self.put_calls.append((path, json))
        return {"ok": True}

    def _request_with_retry(self, method: str, path: str, *, params=None, json=None, timeout=None):
        del params, timeout
        self.retry_calls.append((method, path, json))
        return {"ok": True}


def test_workplatform_dry_run_builds_default_payload() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]
    spec = WorkPlatformSpec(
        name="NotebookOne",
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
        cpu=2,
        memory_gb=8,
        ports=[8888],
        env={"MODE": "lab"},
    )

    result = api.create(spec, dry_run=True, idempotent=False)
    payload = result.payload

    assert result.entity is None
    assert payload["groupId"] == "group-dev"
    assert payload["ports"] == [{"port": 8888, "targetPort": 8888}]
    assert payload["env"] == [{"name": "MODE", "value": "lab"}]
    assert payload["volumes"][0]["nodeVolume"] == "/alice"
    assert payload["volumes"][0]["podVolume"] == "/alice"


def test_workplatform_create_idempotent_returns_existing_without_post() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]
    spec = WorkPlatformSpec(
        name="DevBoxOne",
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
    )

    result = api.create(spec)

    assert result.reused is True
    assert result.entity is not None
    assert result.entity.wp_id == "wp-1"
    assert client.post_calls == []


def test_workplatform_list_groups_cache_and_toggle_collect() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    groups_first = api.list_groups()
    groups_second = api.list_groups()
    toggled = api.toggle_history_collect("wp-1", True)

    assert groups_first[0].group_id == "group-dev"
    assert groups_second[0].group_name == "DEV-POOL"
    assert len([call for call in client.get_calls if call[0] == "/api/iresource/v1/node-group"]) == 1
    assert toggled.action == "toggle_history_collect"
    assert toggled.raw == {"ok": True}
    assert toggled.extras["collected"] is True
    assert client.put_calls == [
        (
            "/api/iresource/v1/work-platform/history-collect/",
            {"wpId": "wp-1", "isHistoryCollect": 1},
        )
    ]


def test_workplatform_history_uses_cache() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    first = api.list_history(page=1, page_size=50)
    second = api.list_history(page=1, page_size=50)

    assert len(first) == 0
    assert second == first
    assert len([call for call in client.get_calls if call[0] == "/api/iresource/v1/work-platform/history"]) == 1


def test_workplatform_list_prefers_history_and_filters_terminal_statuses() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]
    original_get = client.get

    def fake_get(path: str, params: dict | None = None, *, timeout=None):
        if path == "/api/iresource/v1/work-platform/history":
            page = (params or {}).get("page", 1)
            if page == 1:
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
                        },
                        {
                            "wpId": "wp-2",
                            "wpName": "OldBox",
                            "wpStatus": "Stopped",
                            "groupId": "group-dev",
                            "groupName": "DEV-POOL",
                            "image": "registry.example.invalid/ml/dev:latest",
                            "imageType": "INNER_IMAGE",
                            "frameWork": "other",
                        },
                    ]
                }
            return {"data": []}
        return original_get(path, params, timeout=timeout)

    client.get = fake_get  # type: ignore[method-assign]

    active = api.list()
    with_halted = api.list(include_halted=True, refresh=True)

    assert [item.wp_name for item in active] == ["DevBoxOne"]
    assert [item.wp_name for item in with_halted] == ["DevBoxOne", "OldBox"]


def test_workplatform_list_fallback_filters_non_workplatform_rows() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    def fake_get(path: str, params: dict | None = None, *, timeout=None):
        del timeout, params
        if path == "/api/iresource/v1/work-platform/history":
            return {"data": []}
        if path == "/api/iresource/v1/work-platform/goto-train-job":
            return {
                "data": [
                    {
                        "id": "task-1",
                        "name": "train-job",
                        "status": "Running",
                    },
                    {
                        "wpId": "wp-1",
                        "wpName": "DevBoxOne",
                        "wpStatus": "Running",
                        "groupId": "group-dev",
                        "groupName": "DEV-POOL",
                        "image": "registry.example.invalid/ml/dev:latest",
                        "imageType": "INNER_IMAGE",
                        "frameWork": "other",
                    },
                ]
            }
        return client.get(path)  # pragma: no cover

    client.get = fake_get  # type: ignore[method-assign]

    items = api.list()

    assert [item.wp_id for item in items] == ["wp-1"]


def test_workplatform_create_posts_and_fetches_detail() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]
    spec = WorkPlatformSpec(
        name="NotebookOne",
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
        command="sleep 3600",
    )

    result = api.create(spec, idempotent=False)

    assert result.created is True
    assert result.entity is not None
    assert result.entity.wp_id == "wp-new"
    assert client.post_calls[0][0] == "/api/iresource/v1/work-platform/"
    assert client.invalidations == 1


def test_workplatform_resolve_and_wait_ready(monkeypatch) -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "aistation.workplatform.wait_workplatform_ready",
        lambda client_, wp_id, timeout, interval: api.get(wp_id),
    )
    spec = WorkPlatformSpec(
        name="NotebookOne",
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
        command="sleep 3600",
    )

    resolved = api.resolve("DevBoxOne", search_history=False)
    waited = api.create_and_wait_ready(spec, idempotent=False, timeout=1.0, interval=0.0)

    assert resolved.wp_name == "DevBoxOne"
    assert waited.waited is True
    assert waited.entity is not None
    assert waited.entity.wp_id == "wp-new"


def test_workplatform_resolve_by_name_skips_eager_detail() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    resolved = api.resolve("DevBoxOne", search_history=False)

    assert resolved.wp_id == "wp-1"
    assert "/api/iresource/v1/work-platform/wp-1/detail" not in [path for path, _ in client.get_calls]


def test_workplatform_search_history_false_skips_history_requests() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    api.resolve("DevBoxOne", search_history=False)

    assert "/api/iresource/v1/work-platform/history" not in [path for path, _ in client.get_calls]


def test_workplatform_search_history_true_only_fetches_history_once() -> None:
    client = _DummyClient()
    original_get = client.get
    history_calls = {"count": 0}

    def fake_get(path: str, params: dict | None = None, *, timeout=None):
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
        return original_get(path, params, timeout=timeout)

    client.get = fake_get  # type: ignore[method-assign]
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    resolved = api.resolve("HistoryBox")

    assert resolved.wp_id == "wp-2"
    assert history_calls["count"] == 1


def test_workplatform_accepts_object_inputs_and_notebook_spec(monkeypatch) -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]
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
    dry_run = api.create(spec, dry_run=True, idempotent=False)
    deleted = api.delete(workplatform)
    rebuilt = api.rebuild_template(workplatform)
    jupyter = api.jupyter_url(workplatform)

    assert spec.name == "notebookfeedface"
    assert cloned.resource_group == "DEV-POOL"
    assert dry_run.payload["groupId"] == "group-dev"
    assert dry_run.payload["image"] == "registry.example.invalid/ml/dev:latest"
    assert deleted.target_id == "wp-1"
    assert rebuilt == {"data": []}
    assert jupyter == {"data": []}


def test_workplatform_create_retries_detail_lookup(monkeypatch) -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]
    spec = WorkPlatformSpec(
        name="NotebookOne",
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
        command="sleep 3600",
    )
    attempts = {"count": 0}
    original_get = client.get

    def fake_get(path: str, params: dict | None = None, *, timeout=None):
        if path == "/api/iresource/v1/work-platform/wp-new/detail":
            attempts["count"] += 1
            if attempts["count"] < 3:
                return {}
        return original_get(path, params, timeout=timeout)

    client.get = fake_get  # type: ignore[method-assign]
    monkeypatch.setattr("aistation._consistency.time.sleep", lambda _: None)

    result = api.create(spec, idempotent=False)

    assert result.entity is not None
    assert result.entity.wp_id == "wp-new"
    assert attempts["count"] == 3


def test_workplatform_create_raw_and_delete_and_commit_image() -> None:
    client = _DummyClient()
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    created = api.create_raw({"wpName": "RawNotebook"})
    deleted = api.delete("wp-new")
    committed = api.commit_image(
        "wp-new",
        image_name="my/myapp",
        image_tag="v1",
        pod_id="pod-1",
    )

    assert created.action == "create_raw"
    assert created.entity is not None
    assert created.entity.wp_id == "wp-new"
    assert deleted.action == "delete"
    assert deleted.target_id == "wp-new"
    assert committed.action == "commit_image"
    assert committed.extras["workplatform_id"] == "wp-new"


def test_workplatform_resolve_ambiguous() -> None:
    client = _DummyClient()
    original_get = client.get

    def fake_history(path: str, params: dict | None = None, *, timeout=None):
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
        return original_get(path, params, timeout=timeout)

    client.get = fake_history  # type: ignore[method-assign]
    api = WorkPlatformsAPI(client)  # type: ignore[arg-type]

    with pytest.raises(AmbiguousMatchError):
        api.resolve("SharedName")
