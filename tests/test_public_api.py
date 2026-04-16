from __future__ import annotations

import aistation as A
from aistation.specs import TaskSpec as NewTaskSpec
from aistation.specs import WorkPlatformSpec as NewWorkPlatformSpec


def test_public_api_exports_current_surface() -> None:
    assert A.AiStationClient is not None
    assert A.TaskSpec is not None
    assert A.TTLCache is not None
    assert A.lookup_error_guide("IBASE_NO_PERMISSION") is not None
    assert A.presets is not None
    assert A.recommend is not None
    assert A.specs is not None
    assert A.validation is not None
    assert A.watch is not None


def test_specs_module_provides_public_spec_types() -> None:
    assert A.TaskSpec is NewTaskSpec
    assert A.WorkPlatformSpec is NewWorkPlatformSpec
