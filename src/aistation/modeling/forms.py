from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import User
from .images import Image, ImageType_
from .resources import ResourceGroup
from .tasks import TaskType


@dataclass
class FormContext:
    user: User
    resource_groups: list[ResourceGroup]
    images: list[Image]
    image_types: list[ImageType_]
    task_types: list[TaskType]
    start_scripts: list[dict[str, Any]]
    shm_editable: bool
    missing: list[str] = field(default_factory=list)
