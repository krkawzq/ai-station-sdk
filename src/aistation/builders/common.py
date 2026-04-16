from __future__ import annotations

from typing import Any


def build_env_entries(env: dict[str, str] | None) -> list[dict[str, str]] | None:
    if not env:
        return None
    return [{"name": key, "value": value} for key, value in env.items()]


def build_port_pairs(ports: list[int]) -> list[dict[str, int]] | None:
    if not ports:
        return None
    return [{"port": port, "targetPort": port} for port in ports]


def normalize_task_model(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "modelId": model.get("id") or model.get("modelId") or "",
        "name": model.get("name") or model.get("modelName") or "",
        "version": model.get("version") or "",
        "mountPath": model.get("mountPath") or model.get("mount_path") or "",
    }


def resolve_image_ref(image_ref: str, registry_prefix: str) -> str:
    ref = image_ref.strip()
    if ref.count("/") >= 2 and ":" in ref.rsplit("/", 1)[-1]:
        return ref
    prefix = registry_prefix.rstrip("/")
    return f"{prefix}/{ref.lstrip('/')}"


def infer_image_type(image_full: str) -> str:
    ref = image_full.lower()
    for image_type in ("pytorch", "tensorflow", "paddlepaddle", "caffe", "mxnet"):
        if image_type in ref:
            return image_type
    return "other"
