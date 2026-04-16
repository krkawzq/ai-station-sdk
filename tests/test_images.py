from __future__ import annotations

from aistation.images import ImagesAPI


class _DummyClient:
    def __init__(self, image_page: dict, image_types: list[dict]) -> None:
        self._image_page = image_page
        self._image_types = image_types
        self.list_calls = 0
        self.type_calls = 0
        self.post_calls: list[tuple[str, dict]] = []

    def list_all(self, path: str):
        assert path == "/api/iresource/v1/images/all"
        self.list_calls += 1
        for item in self._image_page["resData"]["data"]:
            yield item

    def get(self, path: str, params=None):
        if path == "/api/iresource/v1/image-type":
            self.type_calls += 1
            return self._image_types
        assert path == "/api/iresource/v1/images/progress"
        return {"id": params["id"], "progress": 50}

    def post(self, path: str, json: dict):
        self.post_calls.append((path, json))
        return {"path": path, "body": json}


def test_images_list_filter_resolve_and_cache(load_json_fixture) -> None:
    page = load_json_fixture("images_list_page1.json")
    image_types = [
        {"id": "1", "name": "pytorch"},
        {"id": "2", "name": "tensorflow"}
    ]
    client = _DummyClient(page, image_types)
    api = ImagesAPI(client)

    public_pytorch = api.list(share=2, image_type="pytorch")
    again = api.list()
    refreshed = api.list(refresh=True)
    resolved = api.resolve("ml/pytorch:latest")
    types = api.types()

    assert len(public_pytorch) == 1
    assert len(again) == 3
    assert len(refreshed) == 3
    assert public_pytorch[0].owner == "system-user"
    assert resolved.tag == "latest"
    assert [item.name for item in types] == ["pytorch", "tensorflow"]
    assert client.list_calls == 2
    assert client.type_calls == 1


def test_images_mutation_helpers(load_json_fixture) -> None:
    page = load_json_fixture("images_list_page1.json")
    client = _DummyClient(page, [])
    api = ImagesAPI(client)

    api.list()
    checked = api.check("registry.example.invalid/ml/pytorch", "latest")
    imported = api.import_external(
        image_name="docker.io/library/python",
        image_tag="3.12",
        image_type="other",
        share=1,
        comment="synthetic",
    )
    progress = api.progress("import-1")
    api.list()
    api.list()

    assert checked["path"] == "/api/iresource/v1/images/check"
    assert imported["body"]["imageName"] == "docker.io/library/python"
    assert progress == {"id": "import-1", "progress": 50}
    assert client.list_calls == 2
