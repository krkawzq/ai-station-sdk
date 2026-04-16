from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .modeling.images import Image
    from .modeling.resources import ResourceGroup
    from .modeling.tasks import Task
    from .modeling.workplatforms import WorkPlatform


def _auto_name(prefix: str, *, default: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    safe_prefix = "".join(char for char in prefix if char.isalnum()) or default
    return f"{safe_prefix}{suffix}"


@dataclass
class TaskSpec:
    name: str
    resource_group: str | ResourceGroup
    image: str | Image
    command: str
    cards: int = 1
    cpu: int = 4
    memory_gb: int = 0
    nodes: int = 1
    card_kind: str = "GPU"
    mount_path: str = ""
    script_dir: str = ""
    log_path: str = ""
    datasets: list[dict[str, Any]] = field(default_factory=list)
    models: list[dict[str, Any]] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    shm_size: int = 4
    switch_type: str = "ib"
    image_type: str = ""
    image_flag: int = 0
    is_elastic: bool = False
    distributed: str = "node"
    emergency: bool = False
    description: str = ""
    start_script: str = ""
    exec_dir: str = ""
    parameters: str = ""
    node_names: list[str] = field(default_factory=list)
    mount_path_model: int = 2
    log_storage_name: str = "master"
    task_type: int = 1
    min_nodes: int = -1
    raw_overrides: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def gpu_hold(cls, **kwargs: Any) -> TaskSpec:
        from . import presets

        return presets.gpu_hold(**kwargs)

    @classmethod
    def cpu_debug(cls, **kwargs: Any) -> TaskSpec:
        from . import presets

        return presets.cpu_debug(**kwargs)

    @classmethod
    def pytorch_train(cls, **kwargs: Any) -> TaskSpec:
        from . import presets

        return presets.pytorch_train(**kwargs)

    @classmethod
    def from_existing(cls, task: Task, **kwargs: Any) -> TaskSpec:
        from . import presets

        return presets.from_existing(task, **kwargs)


@dataclass
class WorkPlatformSpec:
    name: str
    resource_group: str | ResourceGroup
    image: str | Image
    command: str = "sleep 3600"
    cards: int = 0
    cpu: int = 1
    memory_gb: int = 0
    card_kind: str = "CPU"
    pod_num: int = 1
    shm_size: int = 1
    frame_work: str = "other"
    image_type: str = "INNER_IMAGE"
    ports: list[int] = field(default_factory=list)
    env: dict[str, str] | None = None
    volumes: list[dict[str, Any]] = field(default_factory=list)
    models: list[dict[str, Any]] = field(default_factory=list)
    switch_type: str = "ib"
    wp_type: str = "COMMON_WP"
    node_list: list[str] = field(default_factory=list)
    raw_overrides: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def notebook(
        cls,
        *,
        resource_group: str | ResourceGroup,
        image: str | Image,
        name: str | None = None,
        name_prefix: str = "notebook",
        cards: int = 0,
        cpu: int = 2,
        memory_gb: int = 8,
        command: str = "sleep infinity",
        ports: list[int] | None = None,
        env: dict[str, str] | None = None,
        card_kind: str | None = None,
        frame_work: str = "other",
        image_type: str = "INNER_IMAGE",
        shm_size: int = 1,
        pod_num: int = 1,
        switch_type: str = "ib",
    ) -> WorkPlatformSpec:
        resolved_name = name or _auto_name(name_prefix, default="notebook")
        resolved_card_kind = card_kind or ("GPU" if cards > 0 else "CPU")
        return cls(
            name=resolved_name,
            resource_group=resource_group,
            image=image,
            command=command,
            cards=cards,
            cpu=cpu,
            memory_gb=memory_gb,
            card_kind=resolved_card_kind,
            pod_num=pod_num,
            shm_size=shm_size,
            frame_work=frame_work,
            image_type=image_type,
            ports=list(ports or []),
            env=dict(env or {}),
            switch_type=switch_type,
        )

    @classmethod
    def from_existing(
        cls,
        workplatform: WorkPlatform,
        *,
        name: str | None = None,
        name_prefix: str = "clone",
    ) -> WorkPlatformSpec:
        resolved_name = name or _auto_name(name_prefix, default="clone")
        return cls(
            name=resolved_name,
            resource_group=workplatform.group_name or workplatform.group_id,
            image=workplatform.image,
            command=workplatform.command or "sleep infinity",
            cards=workplatform.cards,
            cpu=workplatform.cpu,
            memory_gb=workplatform.memory_gb,
            card_kind=workplatform.card_kind or ("GPU" if workplatform.cards > 0 else "CPU"),
            pod_num=workplatform.pod_num or 1,
            shm_size=workplatform.shm_size or 1,
            frame_work=workplatform.frame_work or "other",
            image_type=workplatform.image_type or "INNER_IMAGE",
            env={
                str(item.get("name", "")): str(item.get("value", ""))
                for item in (workplatform.env or [])
                if isinstance(item, dict) and item.get("name")
            },
            volumes=list(workplatform.volumes),
            models=list(workplatform.models),
            raw_overrides={},
        )
