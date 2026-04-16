from __future__ import annotations

import pytest

from aistation.errors import SpecValidationError
from aistation.specs import TaskSpec
from aistation.validation import validate_group_card_compatibility, validate_spec


def test_validate_spec_accepts_valid_input(sample_user) -> None:
    spec = TaskSpec(
        name="ValidTask1",
        resource_group="GPU-POOL-A",
        image="ml/pytorch:latest",
        command="python train.py",
        cards=1,
        cpu=8,
        memory_gb=16,
        shm_size=4,
        mount_path="/alice/work",
    )

    validate_spec(spec, user=sample_user)


@pytest.mark.parametrize(
    ("spec", "field_name"),
    [
        (
            TaskSpec(name="bad-name", resource_group="g", image="ml/pytorch:latest", command="x"),
            "name",
        ),
        (
            TaskSpec(name="NoTag1", resource_group="g", image="ml/pytorch", command="x"),
            "image",
        ),
        (
            TaskSpec(name="BadSwitch1", resource_group="g", image="ml/pytorch:latest", command="x", switch_type="eth"),
            "switch_type",
        ),
        (
            TaskSpec(name="BadMem1", resource_group="g", image="ml/pytorch:latest", command="x", memory_gb=4, shm_size=3),
            "memory_gb",
        ),
    ],
)
def test_validate_spec_rejects_known_invalid_inputs(spec: TaskSpec, field_name: str, sample_user) -> None:
    with pytest.raises(SpecValidationError) as exc_info:
        validate_spec(spec, user=sample_user)
    assert exc_info.value.field_name == field_name


def test_validate_mount_path_and_group_card_compatibility(sample_user) -> None:
    spec = TaskSpec(
        name="MountBad1",
        resource_group="g",
        image="ml/pytorch:latest",
        command="x",
        mount_path="/alice",
    )

    with pytest.raises(SpecValidationError) as exc_info:
        validate_spec(spec, user=sample_user)
    assert exc_info.value.field_name == "mount_path"

    with pytest.raises(SpecValidationError):
        validate_group_card_compatibility("GPU", "CPU", 0)
    with pytest.raises(SpecValidationError):
        validate_group_card_compatibility("CPU", "CPU", 1)
