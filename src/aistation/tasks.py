from __future__ import annotations

import builtins
import json
from typing import TYPE_CHECKING, Any

from ._consistency import retry_not_found
from ._refs import coerce_resource_group_ref, coerce_task_id, coerce_task_ids
from ._resolve import resolve_many as _resolve_many
from ._resolve import resolve_one as _resolve_one
from .builders.task_payloads import build_task_payload
from .cache import TTLCache
from .errors import AiStationError, NotFoundError
from .modeling.runtime import OperationResult
from .modeling.tasks import Pod, Task
from .specs import TaskSpec
from .watch import wait_pods, wait_running

if TYPE_CHECKING:
    from .client import AiStationClient


class TasksAPI:
    def __init__(self, client: AiStationClient) -> None:
        self._c = client
        self._list_cache: TTLCache[list[Task]] = TTLCache(ttl=15.0)

    def list(self, *, status_flag: int = 0, refresh: bool = False) -> list[Task]:
        """List tasks in one fast-path request.

        ``status_flag``: ``0`` unfinished (running/pending), ``3`` finished.
        Note: a full finished-list call can take ~1 minute when the user has
        thousands of historical jobs.
        """
        cached = self._list_cache.get(status_flag) if not refresh else None
        if cached is not None:
            return cached
        items = [
            Task.from_api(item)
            for item in self._c.list_all(
                "/api/iresource/v1/train",
                params={"statusFlag": status_flag},
            )
        ]
        self._list_cache.set(items, status_flag)
        return items

    def get(self, task_id: str | Task, *, status_flag: int = 0) -> Task:
        resolved_id = coerce_task_id(task_id)
        for current_status in dict.fromkeys([status_flag, 3, 0]):
            data = self._c.get(
                "/api/iresource/v1/train",
                params={"id": resolved_id, "statusFlag": current_status, "page": 1, "pageSize": 1},
            )
            if isinstance(data, dict):
                items = data.get("data", [])
                if isinstance(items, list) and items:
                    first = items[0]
                    if isinstance(first, dict):
                        return Task.from_api(first)
        raise NotFoundError("task", resolved_id)

    def resolve_many(
        self,
        query: str,
        *,
        include_finished: bool = True,
        refresh: bool = False,
    ) -> builtins.list[Task]:
        items = self.list(status_flag=0, refresh=refresh)
        if include_finished:
            items = self._dedupe(items + self.list(status_flag=3, refresh=refresh))
        return _resolve_many(
            query,
            items,
            key_fns=(
                lambda item: item.id,
                lambda item: item.name,
            ),
        )

    def resolve(
        self,
        query: str,
        *,
        include_finished: bool = True,
        refresh: bool = False,
    ) -> Task:
        items = self.list(status_flag=0, refresh=refresh)
        if include_finished:
            items = self._dedupe(items + self.list(status_flag=3, refresh=refresh))
        return _resolve_one(
            query,
            items,
            key_fns=(
                lambda item: item.id,
                lambda item: item.name,
            ),
            label_fn=lambda item: f"{item.name} ({item.id})",
            resource_type="task",
        )

    def pods(self, task_id: str | Task) -> builtins.list[Pod]:
        resolved_id = coerce_task_id(task_id)
        data = self._c.get("/api/iresource/v1/train/job-pod-instance", params={"id": resolved_id})
        if not isinstance(data, dict):
            return []
        items = data.get("data", [])
        if not isinstance(items, list):
            return []
        return [Pod.from_api(item) for item in items if isinstance(item, dict)]

    def read_log(self, task_id: str | Task, *, pod_name: str | None = None) -> str:
        resolved_id = coerce_task_id(task_id)
        params = {"podName": pod_name} if pod_name else None
        data = self._c.get(f"/api/iresource/v1/train/{resolved_id}/read-log", params=params)
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("content", "log", "data"):
                value = data.get(key)
                if isinstance(value, str):
                    return value
            return json.dumps(data, ensure_ascii=False)
        return str(data)

    def check_resources(self, spec: TaskSpec, *, validate: bool = True) -> OperationResult[Task]:
        """Dry-run the payload via ``/train/check-resources`` — does not create.

        With ``validate=True`` (default) runs client-side validation first to
        avoid wasting RTT on obviously-bad specs.
        """
        if validate:
            self._validate_spec(spec)
        payload = self._build_payload(spec)
        data = self._c.post("/api/iresource/v1/train/check-resources", json=payload)
        return OperationResult(
            action="check_resources",
            resource_type="task",
            payload=payload,
            raw=data if isinstance(data, dict) else {},
        )

    def exists(self, name: str, *, status_flag: int = 0, refresh: bool = False) -> Task | None:
        """Return an existing unfinished task with ``name``, or ``None``."""
        try:
            for t in self.list(status_flag=status_flag, refresh=refresh):
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
    ) -> OperationResult[Task]:
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
            return OperationResult(
                action="create",
                resource_type="task",
                payload=payload,
                raw=payload,
            )

        if idempotent:
            existing = self.exists(spec.name)
            if existing is not None:
                return OperationResult(
                    action="create",
                    resource_type="task",
                    entity=existing,
                    payload=payload,
                    target_id=existing.id,
                    reused=True,
                )

        if precheck:
            pre = self._c.post("/api/iresource/v1/train/check-resources", json=payload)
            # precheck returns flag=True (with empty resData) when ok; by the
            # time we're here, any non-ok response already raised via check_flag.
            del pre  # noqa: F841 - success path, value discarded

        response = self._c.post("/api/iresource/v1/train", json=payload)
        self.invalidate_cache()
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
                return OperationResult(
                    action="create",
                    resource_type="task",
                    entity=retry_not_found(lambda: self.get(task_id)),
                    payload=payload,
                    raw=response,
                    target_id=task_id,
                    created=True,
                )
            except NotFoundError:
                pass

        existing = self._find_created_task_by_name(spec.name)
        if existing is not None:
            return OperationResult(
                action="create",
                resource_type="task",
                entity=existing,
                payload=payload,
                raw=response,
                target_id=existing.id,
                created=True,
            )
        return OperationResult(
            action="create",
            resource_type="task",
            payload=payload,
            raw=response,
            created=True,
        )

    def create_and_wait(
        self,
        spec: TaskSpec,
        *,
        validate: bool = True,
        precheck: bool = True,
        idempotent: bool = True,
        timeout: float = 600.0,
        interval: float = 5.0,
        wait_for_pods: bool = False,
        pod_timeout: float = 120.0,
        pod_interval: float = 3.0,
    ) -> OperationResult[Task]:
        result = self.create(
            spec,
            validate=validate,
            precheck=precheck,
            idempotent=idempotent,
        )
        result.entity = self.wait_running(
            result.require_entity(f"created task but could not locate it: {spec.name}"),
            timeout=timeout,
            interval=interval,
        )
        result.waited = True
        if wait_for_pods:
            result.extras["pods"] = self.wait_pods(
                result.entity,
                timeout=pod_timeout,
                interval=pod_interval,
            )
        return result

    def _validate_spec(self, spec: TaskSpec) -> None:
        """Run client-side validation. Requires login (for user.account context)."""
        from .validation import validate_spec  # lazy import
        user = self._c.user if getattr(self._c, "user", None) else None
        validate_spec(spec, user=user)

    def delete(self, task_id: str | Task | builtins.list[str | Task]) -> OperationResult[Task]:
        """Soft-delete one or more tasks (records keep ``deleteFlag=true`` in DB
        but are hidden from list queries).

        Verified endpoint: ``DELETE /api/iresource/v1/train`` with JSON body
        ``{"jobIdList": [...]}``. Server responds with ``resData.trainNames``.
        """
        ids = coerce_task_ids(task_id)
        data = self._c._request_with_retry(
            "DELETE",
            "/api/iresource/v1/train",
            json={"jobIdList": ids},
        )
        self.invalidate_cache()
        self._c.nodes.invalidate_cache()
        return OperationResult(
            action="delete",
            resource_type="task",
            raw=data if isinstance(data, dict) else {},
            target_id=ids[0] if len(ids) == 1 else None,
            target_ids=ids,
        )

    def stop(self, task_id: str | Task) -> OperationResult[Task]:
        """Stop a running task. Note: endpoint rejects already-finished tasks.

        Endpoint observed from the UI: ``POST /api/iresource/v1/train/{id}/stop``
        """
        resolved_id = coerce_task_id(task_id)
        data = self._c._request_with_retry(
            "POST",
            f"/api/iresource/v1/train/{resolved_id}/stop",
            json=None,
        )
        self.invalidate_cache()
        self._c.nodes.invalidate_cache()
        return OperationResult(
            action="stop",
            resource_type="task",
            raw=data if isinstance(data, dict) else {},
            target_id=resolved_id,
            target_ids=[resolved_id],
        )

    def wait_running(
        self,
        task_id: str | Task,
        *,
        timeout: float = 600.0,
        interval: float = 5.0,
    ) -> Task:
        return wait_running(
            self._c,
            coerce_task_id(task_id),
            timeout=timeout,
            interval=interval,
        )

    def wait_pods(
        self,
        task_id: str | Task,
        *,
        timeout: float = 120.0,
        interval: float = 3.0,
    ) -> builtins.list[Pod]:
        return wait_pods(
            self._c,
            coerce_task_id(task_id),
            timeout=timeout,
            interval=interval,
        )

    def invalidate_cache(self) -> None:
        self._list_cache.invalidate()

    def _build_payload(self, spec: TaskSpec) -> dict[str, Any]:
        user = self._c.require_user()
        group_ref = coerce_resource_group_ref(spec.resource_group)
        group_id = self._c.groups.resolve(group_ref).group_id
        return build_task_payload(
            spec,
            account=user.account,
            project_id=user.group_id,
            group_id=group_id,
            image_registry_prefix=self._c.config.image_registry_prefix,
        )

    def _find_created_task_by_name(self, name: str) -> Task | None:
        try:
            return retry_not_found(lambda: self._require_existing_task(name))
        except NotFoundError:
            return None

    def _require_existing_task(self, name: str) -> Task:
        existing = self.exists(name, refresh=True)
        if existing is not None:
            return existing
        raise NotFoundError("task", name)

    @staticmethod
    def _dedupe(items: builtins.list[Task]) -> builtins.list[Task]:
        seen: set[str] = set()
        result: builtins.list[Task] = []
        for item in items:
            if item.id in seen:
                continue
            seen.add(item.id)
            result.append(item)
        return result
