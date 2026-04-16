from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._coerce import as_int


@dataclass
class WorkPlatform:
    wp_id: str
    wp_name: str
    wp_status: str
    group_id: str
    group_name: str
    image: str
    image_type: str
    frame_work: str
    cpu: int
    memory_gb: int
    cards: int
    card_kind: str
    card_type: str
    card_memory_gb: int
    shm_size: int
    command: str
    pod_num: int
    user_id: str
    create_time: str
    env: list[dict[str, Any]] | None = None
    models: list[dict[str, Any]] = field(default_factory=list)
    volumes: list[dict[str, Any]] = field(default_factory=list)
    mig_num: int | None = None
    mig_type: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        vols = d.get("workPlatformPodVolumes") or d.get("volumes") or []
        return cls(
            wp_id=str(d.get("wpId", "")),
            wp_name=str(d.get("wpName", "")),
            wp_status=str(d.get("wpStatus", "")),
            group_id=str(d.get("groupId", "")),
            group_name=str(d.get("groupName", "")),
            image=str(d.get("image", "")),
            image_type=str(d.get("imageType", "")),
            frame_work=str(d.get("frameWork", "")),
            cpu=as_int(d.get("cpu")),
            memory_gb=as_int(d.get("memory")),
            cards=as_int(d.get("acceleratorCard")),
            card_kind=str(d.get("acceleratorCardKind", "")),
            card_type=str(d.get("acceleratorCardType", "")),
            card_memory_gb=as_int(d.get("acceleratorCardMemory")),
            shm_size=as_int(d.get("shmSize"), 0),
            command=str(d.get("command", "")),
            pod_num=as_int(d.get("wpPodNum"), 1),
            user_id=str(d.get("userId") or d.get("wpOwnerId") or ""),
            create_time=str(d.get("createDateTime") or d.get("dateTime") or ""),
            env=d.get("env"),
            models=d.get("models") or [],
            volumes=[v for v in vols if isinstance(v, dict)],
            mig_num=as_int(d["migNum"]) if d.get("migNum") is not None else None,
            mig_type=as_int(d["migType"]) if d.get("migType") is not None else None,
            raw=d,
        )
