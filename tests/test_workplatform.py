from __future__ import annotations

from aistation.specs import WorkPlatformSpec
from aistation.workplatform import WorkPlatformsAPI

from .helpers import make_user


class _DummyClient:
    def __init__(self) -> None:
        self.user = make_user()
        self.get_calls: list[tuple[str, dict | None]] = []
        self.post_calls: list[tuple[str, dict | None]] = []
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

    payload = api.create(spec, dry_run=True, idempotent=False)

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

    assert result.wp_id == "wp-1"
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
    assert toggled == {"ok": True}
    assert client.retry_calls == [
        (
            "PUT",
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

    assert result.wp_id == "wp-new"
    assert client.post_calls[0][0] == "/api/iresource/v1/work-platform/"
    assert client.invalidations == 1
