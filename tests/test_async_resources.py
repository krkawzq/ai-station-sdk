from __future__ import annotations

import pytest

from aistation.aio.resources import AsyncGroupsAPI, AsyncNodesAPI
from aistation.modeling import Node


class _DummyNodes:
    def __init__(self, nodes: list[Node]) -> None:
        self._nodes = nodes

    async def list(self, *, refresh: bool = False) -> list[Node]:
        del refresh
        return self._nodes


class _DummyClient:
    def __init__(self, nodes: list[Node], payloads: list[dict] | None = None) -> None:
        self.nodes = _DummyNodes(nodes)
        self.payloads = payloads or []
        self.calls: list[tuple[str, dict | None]] = []

    async def list_all(self, path: str, *, params=None):
        self.calls.append((path, params))
        return list(self.payloads)


@pytest.mark.asyncio
async def test_async_groups_are_aggregated_from_nodes(load_json_fixture) -> None:
    data = load_json_fixture("node_list_page1.json")["resData"]["data"]
    nodes = [Node.from_api(item) for item in data]
    api = AsyncGroupsAPI(_DummyClient(nodes))  # type: ignore[arg-type]

    groups = await api.list()
    matched = await api.resolve_many("POOL-A")

    assert [group.group_name for group in groups] == ["GPU-POOL-A", "GPU-POOL-B"]
    assert await api.resolve_id("GPU-POOL-A") == "group-gpu-a"
    assert matched[0].group_id == "group-gpu-a"
    group = await api.by_name("GPU-POOL-A")
    assert group is not None
    assert group.total_cards == 16
    assert group.used_cards == 3
    assert group.free_cards == 13


@pytest.mark.asyncio
async def test_async_nodes_api_caches_by_query_args(load_json_fixture) -> None:
    payloads = load_json_fixture("node_list_page1.json")["resData"]["data"]
    client = _DummyClient([], payloads=payloads)
    api = AsyncNodesAPI(client)  # type: ignore[arg-type]

    first = await api.list()
    second = await api.list()
    by_group = await api.list(group_id="group-gpu-a")
    without_usage = await api.list(with_usage=False)
    api.invalidate_cache()
    refreshed = await api.list(refresh=True)

    assert len(first) == 3
    assert second is first
    assert len(by_group) == 3
    assert len(without_usage) == 3
    assert len(refreshed) == 3
    assert client.calls == [
        ("/api/iresource/v1/node", {"getUsage": 1}),
        ("/api/iresource/v1/node", {"groupId": "group-gpu-a", "getUsage": 1}),
        ("/api/iresource/v1/node", {}),
        ("/api/iresource/v1/node", {"getUsage": 1}),
    ]
