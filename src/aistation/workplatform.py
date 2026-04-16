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

from .builders.workplatform_payloads import build_workplatform_payload
from .cache import TTLCache
from .errors import AiStationError
from .modeling.resources import ResourceGroup
from .modeling.workplatforms import WorkPlatform
from .specs import WorkPlatformSpec

if TYPE_CHECKING:
    from .client import AiStationClient


# Known enum values empirically observed from the server's error messages.
WP_TYPES = ("COMMON_WP",)  # server enum includes PROJECT_* variants we haven't tested


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
        wp = client.workplatforms.create(spec)
        print(wp.wp_id, wp.wp_status)
        # ... work ...
        client.workplatforms.delete(wp.wp_id)
    """

    def __init__(self, client: AiStationClient) -> None:
        self._c = client
        self._groups_cache: TTLCache[list[ResourceGroup]] = TTLCache(ttl=60.0)
        self._list_cache: TTLCache[list[WorkPlatform]] = TTLCache(ttl=20.0)
        self._history_cache: TTLCache[list[WorkPlatform]] = TTLCache(ttl=60.0)

    # ----- listing / detail -----

    def list(self, *, include_halted: bool = False) -> list[WorkPlatform]:
        """List the user's dev envs.

        NOTE: the server currently returns running/pending training tasks from
        ``/work-platform/goto-train-job`` — not dev envs — so the result of
        this call is a mix. For reliable dev-env listing use
        :meth:`list_history` + filter by ``wpStatus``.
        """
        cache_key = ("active", include_halted)
        cached = self._list_cache.get(cache_key)
        if cached is not None:
            return cached
        status_flag = 0  # 0 = not-finished
        data = self._c.get(
            "/api/iresource/v1/work-platform/goto-train-job",
            params={"statusFlag": status_flag, "page": -1, "pageSize": -1},
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        items = [WorkPlatform.from_api(r) for r in rows if isinstance(r, dict)]
        if not include_halted:
            items = [w for w in items if w.wp_status != "Halt"]
        self._list_cache.set(items, cache_key)
        return items

    def list_history(self, *, page: int = 1, page_size: int = 50) -> builtins.list[WorkPlatform]:
        """List the user's historical dev envs (typically includes Halt/ended)."""
        cache_key = (page, page_size)
        cached = self._history_cache.get(cache_key)
        if cached is not None:
            return cached
        data = self._c.get(
            "/api/iresource/v1/work-platform/history",
            params={"page": page, "pageSize": page_size},
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        items = [WorkPlatform.from_api(r) for r in rows if isinstance(r, dict)]
        self._history_cache.set(items, cache_key)
        return items

    def get(self, wp_id: str) -> WorkPlatform:
        """Fetch detail for a single dev env."""
        d = self._c.get(f"/api/iresource/v1/work-platform/{wp_id}/detail")
        if not isinstance(d, dict):
            raise AiStationError(f"unexpected detail payload for {wp_id}")
        return WorkPlatform.from_api(d)

    def exists(self, name: str) -> WorkPlatform | None:
        """Return an active dev env with this name or ``None``."""
        try:
            for w in self.list():
                if w.wp_name == name:
                    return w
        except AiStationError:
            pass
        return None

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
        for g in self.list_groups():
            if g.group_id == name_or_id or g.group_name == name_or_id:
                return g.group_id
        raise ValueError(
            f"dev-env group not found: {name_or_id!r} "
            "(must be a group with groupLabel=develop)"
        )

    # ----- create / delete -----

    def rebuild_template(self, wp_id: str) -> dict[str, Any]:
        """Return the raw rebuild payload for an existing dev env.

        Very useful for replication: tweak ``wpName`` / ``command`` and submit
        to :meth:`create_raw`.
        """
        data = self._c.get(
            f"/api/iresource/v1/work-platform/{wp_id}/rebuild",
            params={"from": 1},
        )
        return data if isinstance(data, dict) else {}

    def create(
        self,
        spec: WorkPlatformSpec,
        *,
        dry_run: bool = False,
        idempotent: bool = True,
    ) -> WorkPlatform | dict[str, Any]:
        """Create a dev env from a :class:`WorkPlatformSpec`.

        - ``dry_run``: return the assembled payload without calling the server
        - ``idempotent``: if a non-Halt env with the same name exists, return
          it unchanged instead of creating a duplicate
        """
        if idempotent:
            existing = self.exists(spec.name)
            if existing is not None:
                return existing
        payload = self._build_payload(spec)
        if dry_run:
            return payload
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
            got = self.exists(spec.name)
            if got is not None:
                return got
            raise AiStationError(f"created dev env but could not locate it: {spec.name}")
        return self.get(wp_id)

    def create_raw(self, payload: dict[str, Any]) -> WorkPlatform:
        """Submit a raw payload verbatim (e.g. from :meth:`rebuild_template`)."""
        resp = self._c.post("/api/iresource/v1/work-platform/", json=payload)
        self.invalidate_cache()
        self._c.nodes.invalidate_cache()
        wp_id = None
        if isinstance(resp, dict):
            wp_id = resp.get("wpId") or resp.get("id")
        elif isinstance(resp, str):
            wp_id = resp
        if not wp_id:
            raise AiStationError("dev env created but server returned no wpId")
        return self.get(wp_id)

    def delete(self, wp_id: str) -> None:
        """Stop + delete a dev env. Verified endpoint: ``DELETE /work-platform/{id}``."""
        self._c.delete(f"/api/iresource/v1/work-platform/{wp_id}")
        self.invalidate_cache()
        self._c.nodes.invalidate_cache()

    # ----- ancillary actions -----

    def jupyter_url(self, wp_id: str) -> dict[str, Any]:
        """Return Jupyter access info for a running env."""
        d = self._c.get(f"/api/iresource/v1/work-platform/{wp_id}/jupyter")
        return d if isinstance(d, dict) else {}

    def shell_url(self, wp_id: str, *, pod_id: str | None = None) -> dict[str, Any]:
        """Return shell/exec URL for the env (or one of its pods)."""
        path = (
            f"/api/iresource/v1/work-platform/{wp_id}/pod/{pod_id}/shell"
            if pod_id
            else f"/api/iresource/v1/work-platform/{wp_id}/shell"
        )
        d = self._c.get(path)
        return d if isinstance(d, dict) else {}

    def commit_image(
        self,
        wp_id: str,
        *,
        image_name: str,
        image_tag: str,
        pod_id: str,
        comment: str = "",
        image_type: str = "other",
    ) -> dict[str, Any]:
        """Commit a running pod's filesystem to a new internal image."""
        body = {
            "imageName": image_name,
            "imageTag": image_tag,
            "imageComment": comment,
            "wpId": wp_id,
            "podId": pod_id,
            "imageType": image_type,
        }
        d = self._c.post("/api/iresource/v1/work-platform/commit-image", json=body)
        self._c.images.invalidate_cache()
        return d if isinstance(d, dict) else {}

    def toggle_history_collect(self, wp_id: str, collected: bool) -> dict[str, Any]:
        """Star/unstar a history entry. Server endpoint is a PUT with
        ``isHistoryCollect = 1 | 0``."""
        d = self._c._request_with_retry(
            "PUT",
            "/api/iresource/v1/work-platform/history-collect/",
            json={"wpId": wp_id, "isHistoryCollect": 1 if collected else 0},
        )
        self._history_cache.invalidate()
        return d if isinstance(d, dict) else {}

    def invalidate_cache(self) -> None:
        self._list_cache.invalidate()
        self._history_cache.invalidate()

    # ----- payload builder (spec → server JSON) -----

    def _build_payload(self, spec: WorkPlatformSpec) -> dict[str, Any]:
        group_id = self.resolve_group_id(spec.resource_group)
        account = None
        if not spec.volumes:
            account = self._c.require_user().account
        return build_workplatform_payload(
            spec,
            group_id=group_id,
            account=account,
        )
