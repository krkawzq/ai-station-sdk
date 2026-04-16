from __future__ import annotations

import pytest

from aistation.aio.watch import (
    wait_pods,
    wait_running,
    wait_workplatform_ready,
    watch_task,
    watch_workplatform,
)
from aistation.errors import TransportError

from .helpers import make_pod, make_task, make_workplatform


class _DummyTasks:
    def __init__(self, statuses: list[object], pods: list[list[object]] | None = None) -> None:
        self._statuses = list(statuses)
        self._pods = list(pods or [])

    async def get(self, task_id: str):
        del task_id
        item = self._statuses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def pods(self, task_id: str):
        del task_id
        return self._pods.pop(0)


class _DummyClient:
    def __init__(self, tasks: _DummyTasks, workplatforms: object | None = None) -> None:
        self.tasks = tasks
        self.workplatforms = workplatforms


@pytest.mark.asyncio
async def test_async_watch_task_swallow_transport_error_and_yield_transitions(monkeypatch) -> None:
    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("aistation.aio.watch.asyncio.sleep", fake_sleep)
    client = _DummyClient(
        _DummyTasks(
            [
                TransportError("temporary"),
                make_task(status="Pending"),
                make_task(status="Running"),
            ]
        )
    )

    states = [state async for state in watch_task(client, "task-1", interval=0.0, timeout=1.0, until={"Running"})]

    assert [task.status for task in states] == ["Pending", "Running"]


@pytest.mark.asyncio
async def test_async_wait_running_and_wait_pods(monkeypatch) -> None:
    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("aistation.aio.watch.asyncio.sleep", fake_sleep)

    running_client = _DummyClient(_DummyTasks([make_task(status="Pending"), make_task(status="Running")]))
    pod_client = _DummyClient(_DummyTasks([], pods=[[], [make_pod()]]))

    final = await wait_running(running_client, "task-1", timeout=1.0, interval=0.0)
    pods = await wait_pods(pod_client, "task-1", timeout=1.0, interval=0.0)

    assert final.status == "Running"
    assert pods[0].external_urls == ["198.51.100.10:30080"]


class _DummyWorkPlatforms:
    def __init__(self, states: list[object]) -> None:
        self._states = list(states)

    async def get(self, wp_id: str):
        del wp_id
        item = self._states.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.mark.asyncio
async def test_async_watch_workplatform_and_wait_ready(monkeypatch) -> None:
    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("aistation.aio.watch.asyncio.sleep", fake_sleep)
    client = _DummyClient(
        _DummyTasks([]),
        workplatforms=_DummyWorkPlatforms(
            [
                TransportError("temporary"),
                make_workplatform(status="Pending"),
                make_workplatform(status="Running"),
            ]
        ),
    )

    states = [
        state
        async for state in watch_workplatform(client, "wp-1", interval=0.0, timeout=1.0, until={"Running"})
    ]
    final = await wait_workplatform_ready(
        _DummyClient(_DummyTasks([]), workplatforms=_DummyWorkPlatforms([make_workplatform(status="Running")])),
        "wp-1",
        timeout=1.0,
        interval=0.0,
    )

    assert [state.wp_status for state in states] == ["Pending", "Running"]
    assert final.wp_status == "Running"
