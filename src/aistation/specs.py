from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskSpec:
    name: str
    resource_group: str
    image: str
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


@dataclass
class WorkPlatformSpec:
    name: str
    resource_group: str
    image: str
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
