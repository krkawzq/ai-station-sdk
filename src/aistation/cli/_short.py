"""Short JSON payload helpers for AI-friendly CLI output."""
from __future__ import annotations

import json
from typing import Any

from ..config import Config
from ..modeling import Image, Node, Pod, ResourceGroup, Task, WorkPlatform


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _task_cards(task: Task) -> int:
    try:
        config = json.loads(task.config) if task.config else {}
    except json.JSONDecodeError:
        config = {}
    worker = config.get("worker", {}) if isinstance(config, dict) else {}
    return _to_int(worker.get("acceleratorCardNum", 0))


def group(group_: ResourceGroup) -> dict[str, Any]:
    return {
        "group_id": group_.group_id,
        "group_name": group_.group_name,
        "free_cards": group_.free_cards,
        "used_cards": group_.used_cards,
        "total_cards": group_.total_cards,
        "card_type": group_.card_type or group_.card_kind,
        "card_kind": group_.card_kind,
        "node_count": group_.node_count,
    }


def node(node_: Node) -> dict[str, Any]:
    return {
        "node_id": node_.node_id,
        "node_name": node_.node_name,
        "node_ip": node_.node_ip,
        "group_id": node_.group_id,
        "group_name": node_.group_name,
        "cards_free": node_.cards_free,
        "cards_used": node_.cards_used,
        "cards_total": node_.cards_total,
        "card_type": node_.card_type or node_.card_kind,
        "status": node_.status,
        "cpu_used": node_.cpu_used,
        "cpu": node_.cpu,
        "memory_gb": node_.memory_gb,
    }


def image(image_: Image) -> dict[str, Any]:
    return {
        "id": image_.id,
        "name": image_.name,
        "tag": image_.tag,
        "full_ref": image_.full_ref,
        "image_type": image_.image_type,
        "share": image_.share,
        "pull_count": image_.pull_count,
        "owner": image_.owner,
        "update_time": image_.update_time,
        "size_bytes": image_.size_bytes,
    }


def task(task_: Task) -> dict[str, Any]:
    return {
        "id": task_.id,
        "name": task_.name,
        "status": task_.status,
        "resource_group_id": task_.resource_group_id,
        "resource_group_name": task_.resource_group_name,
        "node_name": task_.node_name or None,
        "image": task_.image,
        "image_type": task_.image_type,
        "cards": _task_cards(task_),
        "create_time_ms": task_.create_time_ms,
        "run_time_s": task_.run_time_s,
        "status_reason": task_.status_reason or None,
    }


def pod(pod_: Pod) -> dict[str, Any]:
    return {
        "pod_id": pod_.pod_id,
        "pod_name": pod_.pod_name,
        "pod_name_changed": pod_.pod_name_changed,
        "pod_status": pod_.pod_status,
        "node_name": pod_.node_name,
        "node_ip": pod_.node_ip,
        "pod_gpu_type": pod_.pod_gpu_type,
        "external_urls": pod_.external_urls,
        "restart_count": pod_.restart_count,
    }


def workplatform(env: WorkPlatform) -> dict[str, Any]:
    return {
        "wp_id": env.wp_id,
        "wp_name": env.wp_name,
        "wp_status": env.wp_status,
        "group_id": env.group_id,
        "group_name": env.group_name,
        "image": env.image,
        "image_type": env.image_type,
        "frame_work": env.frame_work,
        "cpu": env.cpu,
        "memory_gb": env.memory_gb,
        "cards": env.cards,
        "card_kind": env.card_kind,
        "create_time": env.create_time,
    }


def config(config_: Config) -> dict[str, Any]:
    return {
        "default_timeout": config_.default_timeout,
        "verify_ssl": config_.verify_ssl,
        "image_registry_prefix": config_.image_registry_prefix,
        "default_project_id": config_.default_project_id,
        "max_retries": config_.max_retries,
        "token_ttl_hours": config_.token_ttl_hours,
    }
