from __future__ import annotations

import types

from aistation import presets
from aistation.specs import TaskSpec, WorkPlatformSpec

from .helpers import make_task, make_workplatform


def test_gpu_hold_and_cpu_debug_presets(monkeypatch) -> None:
    monkeypatch.setattr(presets.uuid, "uuid4", lambda: types.SimpleNamespace(hex="deadbeefcafebabe"))

    gpu = presets.gpu_hold(resource_group="GPU-POOL-A", cards=2, hours=1, name_prefix="hold-job")
    cpu = presets.cpu_debug(resource_group="CPU-POOL", name_prefix="cpu-debug")

    assert gpu.name == "holdjobdeadbeef"
    assert gpu.command == "sleep 3600"
    assert gpu.cards == 2
    assert gpu.card_kind == "GPU"

    assert cpu.name == "cpudebugdeadbeef"
    assert cpu.cards == 0
    assert cpu.card_kind == "CPU"
    assert cpu.raw_overrides["execDir"] == ""


def test_pytorch_train_and_from_existing(monkeypatch) -> None:
    monkeypatch.setattr(presets.uuid, "uuid4", lambda: types.SimpleNamespace(hex="beadfacecafebabe"))

    train = presets.pytorch_train(
        resource_group="GPU-POOL-A",
        image="ml/pytorch:latest",
        command="python train.py",
        ports=[8080],
        env={"A": "1"},
    )
    cloned = presets.from_existing(make_task(name="SourceTask1", ports="22,8080"))

    assert train.name == "trainbeadface"
    assert train.image_type == "pytorch"
    assert train.ports == [8080]
    assert train.env == {"A": "1"}

    assert cloned.name == "clonebeadface"
    assert cloned.resource_group == "GPU-POOL-A"
    assert cloned.command == "sleep 30"
    assert cloned.ports == [22, 8080]


def test_taskspec_classmethods_delegate_to_presets(monkeypatch) -> None:
    monkeypatch.setattr(presets.uuid, "uuid4", lambda: types.SimpleNamespace(hex="12345678cafebabe"))

    gpu = TaskSpec.gpu_hold(resource_group="GPU-POOL-A")
    cpu = TaskSpec.cpu_debug(resource_group="CPU-POOL")
    train = TaskSpec.pytorch_train(
        resource_group="GPU-POOL-A",
        image="ml/pytorch:latest",
        command="python train.py",
    )
    cloned = TaskSpec.from_existing(make_task(name="SourceTask2"))

    assert gpu.name == "hold12345678"
    assert cpu.name == "cpudbg12345678"
    assert train.name == "train12345678"
    assert cloned.name == "clone12345678"


def test_workplatform_spec_notebook_and_from_existing(monkeypatch) -> None:
    monkeypatch.setattr("aistation.specs.uuid.uuid4", lambda: types.SimpleNamespace(hex="87654321cafebabe"))

    notebook = WorkPlatformSpec.notebook(
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
        cards=1,
    )
    cloned = WorkPlatformSpec.from_existing(make_workplatform())

    assert notebook.name == "notebook87654321"
    assert notebook.card_kind == "GPU"
    assert notebook.command == "sleep infinity"
    assert cloned.name == "clone87654321"
    assert cloned.resource_group == "DEV-POOL"
