"""TaskSpec factory functions for common scenarios.

Each preset returns a fully-populated :class:`TaskSpec` ready to submit.
Callers can still mutate fields afterward (dataclasses are mutable).

Rationale: the raw TaskSpec has 20+ fields. Most users only care about
resource_group / image / cards / command. Presets hide the rest with
sensible, validated defaults.
"""
from __future__ import annotations

import uuid
from typing import Any

from .specs import TaskSpec


def _auto_name(prefix: str) -> str:
    """Generate a server-legal task name (alphanumeric only)."""
    suffix = uuid.uuid4().hex[:8]
    safe_prefix = "".join(c for c in prefix if c.isalnum()) or "task"
    return f"{safe_prefix}{suffix}"


def gpu_hold(
    *,
    resource_group: str,
    cards: int = 1,
    cpu: int = 8,
    memory_gb: int = 16,
    image: str = "pytorch/pytorch:21.10-py3",
    mount_path: str | None = None,
    name_prefix: str = "hold",
    hours: int | None = None,
    command: str | None = None,
) -> TaskSpec:
    """Single-node GPU "占卡" task.

    Ideal for interactive development / holding resources when cluster is tight.
    By default runs ``sleep infinity`` until you manually delete it. Pass
    ``hours`` to bound the hold, or provide ``command`` for a custom script.

    Example::

        spec = presets.gpu_hold(resource_group="8A100_80", cards=2, hours=4)
        task = client.tasks.create(spec).entity
    """
    if command is None:
        if hours is not None and hours > 0:
            command = f"sleep {hours * 3600}"
        else:
            command = "sleep infinity"
    return TaskSpec(
        name=_auto_name(name_prefix),
        resource_group=resource_group,
        image=image,
        command=command,
        cards=cards,
        cpu=cpu,
        memory_gb=memory_gb,
        card_kind="GPU",
        shm_size=min(4, memory_gb // 2) if memory_gb > 0 else 1,
        mount_path=mount_path or "",   # let SDK pick /{account}/...
        exec_dir="",
        raw_overrides={"execDir": ""},
    )


def cpu_debug(
    *,
    resource_group: str = "CPU",
    cpu: int = 1,
    memory_gb: int = 4,
    image: str = "pytorch/pytorch:21.10-py3",
    command: str = "sleep 60",
    name_prefix: str = "cpudbg",
    mount_suffix: str = "debug",
) -> TaskSpec:
    """Small CPU-only task, good for smoke-testing the SDK against the server
    without consuming GPU resources.
    """
    # CPU group refuses mount_path == account name; mount_suffix is a hint
    # for the Skill layer to post-process (SDK itself leaves mount_path empty
    # so tasks._build_payload falls through to /{account}).
    _ = mount_suffix  # accepted for API stability; not currently wired
    return TaskSpec(
        name=_auto_name(name_prefix),
        resource_group=resource_group,
        image=image,
        command=command,
        cards=0,
        cpu=cpu,
        memory_gb=memory_gb,
        card_kind="CPU",
        shm_size=min(1, memory_gb // 2) if memory_gb >= 2 else 1,
        mount_path="",
        exec_dir="",
        raw_overrides={"execDir": ""},
    )


def pytorch_train(
    *,
    resource_group: str,
    image: str,
    command: str,
    cards: int = 1,
    cpu: int = 16,
    memory_gb: int = 32,
    ports: list[int] | None = None,
    name_prefix: str = "train",
    distributed: str = "node",
    env: dict[str, str] | None = None,
    mount_path: str | None = None,
) -> TaskSpec:
    """Full pytorch training spec with sane defaults.

    For distributed jobs set ``distributed`` to one of
    ``mpi`` / ``ps_worker`` / ``master_worker`` / ``server_worker``.
    """
    return TaskSpec(
        name=_auto_name(name_prefix),
        resource_group=resource_group,
        image=image,
        command=command,
        cards=cards,
        cpu=cpu,
        memory_gb=memory_gb,
        card_kind="GPU",
        shm_size=min(8, memory_gb // 4) if memory_gb > 0 else 1,
        ports=list(ports or []),
        env=dict(env or {}),
        image_type="pytorch",
        distributed=distributed,
        mount_path=mount_path or "",
        exec_dir="",
        raw_overrides={"execDir": ""},
    )


def from_existing(task: Any, *, name_prefix: str = "clone") -> TaskSpec:
    """Derive a TaskSpec from an existing :class:`Task` object (reverse-engineer).

    Useful for cloning a known-good task with small modifications::

        existing = client.tasks.get("GFM")
        spec = presets.from_existing(existing)
        spec.command = "bash new_script.sh"
        client.tasks.create(spec).entity
    """
    import json as _json
    try:
        cfg = _json.loads(task.config) if isinstance(task.config, str) and task.config else {}
    except _json.JSONDecodeError:
        cfg = {}
    worker = cfg.get("worker", {}) if isinstance(cfg, dict) else {}

    ports_raw = task.ports
    if isinstance(ports_raw, str):
        ports = [int(p) for p in ports_raw.split(",") if p.strip().isdigit()]
    elif isinstance(ports_raw, list):
        ports = [int(p) for p in ports_raw if isinstance(p, (int, str)) and str(p).isdigit()]
    else:
        ports = []

    return TaskSpec(
        name=_auto_name(name_prefix),
        resource_group=task.resource_group_name or task.resource_group_id,
        image=task.image,
        command=task.command or "",
        cards=int(worker.get("acceleratorCardNum", 0) or 0),
        cpu=int(worker.get("cpuNum", 0) or 0),
        memory_gb=int(worker.get("memory", 0) or 0),
        nodes=int(worker.get("nodeNum", 1) or 1),
        card_kind="GPU" if int(worker.get("acceleratorCardNum", 0) or 0) > 0 else "CPU",
        shm_size=int(task.shm_size or 1),
        mount_path=task.mount_dir or "",
        script_dir=task.script_dir or "",
        log_path=task.log_out or "",
        ports=ports,
        switch_type=task.switch_type or "ib",
        image_type=task.image_type or "other",
        image_flag=int(task.image_flag or 0),
        distributed="mpi" if task.mpi_flag else ("node" if not task.dist_flag else "master_worker"),
        is_elastic=bool(task.is_elastic),
        emergency=bool(task.emergency_flag),
        start_script=task.start_script or "",
        exec_dir=task.exec_dir or "",
        raw_overrides={"execDir": task.exec_dir or ""},
    )
