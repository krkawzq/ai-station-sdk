"""Async polling helpers for task and workplatform status transitions."""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from ..errors import AiStationError, TransportError
from ..modeling.tasks import Pod, Task
from ..modeling.workplatforms import WorkPlatform

if TYPE_CHECKING:
    from .client import AsyncAiStationClient


DEFAULT_TERMINAL_STATUSES = frozenset({"Running", "Succeeded", "Failed", "Terminating"})
DEFAULT_WORKPLATFORM_READY_STATUSES = frozenset({"Running", "Halt", "Stopped", "Failed"})


async def watch_task(
    client: "AsyncAiStationClient",
    task_id: str,
    *,
    interval: float = 5.0,
    timeout: float = 600.0,
    until: set[str] | None = None,
) -> AsyncIterator[Task]:
    stop_set = set(until) if until is not None else set(DEFAULT_TERMINAL_STATUSES)
    deadline = time.monotonic() + timeout
    last_status: str | None = None

    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f"watch_task timed out after {timeout}s (last status={last_status!r})")
        try:
            task = await client.tasks.get(task_id)
        except TransportError:
            await asyncio.sleep(interval)
            continue
        except AiStationError:
            raise

        if task.status != last_status:
            yield task
            last_status = task.status
        if task.status in stop_set:
            break
        await asyncio.sleep(interval)


async def wait_running(
    client: "AsyncAiStationClient",
    task_id: str,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> Task:
    last: Task | None = None
    async for task in watch_task(
        client,
        task_id,
        interval=interval,
        timeout=timeout,
        until={"Running", "Succeeded", "Failed"},
    ):
        last = task
    if last is None:
        last = await client.tasks.get(task_id)
    return last


async def wait_pods(
    client: "AsyncAiStationClient",
    task_id: str,
    *,
    timeout: float = 120.0,
    interval: float = 3.0,
) -> list[Pod]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            pods = await client.tasks.pods(task_id)
        except TransportError:
            await asyncio.sleep(interval)
            continue
        ready = [pod for pod in pods if pod.node_ip and pod.ports]
        if ready:
            return ready
        await asyncio.sleep(interval)
    raise TimeoutError(f"no pods with ports after {timeout}s for task {task_id}")


async def watch_workplatform(
    client: "AsyncAiStationClient",
    wp_id: str,
    *,
    interval: float = 5.0,
    timeout: float = 600.0,
    until: set[str] | None = None,
) -> AsyncIterator[WorkPlatform]:
    stop_set = set(until) if until is not None else set(DEFAULT_WORKPLATFORM_READY_STATUSES)
    deadline = time.monotonic() + timeout
    last_status: str | None = None

    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"watch_workplatform timed out after {timeout}s (last status={last_status!r})"
            )
        try:
            workplatform = await client.workplatforms.get(wp_id)
        except TransportError:
            await asyncio.sleep(interval)
            continue
        except AiStationError:
            raise

        if workplatform.wp_status != last_status:
            yield workplatform
            last_status = workplatform.wp_status
        if workplatform.wp_status in stop_set:
            break
        await asyncio.sleep(interval)


async def wait_workplatform_ready(
    client: "AsyncAiStationClient",
    wp_id: str,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> WorkPlatform:
    last: WorkPlatform | None = None
    async for workplatform in watch_workplatform(
        client,
        wp_id,
        interval=interval,
        timeout=timeout,
        until={"Running", "Halt", "Stopped", "Failed"},
    ):
        last = workplatform
    if last is None:
        last = await client.workplatforms.get(wp_id)
    return last
