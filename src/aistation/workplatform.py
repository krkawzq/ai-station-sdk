"""Development-environment (work-platform) API.

Dev envs are Jupyter-like interactive workspaces. They live on groups tagged
``groupLabel=develop`` and have shorter default lifetimes than training tasks.

API shape notes (from reverse-engineering):
- List running:   GET  /work-platform/goto-train-job?statusFlag=0  (confusing name,
                  actually lists user's active workloads)
- List history:   GET  /work-platform/history?page=1&pageSize=N
- Detail:         GET  /work-platform/{wpId}/detail
- Rebuild tmpl:   GET  /work-platform/{wpId}/rebuild?from=1   ← the easiest way
                  to get a valid creation payload is to rebuild from an
                  existing env
- Create:         POST /work-platform/   (note trailing slash; empty body triggers
                  per-field NOT_NULL probes exactly like /train)
- Delete:         DELETE /work-platform/{wpId}   (no body; simpler than /train)
- Jupyter URL:    GET  /work-platform/{wpId}/jupyter
- Shell URL:      GET  /work-platform/{wpId}/shell
- Commit image:   POST /work-platform/commit-image
- Collect/star:   PUT  /work-platform/history-collect/   (body: {wpId, isHistoryCollect})
- Eligible groups: GET /node-group?page=-1&pageSize=-1&groupStatus=1&groupLabel=develop&nodeGroup=1
"""
from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from ._consistency import retry_not_found
from ._refs import coerce_resource_group_ref, coerce_workplatform_id
from ._resolve import resolve_many as _resolve_many
from ._resolve import resolve_one as _resolve_one
from .builders.workplatform_payloads import build_workplatform_payload
from .cache import TTLCache
from .errors import AiStationError, NotFoundError
from .modeling.runtime import OperationResult
from .modeling.resources import ResourceGroup
from .modeling.workplatforms import WorkPlatform
from .specs import WorkPlatformSpec
from .watch import wait_workplatform_ready

if TYPE_CHECKING:
    from .client import AiStationClient


# Known enum values empirically observed from the server's error messages.
WP_TYPES = ("COMMON_WP",)  # server enum includes PROJECT_* variants we haven't tested
_TERMINAL_WP_STATUSES = frozenset({
    "halt",
    "stopped",
    "failed",
    "deleted",
    "terminated",
    "succeeded",
    "finished",
    "closed",
})


class WorkPlatformsAPI:
    """Manage development environments.

    Example::

        spec = WorkPlatformSpec(
            name="mynotebook",
            resource_group="4V100",
            image="192.168.108.1:5000/pytorch/pytorch:21.10-py3",
            cards=1,
            card_kind="GPU",
            cpu=4,
            memory_gb=16,
            command="sleep infinity",
        )
        wp = client.workplatforms.create(spec).entity
        print(wp.wp_id, wp.wp_status)  # type: ignore[union-attr]
        # ... work ...
        client.workplatforms.delete(wp.wp_id)  # type: ignore[union-attr]
    """

    def __init__(self, client: AiStationClient) -> None:
        self._c = client
        self._groups_cache: TTLCache[list[ResourceGroup]] = TTLCache(ttl=60.0)
        self._list_cache: TTLCache[list[WorkPlatform]] = TTLCache(ttl=20.0)
        self._fallback_cache: TTLCache[list[WorkPlatform]] = TTLCache(ttl=20.0)
        self._history_cache: TTLCache[list[WorkPlatform]] = TTLCache(ttl=60.0)

    # ----- listing / detail -----

    def list(
        self,
        *,
        include_halted: bool = False,
        refresh: bool = False,
        max_history_pages: int = 10,
        history_page_size: int = 50,
    ) -> builtins.list[WorkPlatform]:
        """List the user's dev envs.

        Prefer the history endpoint because it yields a reliable dev-env view.
        If history returns nothing, fall back to the active endpoint and keep
        only rows that look like real workplatform entries.
        """
        cache_key = ("active", include_halted, max_history_pages, history_page_size)
        cached = self._list_cache.get(cache_key) if not refresh else None
        if cached is not None:
            return cached
        items = self.list_history(
            all_pages=True,
            page_size=history_page_size,
            max_pages=max_history_pages,
            refresh=refresh,
        )
        if items:
            items = [
                item for item in items
                if include_halted or self._is_active_status(item.wp_status)
            ]
        else:
            items = self._list_active_fallback(include_halted=include_halted, refresh=refresh)
        self._list_cache.set(items, cache_key)
        return items

    def list_history(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        all_pages: bool = False,
        max_pages: int | None = None,
        refresh: bool = False,
    ) -> builtins.list[WorkPlatform]:
        """List the user's historical dev envs (typically includes Halt/ended)."""
        if all_pages:
            capped_pages = max(1, max_pages or 10)
            all_cache_key = ("all", page_size, capped_pages)
            cached = self._history_cache.get(all_cache_key) if not refresh else None
            if cached is not None:
                return cached
            items: builtins.list[WorkPlatform] = []
            current_page = 1
            while current_page <= capped_pages:
                page_items = self._fetch_history_page(current_page, page_size)
                if not page_items:
                    break
                items.extend(page_items)
                if len(page_items) < page_size:
                    break
                current_page += 1
            items = self._dedupe(items)
            self._history_cache.set(items, all_cache_key)
            return items

        page_cache_key = (page, page_size)
        cached = self._history_cache.get(page_cache_key) if not refresh else None
        if cached is not None:
            return cached
        items = self._fetch_history_page(page, page_size)
        self._history_cache.set(items, page_cache_key)
        return items

    def get(self, wp_id: str | WorkPlatform) -> WorkPlatform:
        """Fetch detail for a single dev env."""
        resolved_id = coerce_workplatform_id(wp_id)
        d = self._c.get(f"/api/iresource/v1/work-platform/{resolved_id}/detail")
        if not isinstance(d, dict):
            raise AiStationError(f"unexpected detail payload for {resolved_id}")
        wp = WorkPlatform.from_api(d)
        if not wp.wp_id:
            raise NotFoundError("workplatform", resolved_id)
        return wp

    def exists(self, name: str, *, refresh: bool = False) -> WorkPlatform | None:
        """Return an active dev env with this name or ``None``."""
        try:
            for w in self._lookup_candidates(
                include_halted=False,
                search_history=False,
                refresh=refresh,
                max_history_pages=1,
            ):
                if w.wp_name == name:
                    return w
        except AiStationError:
            pass
        return None

    def resolve_many(
        self,
        query: str,
        *,
        include_halted: bool = True,
        search_history: bool = True,
        refresh: bool = False,
        max_history_pages: int = 10,
    ) -> builtins.list[WorkPlatform]:
        items = self._lookup_candidates(
            include_halted=include_halted,
            search_history=search_history,
            refresh=refresh,
            max_history_pages=max_history_pages,
        )
        if not include_halted:
            items = [item for item in items if self._is_active_status(item.wp_status)]
        return _resolve_many(
            query,
            items,
            key_fns=(
                lambda item: item.wp_id,
                lambda item: item.wp_name,
            ),
        )

    def resolve(
        self,
        query: str | WorkPlatform,
        *,
        include_halted: bool = True,
        search_history: bool = True,
        refresh: bool = False,
        max_history_pages: int = 10,
    ) -> WorkPlatform:
        query_ref = coerce_workplatform_id(query) if isinstance(query, WorkPlatform) else query
        items = self._lookup_candidates(
            include_halted=include_halted,
            search_history=search_history,
            refresh=refresh,
            max_history_pages=max_history_pages,
        )
        if not include_halted:
            items = [item for item in items if self._is_active_status(item.wp_status)]
        try:
            return _resolve_one(
                query_ref,
                items,
                key_fns=(
                    lambda item: item.wp_id,
                    lambda item: item.wp_name,
                ),
                label_fn=lambda item: f"{item.wp_name} ({item.wp_id})",
                resource_type="workplatform",
            )
        except NotFoundError as local_error:
            try:
                return self.get(query_ref)
            except NotFoundError:
                raise local_error

    # ----- resource groups -----

    def list_groups(self, *, refresh: bool = False) -> builtins.list[ResourceGroup]:
        """Dev-env eligible resource groups (``groupLabel=develop``).

        Uses a dedicated query — don't reuse the generic
        :meth:`GroupsAPI.list` result because dev envs need the ``develop`` label.
        """
        if not refresh and not self._groups_cache.expired():
            cached = self._groups_cache.get()
            if cached is not None:
                return cached
        data = self._c.get(
            "/api/iresource/v1/node-group",
            params={
                "page": -1, "pageSize": -1,
                "groupStatus": 1, "groupLabel": "develop", "nodeGroup": 1,
            },
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        groups: list[ResourceGroup] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            groups.append(ResourceGroup(
                group_id=str(r.get("groupId", "")),
                group_name=str(r.get("groupName", "")),
                card_type="",       # not in this response; call nodes.list() for detail
                card_kind=str(r.get("acceleratorCardKind") or ""),
                switch_type="",
                node_count=int(r.get("nodeCount") or 0),
                total_cards=int(r.get("acceleratorCardCount") or 0),
                used_cards=int(r.get("usedAcceleratorCardCount") or 0),
                total_cpu=int(r.get("cpuCoreNum") or 0),
                total_memory_gb=0,
                node_names=[],
                raw=r,
            ))
        self._groups_cache.set(groups)
        return groups

    def resolve_group_id(self, name_or_id: str) -> str:
        """Match ``name_or_id`` against dev-env eligible groups."""
        return self.resolve_group(name_or_id).group_id

    def resolve_group(self, name_or_id: str) -> ResourceGroup:
        return _resolve_one(
            name_or_id,
            self.list_groups(),
            key_fns=(
                lambda item: item.group_id,
                lambda item: item.group_name,
            ),
            label_fn=lambda item: f"{item.group_name} ({item.group_id})",
            resource_type="dev-env group",
        )

    # ----- create / delete -----

    def rebuild_template(self, wp_id: str | WorkPlatform) -> dict[str, Any]:
        """Return the raw rebuild payload for an existing dev env.

        Very useful for replication: tweak ``wpName`` / ``command`` and submit
        to :meth:`create_raw`.
        """
        resolved_id = coerce_workplatform_id(wp_id)
        data = self._c.get(
            f"/api/iresource/v1/work-platform/{resolved_id}/rebuild",
            params={"from": 1},
        )
        return data if isinstance(data, dict) else {}

    def create(
        self,
        spec: WorkPlatformSpec,
        *,
        dry_run: bool = False,
        idempotent: bool = True,
    ) -> OperationResult[WorkPlatform]:
        """Create a dev env from a :class:`WorkPlatformSpec`.

        - ``dry_run``: return the assembled payload without calling the server
        - ``idempotent``: if a non-Halt env with the same name exists, return
          it unchanged instead of creating a duplicate
        """
        if idempotent:
            existing = self.exists(spec.name)
            if existing is not None:
                return OperationResult(
                    action="create",
                    resource_type="workplatform",
                    entity=existing,
                    target_id=existing.wp_id,
                    target_ids=[existing.wp_id],
                    reused=True,
                )
        payload = self._build_payload(spec)
        if dry_run:
            return OperationResult(
                action="create",
                resource_type="workplatform",
                payload=payload,
                raw=payload,
            )
        resp = self._c.post("/api/iresource/v1/work-platform/", json=payload)
        self.invalidate_cache()
        self._c.nodes.invalidate_cache()
        wp_id = None
        if isinstance(resp, dict):
            wp_id = resp.get("wpId") or resp.get("id")
        elif isinstance(resp, str):
            wp_id = resp
        if not wp_id:
            # Fallback: look up by name
            got = self._find_created_workplatform(spec.name)
            if got is not None:
                return OperationResult(
                    action="create",
                    resource_type="workplatform",
                    entity=got,
                    payload=payload,
                    raw=resp,
                    target_id=got.wp_id,
                    target_ids=[got.wp_id],
                    created=True,
                )
            return OperationResult(
                action="create",
                resource_type="workplatform",
                payload=payload,
                raw=resp,
                created=True,
            )
        try:
            entity: WorkPlatform | None = retry_not_found(lambda: self.get(wp_id))
        except NotFoundError:
            entity = self._find_created_workplatform(spec.name)
        return OperationResult(
            action="create",
            resource_type="workplatform",
            entity=entity,
            payload=payload,
            raw=resp,
            target_id=wp_id,
            target_ids=[wp_id],
            created=True,
        )

    def create_and_wait_ready(
        self,
        spec: WorkPlatformSpec,
        *,
        idempotent: bool = True,
        timeout: float = 600.0,
        interval: float = 5.0,
    ) -> OperationResult[WorkPlatform]:
        result = self.create(spec, idempotent=idempotent)
        result.entity = self.wait_ready(
            result.require_entity(f"created dev env but could not locate it: {spec.name}"),
            timeout=timeout,
            interval=interval,
        )
        result.waited = True
        return result

    def create_raw(self, payload: dict[str, Any]) -> OperationResult[WorkPlatform]:
        """Submit a raw payload verbatim (e.g. from :meth:`rebuild_template`)."""
        resp = self._c.post("/api/iresource/v1/work-platform/", json=payload)
        self.invalidate_cache()
        self._c.nodes.invalidate_cache()
        wp_id = None
        if isinstance(resp, dict):
            wp_id = resp.get("wpId") or resp.get("id")
        elif isinstance(resp, str):
            wp_id = resp
        entity: WorkPlatform | None = None
        if wp_id:
            try:
                entity = retry_not_found(lambda: self.get(wp_id))
            except NotFoundError:
                entity = None
        if entity is None:
            wp_name = payload.get("wpName")
            if isinstance(wp_name, str) and wp_name.strip():
                entity = self._find_created_workplatform(wp_name)
        if not wp_id and entity is None:
            raise AiStationError("dev env created but server returned no wpId")
        return OperationResult(
            action="create_raw",
            resource_type="workplatform",
            entity=entity,
            payload=payload,
            raw=resp,
            target_id=wp_id,
            target_ids=[wp_id] if wp_id else [],
            created=True,
        )

    def delete(self, wp_id: str | WorkPlatform) -> OperationResult[WorkPlatform]:
        """Stop + delete a dev env. Verified endpoint: ``DELETE /work-platform/{id}``."""
        resolved_id = coerce_workplatform_id(wp_id)
        raw = self._c.delete(f"/api/iresource/v1/work-platform/{resolved_id}")
        self.invalidate_cache()
        self._c.nodes.invalidate_cache()
        return OperationResult(
            action="delete",
            resource_type="workplatform",
            raw=raw if isinstance(raw, dict) else {},
            target_id=resolved_id,
            target_ids=[resolved_id],
        )

    # ----- ancillary actions -----

    def jupyter_url(self, wp_id: str | WorkPlatform) -> dict[str, Any]:
        """Return Jupyter access info for a running env."""
        resolved_id = coerce_workplatform_id(wp_id)
        d = self._c.get(f"/api/iresource/v1/work-platform/{resolved_id}/jupyter")
        return d if isinstance(d, dict) else {}

    def shell_url(self, wp_id: str | WorkPlatform, *, pod_id: str | None = None) -> dict[str, Any]:
        """Return shell/exec URL for the env (or one of its pods)."""
        resolved_id = coerce_workplatform_id(wp_id)
        path = (
            f"/api/iresource/v1/work-platform/{resolved_id}/pod/{pod_id}/shell"
            if pod_id
            else f"/api/iresource/v1/work-platform/{resolved_id}/shell"
        )
        d = self._c.get(path)
        return d if isinstance(d, dict) else {}

    def commit_image(
        self,
        wp_id: str | WorkPlatform,
        *,
        image_name: str,
        image_tag: str,
        pod_id: str,
        comment: str = "",
        image_type: str = "other",
    ) -> OperationResult[WorkPlatform]:
        """Commit a running pod's filesystem to a new internal image."""
        resolved_id = coerce_workplatform_id(wp_id)
        body = {
            "imageName": image_name,
            "imageTag": image_tag,
            "imageComment": comment,
            "wpId": resolved_id,
            "podId": pod_id,
            "imageType": image_type,
        }
        d = self._c.post("/api/iresource/v1/work-platform/commit-image", json=body)
        self._c.images.invalidate_cache()
        raw = d if isinstance(d, dict) else {}
        target_id = None
        for key in ("id", "taskId", "imageId"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                target_id = value
                break
        return OperationResult(
            action="commit_image",
            resource_type="workplatform",
            payload=body,
            raw=raw,
            target_id=target_id,
            target_ids=[target_id] if target_id else [resolved_id],
            extras={"workplatform_id": resolved_id},
        )

    def toggle_history_collect(
        self,
        wp_id: str | WorkPlatform,
        collected: bool,
    ) -> OperationResult[WorkPlatform]:
        """Star/unstar a history entry. Server endpoint is a PUT with
        ``isHistoryCollect = 1 | 0``."""
        resolved_id = coerce_workplatform_id(wp_id)
        d = self._c.put(
            "/api/iresource/v1/work-platform/history-collect/",
            json={"wpId": resolved_id, "isHistoryCollect": 1 if collected else 0},
        )
        self._history_cache.invalidate()
        return OperationResult(
            action="toggle_history_collect",
            resource_type="workplatform",
            raw=d if isinstance(d, dict) else {},
            target_id=resolved_id,
            target_ids=[resolved_id],
            extras={"collected": collected},
        )

    def wait_ready(
        self,
        wp_id: str | WorkPlatform,
        *,
        timeout: float = 600.0,
        interval: float = 5.0,
    ) -> WorkPlatform:
        return wait_workplatform_ready(
            self._c,
            coerce_workplatform_id(wp_id),
            timeout=timeout,
            interval=interval,
        )

    def invalidate_cache(self) -> None:
        self._list_cache.invalidate()
        self._fallback_cache.invalidate()
        self._history_cache.invalidate()

    # ----- payload builder (spec → server JSON) -----

    def _build_payload(self, spec: WorkPlatformSpec) -> dict[str, Any]:
        group_ref = coerce_resource_group_ref(spec.resource_group)
        group_id = self.resolve_group(group_ref).group_id
        account = None
        if not spec.volumes:
            account = self._c.require_user().account
        return build_workplatform_payload(
            spec,
            group_id=group_id,
            account=account,
        )

    @staticmethod
    def _dedupe(items: builtins.list[WorkPlatform]) -> builtins.list[WorkPlatform]:
        seen: set[str] = set()
        result: builtins.list[WorkPlatform] = []
        for item in items:
            if not item.wp_id or item.wp_id in seen:
                continue
            seen.add(item.wp_id)
            result.append(item)
        return result

    def _fetch_history_page(self, page: int, page_size: int) -> builtins.list[WorkPlatform]:
        data = self._c.get(
            "/api/iresource/v1/work-platform/history",
            params={"page": page, "pageSize": page_size},
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        return self._parse_workplatform_rows(rows)

    def _list_active_fallback(
        self,
        *,
        include_halted: bool,
        refresh: bool = False,
    ) -> builtins.list[WorkPlatform]:
        cache_key = ("fallback", include_halted)
        cached = self._fallback_cache.get(cache_key) if not refresh else None
        if cached is not None:
            return cached
        data = self._c.get(
            "/api/iresource/v1/work-platform/goto-train-job",
            params={"statusFlag": 0, "page": -1, "pageSize": -1},
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        items = self._parse_workplatform_rows(rows)
        if include_halted:
            self._fallback_cache.set(items, cache_key)
            return items
        filtered = [item for item in items if self._is_active_status(item.wp_status)]
        self._fallback_cache.set(filtered, cache_key)
        return filtered

    def _parse_workplatform_rows(self, rows: object) -> builtins.list[WorkPlatform]:
        items: builtins.list[WorkPlatform] = []
        if not isinstance(rows, list):
            return items
        for row in rows:
            if not isinstance(row, dict):
                continue
            if not row.get("wpId") or not row.get("wpName"):
                continue
            wp = WorkPlatform.from_api(row)
            if not wp.wp_id or not wp.wp_name:
                continue
            items.append(wp)
        return items

    @staticmethod
    def _is_active_status(status: str) -> bool:
        normalized = status.strip().lower()
        if not normalized:
            return True
        return normalized not in _TERMINAL_WP_STATUSES

    def _lookup_candidates(
        self,
        *,
        include_halted: bool,
        search_history: bool,
        refresh: bool,
        max_history_pages: int,
    ) -> builtins.list[WorkPlatform]:
        if search_history:
            history_items = self.list_history(
                    all_pages=True,
                    page_size=50,
                    max_pages=max_history_pages,
                    refresh=refresh,
                )
        else:
            history_items = []
        active_items = self._list_active_fallback(include_halted=include_halted, refresh=refresh)
        if not search_history:
            return active_items
        if include_halted:
            return self._dedupe(history_items + active_items)
        filtered_history = [item for item in history_items if self._is_active_status(item.wp_status)]
        return self._dedupe(filtered_history + active_items)

    def _find_created_workplatform(self, name: str) -> WorkPlatform | None:
        try:
            return retry_not_found(lambda: self._require_existing_workplatform(name))
        except NotFoundError:
            return None

    def _require_existing_workplatform(self, name: str) -> WorkPlatform:
        existing = self.exists(name, refresh=True)
        if existing is not None:
            return existing
        raise NotFoundError("workplatform", name)
