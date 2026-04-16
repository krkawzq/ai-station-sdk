from __future__ import annotations

import pytest

from aistation.aio.images import AsyncImagesAPI


class _DummyClient:
    def __init__(self, image_page: dict, image_types: list[dict]) -> None:
        self._image_page = image_page
        self._image_types = image_types
        self.list_calls = 0
        self.type_calls = 0
        self.post_calls: list[tuple[str, dict]] = []

    async def list_all(self, path: str):
        assert path == "/api/iresource/v1/images/all"
        self.list_calls += 1
        return [item for item in self._image_page["resData"]["data"]]

    async def get(self, path: str, params=None):
        if path == "/api/iresource/v1/image-type":
            self.type_calls += 1
            return self._image_types
        assert path == "/api/iresource/v1/images/progress"
        return {"id": params["id"], "progress": 50}

    async def post(self, path: str, json: dict):
        self.post_calls.append((path, json))
        return {"path": path, "body": json}


@pytest.mark.asyncio
async def test_async_images_list_filter_resolve_and_cache(load_json_fixture) -> None:
    page = load_json_fixture("images_list_page1.json")
    image_types = [
        {"id": "1", "name": "pytorch"},
        {"id": "2", "name": "tensorflow"},
    ]
    client = _DummyClient(page, image_types)
    api = AsyncImagesAPI(client)  # type: ignore[arg-type]

    public_pytorch = await api.list(share=2, image_type="pytorch")
    again = await api.list()
    refreshed = await api.list(refresh=True)
    resolved = await api.resolve("ml/pytorch:latest")
    matched = await api.resolve_many("pytorch")
    types = await api.types()

    assert len(public_pytorch) == 1
    assert len(again) == 3
    assert len(refreshed) == 3
    assert public_pytorch[0].owner == "system-user"
    assert resolved.tag == "latest"
    assert matched[0].tag == "latest"
    assert [item.name for item in types] == ["pytorch", "tensorflow"]
    assert client.list_calls == 2
    assert client.type_calls == 1


@pytest.mark.asyncio
async def test_async_images_mutation_helpers(load_json_fixture) -> None:
    page = load_json_fixture("images_list_page1.json")
    client = _DummyClient(page, [])
    api = AsyncImagesAPI(client)  # type: ignore[arg-type]

    await api.list()
    checked = await api.check("registry.example.invalid/ml/pytorch", "latest")
    imported = await api.import_external(
        image_name="docker.io/library/python",
        image_tag="3.12",
        image_type="other",
        share=1,
        comment="synthetic",
    )
    progress = await api.progress("import-1")
    await api.list()
    await api.list()

    assert checked.action == "check"
    assert checked.raw["path"] == "/api/iresource/v1/images/check"
    assert imported.action == "import_external"
    assert imported.raw["body"]["imageName"] == "docker.io/library/python"
    assert progress == {"id": "import-1", "progress": 50}
    assert client.list_calls == 2
