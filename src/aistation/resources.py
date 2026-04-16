from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from ._resolve import resolve_many as _resolve_many
from ._resolve import resolve_one as _resolve_one
from .cache import TTLCache
from .modeling.resources import Node, ResourceGroup

if TYPE_CHECKING:
    from .client import AiStationClient


class NodesAPI:
    """Node listing with short TTL cache (occupancy changes fast, but not per-second)."""

    def __init__(self, client: AiStationClient) -> None:
        self._c = client
        self._cache: TTLCache[list[Node]] = TTLCache(ttl=30.0)

    def list(
        self,
        *,
        group_id: str | None = None,
        with_usage: bool = True,
        refresh: bool = False,
    ) -> list[Node]:
        """List nodes in a single fast-path request.

        ``with_usage=True`` (default) sends ``getUsage=1`` to reveal real
        ``acceleratorCardUsage`` and live ``cardType``. Without it the server
        returns stale values (usage always 0) even for a normal user.

        Cached with a 30s TTL; pass ``refresh=True`` to bypass the cache.
        Cache is keyed per (group_id, with_usage) — if you change args you
        get a fresh fetch.
        """
        cache_key = (group_id, with_usage)
        if not refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        params: dict[str, Any] = {}
        if group_id:
            params["groupId"] = group_id
        if with_usage:
            params["getUsage"] = 1
        nodes = [
            Node.from_api(item)
            for item in self._c.list_all("/api/iresource/v1/node", params=params)
        ]
        self._cache.set(nodes, cache_key)
        return nodes

    def invalidate_cache(self) -> None:
        """Drop the cached node list."""
        self._cache.invalidate()

    def get(self, node_id: str) -> Node:
        data = self._c.get(f"/api/iresource/v1/node/{node_id}")
        if not isinstance(data, dict):
            raise ValueError(f"unexpected node payload for {node_id}")
        return Node.from_api(data)


class GroupsAPI:
    """Resource groups are aggregated from node listings.

    Group identity (id, name, cardType, switchType) is stable; only
    ``free_cards`` / ``used_cards`` fluctuate. Share the nodes cache with
    :class:`NodesAPI`.
    """

    def __init__(self, client: AiStationClient) -> None:
        self._c = client

    def list(self, *, refresh: bool = False) -> list[ResourceGroup]:
        return self._aggregate(self._c.nodes.list(refresh=refresh))

    def by_name(self, name: str) -> ResourceGroup | None:
        for group in self.list():
            if group.group_name == name:
                return group
        return None

    def resolve_many(self, query: str) -> list[ResourceGroup]:
        return _resolve_many(
            query,
            self.list(),
            key_fns=(
                lambda item: item.group_id,
                lambda item: item.group_name,
            ),
        )

    def resolve(self, name_or_id: str) -> ResourceGroup:
        return _resolve_one(
            name_or_id,
            self.list(),
            key_fns=(
                lambda item: item.group_id,
                lambda item: item.group_name,
            ),
            label_fn=lambda item: f"{item.group_name} ({item.group_id})",
            resource_type="resource group",
        )

    def resolve_id(self, name_or_id: str) -> str:
        return self.resolve(name_or_id).group_id

    @staticmethod
    def _aggregate(nodes: builtins.list[Node]) -> builtins.list[ResourceGroup]:
        groups: dict[str, ResourceGroup] = {}
        for node in nodes:
            group = groups.get(node.group_id)
            if group is None:
                group = ResourceGroup(
                    group_id=node.group_id,
                    group_name=node.group_name,
                    card_type=node.card_type,
                    card_kind=node.card_kind,
                    switch_type=node.switch_type,
                )
                groups[node.group_id] = group
            group.node_count += 1
            group.total_cards += node.cards_total
            group.used_cards += node.cards_used
            group.total_cpu += node.cpu
            group.total_memory_gb += node.memory_gb
            group.node_names.append(node.node_name)
        return sorted(groups.values(), key=lambda item: item.group_name)
