from __future__ import annotations

import types

from aistation import presets

from .helpers import make_task


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
