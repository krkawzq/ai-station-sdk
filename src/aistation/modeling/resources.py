from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._coerce import as_bool, as_int, as_str_list


@dataclass
class Node:
    node_id: str
    node_name: str
    node_ip: str
    group_id: str
    group_name: str
    card_type: str
    card_kind: str
    card_memory_gb: int
    cards_total: int
    cards_used: int
    cpu: int
    cpu_used: int
    memory_gb: int
    disk_gb: int
    switch_type: str
    status: str
    resource_status: str
    role: str
    task_count: int
    task_users: list[str]
    is_mig: bool
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def cards_free(self) -> int:
        return max(0, self.cards_total - self.cards_used)

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        return cls(
            node_id=str(d.get("nodeId", "")),
            node_name=str(d.get("nodeName", "")),
            node_ip=str(d.get("nodeIp", "")),
            group_id=str(d.get("groupId", "")),
            group_name=str(d.get("groupName", "")),
            card_type=str(d.get("cardType", "")),
            card_kind=str(d.get("cardKind", "")),
            card_memory_gb=as_int(d.get("acceleratorCardMemory")),
            cards_total=as_int(d.get("acceleratorCard")),
            cards_used=as_int(d.get("acceleratorCardUsage")),
            cpu=as_int(d.get("cpu")),
            cpu_used=as_int(d.get("cpuUsage")),
            memory_gb=as_int(d.get("memory")),
            disk_gb=as_int(d.get("disk")),
            switch_type=str(d.get("switchType", "")).lower(),
            status=str(d.get("nodeStatus", "")),
            resource_status=str(d.get("nodeResourceStatus", "")),
            role=str(d.get("nodeRole", "")),
            task_count=as_int(d.get("taskCount")),
            task_users=as_str_list(d.get("taskUser")),
            is_mig=as_bool(d.get("isMig")),
            raw=d,
        )


@dataclass
class ResourceGroup:
    group_id: str
    group_name: str
    card_type: str
    card_kind: str
    switch_type: str
    node_count: int = 0
    total_cards: int = 0
    used_cards: int = 0
    total_cpu: int = 0
    total_memory_gb: int = 0
    node_names: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def free_cards(self) -> int:
        return max(0, self.total_cards - self.used_cards)
