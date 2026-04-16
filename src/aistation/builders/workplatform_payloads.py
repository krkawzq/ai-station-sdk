from __future__ import annotations

from typing import Any

from .._refs import coerce_image_ref
from ..specs import WorkPlatformSpec
from .common import build_env_entries, build_port_pairs


def build_workplatform_payload(
    spec: WorkPlatformSpec,
    *,
    group_id: str,
    account: str | None,
) -> dict[str, Any]:
    volumes = list(spec.volumes)
    if not volumes:
        if not account:
            raise ValueError("account is required to build default workplatform volumes")
        mount_path = f"/{account}"
        volumes = [
            {
                "nodeVolume": mount_path,
                "podVolume": mount_path,
                "volumeType": 2,
                "volumeCache": 0,
                "storageName": "master",
                "bucket": None,
                "originPath": None,
                "datasetCacheType": "LOCAL_CACHE",
                "podVolumeAlias": None,
                "fileType": "",
                "storageType": "",
                "isUnzip": False,
            }
        ]

    payload: dict[str, Any] = {
        "wpName": spec.name,
        "wpType": spec.wp_type,
        "wpPodNum": spec.pod_num,
        "frameWork": spec.frame_work,
        "imageType": spec.image_type,
        "image": coerce_image_ref(spec.image),
        "groupId": group_id,
        "cpu": spec.cpu,
        "memory": spec.memory_gb,
        "acceleratorCard": spec.cards,
        "acceleratorCardKind": spec.card_kind,
        "acceleratorCardType": "",
        "acceleratorCardMemory": 0,
        "shmSize": spec.shm_size,
        "command": spec.command,
        "switchType": spec.switch_type,
        "env": build_env_entries(spec.env),
        "models": list(spec.models),
        "ports": build_port_pairs(spec.ports),
        "volumes": volumes,
        "nodeList": list(spec.node_list),
        "pjId": None,
        "enUpdateDataSet": 0,
    }
    payload.update(spec.raw_overrides)
    return payload
