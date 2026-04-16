from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, TypeVar

from .errors import AiStationError, PermissionDenied
from .modeling.forms import FormContext
from .modeling.images import ImageType_
from .modeling.tasks import TaskType

if TYPE_CHECKING:
    from .client import AiStationClient

T = TypeVar("T")


def enumerate_form_context(
    client: AiStationClient,
    *,
    include_all_images: bool = True,
) -> FormContext:
    user = client.require_user()
    missing: list[str] = []

    def _safe(label: str, fn: Callable[[], T]) -> T | None:
        try:
            return fn()
        except PermissionDenied as exc:
            missing.append(f"{label}: denied ({exc.err_code})")
        except AiStationError as exc:
            missing.append(f"{label}: {exc.err_code}: {exc.err_message or exc}")
        except Exception as exc:  # pragma: no cover - defensive
            missing.append(f"{label}: {type(exc).__name__}: {exc}")
        return None

    raw_types = _safe("image-type", lambda: client.get("/api/iresource/v1/image-type")) or []
    image_types = [ImageType_.from_api(item) for item in raw_types if isinstance(item, dict)]

    raw_task_types = _safe(
        "timeout-task-type",
        lambda: client.get("/api/iresource/v1/base/timeout-task-type"),
    ) or []
    task_types = [TaskType.from_api(item) for item in raw_task_types if isinstance(item, dict)]

    shm_value = _safe("config/shm", lambda: client.get("/api/iresource/v1/config/shm"))
    shm_editable = bool(shm_value) if shm_value is not None else True

    raw_scripts = _safe("train/start-file", lambda: client.get("/api/iresource/v1/train/start-file")) or {}
    start_scripts: list[dict[str, Any]] = []
    if isinstance(raw_scripts, dict):
        start_scripts_data = raw_scripts.get("startScriptList", [])
        if isinstance(start_scripts_data, list):
            start_scripts = [item for item in start_scripts_data if isinstance(item, dict)]

    images = _safe(
        "images/all",
        lambda: client.images.list() if include_all_images else client.images.list(share=2),
    ) or []
    groups = _safe("resource-groups", client.groups.list) or []

    return FormContext(
        user=user,
        resource_groups=groups,
        images=images,
        image_types=image_types,
        task_types=task_types,
        start_scripts=start_scripts,
        shm_editable=shm_editable,
        missing=missing,
    )
