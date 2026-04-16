from __future__ import annotations

import builtins
import json
from typing import Any

from ..modeling.tasks import JobVolume
from ..specs import TaskSpec
from .common import build_env_entries, infer_image_type, normalize_task_model, resolve_image_ref


def build_task_payload(
    spec: TaskSpec,
    *,
    account: str,
    project_id: str,
    group_id: str,
    image_registry_prefix: str,
) -> dict[str, Any]:
    image_full = resolve_image_ref(spec.image, image_registry_prefix)
    image_type = spec.image_type or infer_image_type(image_full)
    mount_dir = spec.mount_path or f"/{account}"
    exec_dir = spec.exec_dir or spec.script_dir or mount_dir
    payload: dict[str, Any] = {
        "name": spec.name,
        "description": spec.description,
        "projectId": project_id,
        "imageType": image_type,
        "resGroupId": group_id,
        "image": image_full,
        "mountDir": mount_dir,
        "startScript": spec.start_script,
        "data": "",
        "logOut": spec.log_path,
        "distFlag": spec.distributed not in {"", "node"},
        "enUpdateDataSet": 0,
        "ports": ",".join(str(port) for port in spec.ports),
        "param": spec.parameters,
        "execDir": exec_dir,
        "nodeName": ",".join(spec.node_names) if spec.node_names else None,
        "mpiFlag": spec.distributed == "mpi",
        "type": "mpi" if spec.distributed == "mpi" else image_type,
        "shmSize": spec.shm_size,
        "emergencyFlag": spec.emergency,
        "imageFlag": spec.image_flag,
        "switchType": spec.switch_type or None,
        "isElastic": spec.is_elastic,
        "env": build_env_entries(spec.env),
        "acceleratorCardKind": spec.card_kind,
        "models": [normalize_task_model(model) for model in spec.models] or None,
        "config": json.dumps(build_task_config(spec), ensure_ascii=False, separators=(",", ":")),
        "command": spec.command,
        "commandScriptList": list(spec.raw_overrides.get("commandScriptList", [])),
        "jobVolume": [volume.to_api() for volume in build_task_job_volumes(spec, account)],
        "taskType": spec.task_type,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    payload.update(spec.raw_overrides)
    return payload


def build_task_config(spec: TaskSpec) -> dict[str, Any]:
    worker = {
        "nodeNum": spec.nodes,
        "cpuNum": spec.cpu,
        "acceleratorCardNum": spec.cards,
        "memory": spec.memory_gb,
        "minNodeNum": spec.min_nodes if spec.is_elastic else -1,
    }
    config: dict[str, Any] = {"worker": worker}
    if spec.distributed == "ps_worker":
        config["ps"] = _deployment_block("ps", spec, default_cards=0)
    elif spec.distributed == "master_worker":
        config["master"] = _deployment_block("master", spec, default_cards=spec.cards)
    elif spec.distributed == "server_worker":
        config["server"] = _deployment_block("server", spec, default_cards=0)
    return config


def build_task_job_volumes(spec: TaskSpec, account: str) -> builtins.list[JobVolume]:
    volumes: builtins.list[JobVolume] = []
    for dataset in spec.datasets:
        volumes.append(
            JobVolume(
                file_model=int(dataset.get("file_model", dataset.get("volumeType", 1))),
                function_model=int(dataset.get("function_model", 1)),
                volume_mount=str(dataset.get("volume_mount", dataset.get("volumeMount", ""))),
                storage_name=str(dataset.get("storage_name", dataset.get("storageName", "master"))),
                bucket=str(dataset.get("bucket", "")),
                origin_path=(
                    str(dataset["origin_path"])
                    if dataset.get("origin_path") is not None
                    else (str(dataset["originPath"]) if dataset.get("originPath") is not None else None)
                ),
                dataset_cache_type=(
                    str(dataset["dataset_cache_type"])
                    if dataset.get("dataset_cache_type") is not None
                    else (
                        str(dataset["datasetCacheType"])
                        if dataset.get("datasetCacheType") is not None
                        else None
                    )
                ),
                file_type=(
                    str(dataset["file_type"])
                    if dataset.get("file_type") is not None
                    else (str(dataset["fileType"]) if dataset.get("fileType") is not None else None)
                ),
                is_unzip=bool(dataset.get("is_unzip", dataset.get("isUnzip", False))),
                volume_mount_alias=(
                    str(dataset["volume_mount_alias"])
                    if dataset.get("volume_mount_alias") is not None
                    else (
                        str(dataset["volumeMountAlias"])
                        if dataset.get("volumeMountAlias") is not None
                        else None
                    )
                ),
                storage_type=(
                    str(dataset["storage_type"])
                    if dataset.get("storage_type") is not None
                    else (
                        str(dataset["storageType"])
                        if dataset.get("storageType") is not None
                        else None
                    )
                ),
            )
        )

    volumes.append(
        JobVolume(
            file_model=spec.mount_path_model,
            function_model=2,
            volume_mount=spec.mount_path or f"/{account}",
            storage_name="master",
            bucket="",
        )
    )

    if spec.log_path:
        volumes.append(
            JobVolume(
                file_model=2,
                function_model=3,
                volume_mount=spec.log_path,
                storage_name=spec.log_storage_name,
                bucket="",
            )
        )
    return volumes


def _deployment_block(prefix: str, spec: TaskSpec, *, default_cards: int) -> dict[str, int]:
    return {
        "nodeNum": int(_override(spec, f"{prefix}_nodes", f"{prefix}NodeNum", default=1)),
        "cpuNum": int(_override(spec, f"{prefix}_cpu", f"{prefix}CpuNum", default=spec.cpu)),
        "acceleratorCardNum": int(
            _override(
                spec,
                f"{prefix}_cards",
                f"{prefix}AcceleratorCardNum",
                default=default_cards,
            )
        ),
        "memory": int(_override(spec, f"{prefix}_memory", f"{prefix}Memory", default=spec.memory_gb)),
    }


def _override(spec: TaskSpec, *keys: str, default: Any) -> Any:
    for key in keys:
        if key in spec.raw_overrides:
            return spec.raw_overrides[key]
    return default
