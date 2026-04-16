from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._coerce import as_bool, as_int, as_json_string
from .common import Port


@dataclass
class JobVolume:
    file_model: int
    function_model: int
    volume_mount: str
    storage_name: str
    bucket: str = ""
    origin_path: str | None = None
    dataset_cache_type: str | None = None
    file_type: str | None = None
    is_unzip: bool = False
    volume_mount_alias: str | None = None
    storage_type: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "fileModel": int(self.file_model),
            "functionModel": int(self.function_model),
            "volumeMount": self.volume_mount,
            "storageName": self.storage_name,
            "bucket": self.bucket,
        }
        if self.is_unzip or self.function_model == 1:
            payload["isUnzip"] = self.is_unzip
        if self.origin_path is not None:
            payload["originPath"] = self.origin_path
        if self.dataset_cache_type is not None:
            payload["datasetCacheType"] = self.dataset_cache_type
        if self.file_type is not None:
            payload["fileType"] = self.file_type
        if self.volume_mount_alias is not None:
            payload["volumeMountAlias"] = self.volume_mount_alias
        if self.storage_type is not None:
            payload["storageType"] = self.storage_type
        return payload

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        return cls(
            file_model=as_int(d.get("fileModel")),
            function_model=as_int(d.get("functionModel")),
            volume_mount=str(d.get("volumeMount", "")),
            storage_name=str(d.get("storageName", "")),
            bucket=str(d.get("bucket", "")),
            origin_path=str(d["originPath"]) if d.get("originPath") is not None else None,
            dataset_cache_type=str(d["datasetCacheType"]) if d.get("datasetCacheType") is not None else None,
            file_type=str(d["fileType"]) if d.get("fileType") is not None else None,
            is_unzip=as_bool(d.get("isUnzip")),
            volume_mount_alias=str(d["volumeMountAlias"]) if d.get("volumeMountAlias") is not None else None,
            storage_type=str(d["storageType"]) if d.get("storageType") is not None else None,
            raw=d,
        )


@dataclass
class Pod:
    pod_id: str
    pod_name: str
    pod_name_changed: str
    pod_status: str
    node_name: str
    node_ip: str
    pod_ip: str
    gpu_ids: str
    gpu_names: str
    pod_gpu_type: str
    ports: list[Port]
    restart_count: int
    switch_type: str
    create_time_ms: int
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def external_urls(self) -> list[str]:
        return [f"{self.node_ip}:{port.node_port}" for port in self.ports if self.node_ip and port.node_port]

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        ports = d.get("ports") or []
        return cls(
            pod_id=str(d.get("podId", "")),
            pod_name=str(d.get("podName", "")),
            pod_name_changed=str(d.get("podNameChanged", "")),
            pod_status=str(d.get("podStatus", "")),
            node_name=str(d.get("nodeName", "")),
            node_ip=str(d.get("nodeIp", "")),
            pod_ip=str(d.get("podIp", "")),
            gpu_ids=str(d.get("gpuIds", "")),
            gpu_names=str(d.get("gpuNames", "")),
            pod_gpu_type=str(d.get("podGpuType", "")),
            ports=[Port.from_api(port) for port in ports if isinstance(port, dict)],
            restart_count=as_int(d.get("restartCount")),
            switch_type=str(d.get("switchType", "")),
            create_time_ms=as_int(d.get("createDateTime") or d.get("createTime")),
            raw=d,
        )


@dataclass
class Task:
    id: str
    name: str
    status: str
    user_id: str
    user_name: str
    project_id: str
    project_name: str
    resource_group_id: str
    resource_group_name: str
    job_type: str
    image: str
    image_type: str
    image_flag: int
    command: str
    start_script: str
    exec_dir: str
    mount_dir: str
    script_dir: str
    log_out: str
    log_persistence: str
    config: str
    gpu_info: str
    pod_info: str
    switch_type: str
    dist_flag: bool
    mpi_flag: bool
    is_elastic: bool
    shm_size: int
    ports: str
    emergency_flag: bool
    task_type: int
    task_type_name: str
    create_time_ms: int
    start_time_ms: int | None
    end_time_ms: int | None
    run_time_s: int
    node_name: str
    job_volume: list[JobVolume]
    status_reason: str
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        raw_ports = d.get("ports", "")
        if isinstance(raw_ports, list):
            ports = ",".join(str(item) for item in raw_ports)
        else:
            ports = str(raw_ports or "")
        job_volume = d.get("jobVolume") or []
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            status=str(d.get("status", "")),
            user_id=str(d.get("userId", "")),
            user_name=str(d.get("userName", "")),
            project_id=str(d.get("projectId") or d.get("groupId") or ""),
            project_name=str(d.get("projectName", "")),
            resource_group_id=str(d.get("resGroupId") or d.get("resourceGroupId") or ""),
            resource_group_name=str(d.get("resGroupName") or d.get("resourceGroupName") or ""),
            job_type=str(d.get("jobType", "")),
            image=str(d.get("image", "")),
            image_type=str(d.get("imageType", "")),
            image_flag=as_int(d.get("imageFlag")),
            command=str(d.get("command", "")),
            start_script=str(d.get("startScript", "")),
            exec_dir=str(d.get("execDir", "")),
            mount_dir=str(d.get("mountDir", "")),
            script_dir=str(d.get("scriptDir", "")),
            log_out=str(d.get("logOut", "")),
            log_persistence=str(d.get("logPersistence", "")),
            config=as_json_string(d.get("config")),
            gpu_info=as_json_string(d.get("gpuInfo")),
            pod_info=as_json_string(d.get("podInfo")),
            switch_type=str(d.get("switchType", "")),
            dist_flag=as_bool(d.get("distFlag")),
            mpi_flag=as_bool(d.get("mpiFlag")),
            is_elastic=as_bool(d.get("isElastic")),
            shm_size=as_int(d.get("shmSize"), 0),
            ports=ports,
            emergency_flag=as_bool(d.get("emergencyFlag")),
            task_type=as_int(d.get("taskType")),
            task_type_name=str(d.get("taskTypeName", "")),
            create_time_ms=as_int(d.get("createDateTime") or d.get("createTime")),
            start_time_ms=(
                as_int(d.get("startDateTime") or d.get("startTime"))
                if d.get("startDateTime") is not None or d.get("startTime") is not None
                else None
            ),
            end_time_ms=(
                as_int(d.get("endDateTime") or d.get("endTime") or d.get("finishDateTime"))
                if d.get("endDateTime") is not None
                or d.get("endTime") is not None
                or d.get("finishDateTime") is not None
                else None
            ),
            run_time_s=as_int(d.get("runTime") or d.get("runTimeS")),
            node_name=str(d.get("nodeName", "")),
            job_volume=[JobVolume.from_api(item) for item in job_volume if isinstance(item, dict)],
            status_reason=str(d.get("statusReason", "")),
            raw=d,
        )


@dataclass
class TaskType:
    type_code: str
    type_name: str
    platform: str
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        return cls(
            type_code=str(d.get("typeCode", "")),
            type_name=str(d.get("typeName", "")),
            platform=str(d.get("platform", "")),
            raw=d,
        )
