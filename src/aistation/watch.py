"""Polling helpers for task status transitions.

None of these involve websockets — AI Station doesn't expose any — we just
poll on a reasonable interval and stream transitions to the caller.
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

from .errors import AiStationError, TransportError
from .modeling.tasks import Pod, Task
from .modeling.workplatforms import WorkPlatform

if TYPE_CHECKING:
    from .client import AiStationClient


DEFAULT_TERMINAL_STATUSES = frozenset({"Running", "Succeeded", "Failed", "Terminating"})
DEFAULT_WORKPLATFORM_READY_STATUSES = frozenset({"Running", "Halt", "Stopped", "Failed"})


def watch_task(
    client: "AiStationClient",
    task_id: str,
    *,
    interval: float = 5.0,
    timeout: float = 600.0,
    until: set[str] | None = None,
) -> Iterator[Task]:
    """Yield the :class:`Task` each time its ``status`` changes.

    Stops when:
    - status enters one of ``until`` (defaults to terminal + Running)
    - ``timeout`` seconds have elapsed since start (raises TimeoutError)

    Network blips are swallowed (caller sees a reduced update rate, not an
    exception) — only the final timeout raises.

    Example::

        for state in watch_task(client, tid, until={"Running"}):
            print(state.status)
    """
    stop_set = set(until) if until is not None else set(DEFAULT_TERMINAL_STATUSES)
    deadline = time.monotonic() + timeout
    last_status: str | None = None

    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f"watch_task timed out after {timeout}s (last status={last_status!r})")
        try:
            task = client.tasks.get(task_id)
        except TransportError:
            time.sleep(interval)
            continue
        except AiStationError:
            # Permission / not-found — surface; caller decides
            raise

        if task.status != last_status:
            yield task
            last_status = task.status
        if task.status in stop_set:
            break
        time.sleep(interval)


def wait_running(
    client: "AiStationClient",
    task_id: str,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> Task:
    """Block until the task is Running (or fails). Returns the final Task."""
    last: Task | None = None
    for t in watch_task(
        client, task_id,
        interval=interval, timeout=timeout,
        until={"Running", "Succeeded", "Failed"},
    ):
        last = t
    if last is None:
        # Defensive: watch_task always yields at least the first status
        last = client.tasks.get(task_id)
    return last


def wait_pods(
    client: "AiStationClient",
    task_id: str,
    *,
    timeout: float = 120.0,
    interval: float = 3.0,
) -> list[Pod]:
    """Block until pods with port mappings appear. Returns the pod list."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            pods = client.tasks.pods(task_id)
        except TransportError:
            time.sleep(interval)
            continue
        ready = [p for p in pods if p.node_ip and p.ports]
        if ready:
            return ready
        time.sleep(interval)
    raise TimeoutError(f"no pods with ports after {timeout}s for task {task_id}")


def watch_workplatform(
    client: "AiStationClient",
    wp_id: str,
    *,
    interval: float = 5.0,
    timeout: float = 600.0,
    until: set[str] | None = None,
) -> Iterator[WorkPlatform]:
    """Yield the WorkPlatform each time its status changes."""
    stop_set = set(until) if until is not None else set(DEFAULT_WORKPLATFORM_READY_STATUSES)
    deadline = time.monotonic() + timeout
    last_status: str | None = None

    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"watch_workplatform timed out after {timeout}s (last status={last_status!r})"
            )
        try:
            wp = client.workplatforms.get(wp_id)
        except TransportError:
            time.sleep(interval)
            continue
        except AiStationError:
            raise

        if wp.wp_status != last_status:
            yield wp
            last_status = wp.wp_status
        if wp.wp_status in stop_set:
            break
        time.sleep(interval)


def wait_workplatform_ready(
    client: "AiStationClient",
    wp_id: str,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> WorkPlatform:
    """Block until the dev env reaches a ready or terminal status."""
    last: WorkPlatform | None = None
    for wp in watch_workplatform(
        client,
        wp_id,
        interval=interval,
        timeout=timeout,
        until={"Running", "Halt", "Stopped", "Failed"},
    ):
        last = wp
    if last is None:
        last = client.workplatforms.get(wp_id)
    return last
