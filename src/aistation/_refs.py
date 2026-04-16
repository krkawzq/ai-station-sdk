from __future__ import annotations

from collections.abc import Iterable

from .errors import AiStationError
from .modeling.images import Image
from .modeling.resources import ResourceGroup
from .modeling.tasks import Task
from .modeling.workplatforms import WorkPlatform


def coerce_task_id(task_or_id: str | Task) -> str:
    if isinstance(task_or_id, Task):
        return _require_ref(task_or_id.id, resource_type="task")
    return _require_ref(task_or_id, resource_type="task")


def coerce_task_ids(task_or_ids: str | Task | Iterable[str | Task]) -> list[str]:
    if isinstance(task_or_ids, str | Task):
        return [coerce_task_id(task_or_ids)]
    return [coerce_task_id(item) for item in task_or_ids]


def coerce_workplatform_id(workplatform_or_id: str | WorkPlatform) -> str:
    if isinstance(workplatform_or_id, WorkPlatform):
        return _require_ref(workplatform_or_id.wp_id, resource_type="workplatform")
    return _require_ref(workplatform_or_id, resource_type="workplatform")


def coerce_resource_group_ref(group_or_ref: str | ResourceGroup) -> str:
    if isinstance(group_or_ref, ResourceGroup):
        return _require_ref(group_or_ref.group_id or group_or_ref.group_name, resource_type="resource group")
    return _require_ref(group_or_ref, resource_type="resource group")


def coerce_image_ref(image_or_ref: str | Image) -> str:
    if isinstance(image_or_ref, Image):
        return _require_ref(image_or_ref.full_ref, resource_type="image")
    return _require_ref(image_or_ref, resource_type="image")


def _require_ref(value: str, *, resource_type: str) -> str:
    ref = value.strip()
    if ref:
        return ref
    raise AiStationError(
        f"{resource_type} reference is empty",
        err_code="SDK_INVALID_REFERENCE",
        err_message=f"{resource_type} reference is empty",
    )
