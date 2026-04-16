from __future__ import annotations

import builtins
import json
from typing import TYPE_CHECKING, Any

from .builders.task_payloads import build_task_payload
from .errors import AiStationError
from .modeling.tasks import Pod, Task
from .specs import TaskSpec

if TYPE_CHECKING:
    from .client import AiStationClient


class TasksAPI:
    def __init__(self, client: AiStationClient) -> None:
        self._c = client

    def list(self, *, status_flag: int = 0) -> list[Task]:
        """List tasks in one fast-path request.

        ``status_flag``: ``0`` unfinished (running/pending), ``3`` finished.
        Note: a full finished-list call can take ~1 minute when the user has
        thousands of historical jobs.
        """
        return [
            Task.from_api(item)
            for item in self._c.list_all(
                "/api/iresource/v1/train",
                params={"statusFlag": status_flag},
            )
        ]

    def get(self, task_id: str, *, status_flag: int = 0) -> Task:
        for current_status in dict.fromkeys([status_flag, 3, 0]):
            data = self._c.get(
                "/api/iresource/v1/train",
                params={"id": task_id, "statusFlag": current_status, "page": 1, "pageSize": 1},
            )
            if isinstance(data, dict):
                items = data.get("data", [])
                if isinstance(items, list) and items:
                    first = items[0]
                    if isinstance(first, dict):
                        return Task.from_api(first)
        raise ValueError(f"task not found: {task_id}")

    def pods(self, task_id: str) -> builtins.list[Pod]:
        data = self._c.get("/api/iresource/v1/train/job-pod-instance", params={"id": task_id})
        if not isinstance(data, dict):
            return []
        items = data.get("data", [])
        if not isinstance(items, list):
            return []
        return [Pod.from_api(item) for item in items if isinstance(item, dict)]

    def read_log(self, task_id: str, *, pod_name: str | None = None) -> str:
        params = {"podName": pod_name} if pod_name else None
        data = self._c.get(f"/api/iresource/v1/train/{task_id}/read-log", params=params)
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("content", "log", "data"):
                value = data.get(key)
                if isinstance(value, str):
                    return value
            return json.dumps(data, ensure_ascii=False)
        return str(data)

    def check_resources(self, spec: TaskSpec, *, validate: bool = True) -> dict[str, Any]:
        """Dry-run the payload via ``/train/check-resources`` — does not create.

        With ``validate=True`` (default) runs client-side validation first to
        avoid wasting RTT on obviously-bad specs.
        """
        if validate:
            self._validate_spec(spec)
        payload = self._build_payload(spec)
        data = self._c.post("/api/iresource/v1/train/check-resources", json=payload)
        return data if isinstance(data, dict) else {}

    def exists(self, name: str, *, status_flag: int = 0) -> Task | None:
        """Return an existing unfinished task with ``name``, or ``None``."""
        try:
            for t in self.list(status_flag=status_flag):
                if t.name == name:
                    return t
        except AiStationError:
            pass
        return None

    def create(
        self,
        spec: TaskSpec,
        *,
        dry_run: bool = False,
        validate: bool = True,
        precheck: bool = True,
        idempotent: bool = True,
    ) -> Task | dict[str, Any]:
        """Create a training task.

        - ``dry_run``: return the assembled payload without any server call
        - ``validate``: client-side TaskSpec rules (default True)
        - ``precheck``: POST to /train/check-resources first (default True);
          fail fast on obvious issues without creating a stub task
        - ``idempotent``: if an unfinished task with the same name already
          exists, return it instead of creating a duplicate (default True)
        """
        if validate:
            self._validate_spec(spec)

        payload = self._build_payload(spec)
        if dry_run:
            return payload

        if idempotent:
            existing = self.exists(spec.name)
            if existing is not None:
                return existing

        if precheck:
            pre = self._c.post("/api/iresource/v1/train/check-resources", json=payload)
            # precheck returns flag=True (with empty resData) when ok; by the
            # time we're here, any non-ok response already raised via check_flag.
            del pre  # noqa: F841 - success path, value discarded

        response = self._c.post("/api/iresource/v1/train", json=payload)
        self._c.nodes.invalidate_cache()
        task_id = None
        if isinstance(response, dict):
            for key in ("id", "taskId", "jobId", "trainId"):
                value = response.get(key)
                if isinstance(value, str) and value:
                    task_id = value
                    break
        if task_id:
            try:
                return self.get(task_id)
            except ValueError:
                pass

        existing = self.exists(spec.name)
        if existing is not None:
            return existing
        if isinstance(response, dict):
            return response
        raise AiStationError(f"created task but could not locate it: {spec.name}")

    def _validate_spec(self, spec: TaskSpec) -> None:
        """Run client-side validation. Requires login (for user.account context)."""
        from .validation import validate_spec  # lazy import
        user = self._c.user if getattr(self._c, "user", None) else None
        validate_spec(spec, user=user)

    def delete(self, task_id: str | builtins.list[str]) -> dict[str, Any]:
        """Soft-delete one or more tasks (records keep ``deleteFlag=true`` in DB
        but are hidden from list queries).

        Verified endpoint: ``DELETE /api/iresource/v1/train`` with JSON body
        ``{"jobIdList": [...]}``. Server responds with ``resData.trainNames``.
        """
        ids = [task_id] if isinstance(task_id, str) else list(task_id)
        data = self._c._request_with_retry(
            "DELETE",
            "/api/iresource/v1/train",
            json={"jobIdList": ids},
        )
        self._c.nodes.invalidate_cache()
        return data if isinstance(data, dict) else {}

    def stop(self, task_id: str) -> dict[str, Any]:
        """Stop a running task. Note: endpoint rejects already-finished tasks.

        Endpoint observed from the UI: ``POST /api/iresource/v1/train/{id}/stop``
        """
        data = self._c._request_with_retry(
            "POST",
            f"/api/iresource/v1/train/{task_id}/stop",
            json=None,
        )
        self._c.nodes.invalidate_cache()
        return data if isinstance(data, dict) else {}

    def _build_payload(self, spec: TaskSpec) -> dict[str, Any]:
        user = self._c.require_user()
        group_id = self._c.groups.resolve_id(spec.resource_group)
        return build_task_payload(
            spec,
            account=user.account,
            project_id=user.group_id,
            group_id=group_id,
            image_registry_prefix=self._c.config.image_registry_prefix,
        )
