"""Auto-discovery of task-submit payload constraints.

The AI Station server echoes structured Chinese error messages that name the
offending field and often include the validation regex or range. We parse those
messages, apply heuristic fixes, resubmit, and report what we learned.

Intended use: a Skill or CLI user constructs a rough ``TaskSpec``; the skill
calls :func:`discover_payload_requirements` to iteratively correct it against
the live server, then either submits the returned working payload or shows the
report to the user for manual review.

Safety:
- Every iteration is a real POST against ``/api/iresource/v1/train``, which can
  create a task on the final successful iteration. The caller chooses via
  ``auto_delete_created`` whether to clean up automatically.
- ``max_iterations`` bounds server traffic.
- A unique name prefix is generated so side-effects are easy to identify.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .errors import AiStationError, TransportError

if TYPE_CHECKING:
    from .client import AiStationClient
    from .specs import TaskSpec


# ---------- error message parsers ----------
# Match Chinese 入参[中文字段名(camelFieldName)] ...
_FIELD_RE = re.compile(r"入参\[[^()（）]*[(（](\w+)[)）]\]")
# Regex constraint inside error messages, e.g. "不满足规则：^ib|ether|...$"
_REGEX_RULE_RE = re.compile(r"不满足规则[：:]\s*(\^[^\s，,]+?\$)")
# Human-readable numeric range "范围为0-500"
_RANGE_RULE_RE = re.compile(r"范围为\s*(\d+)\s*[-~]\s*(\d+)")


# ---------- heuristic default values keyed by field name ----------
# Picked to satisfy the strictest observed constraints. These are starting
# points; the loop may override them when regex/range clues become available.
_FIELD_DEFAULTS: dict[str, Any] = {
    # booleans (server rejects null; False is safest)
    "distFlag": False,
    "mpiFlag": False,
    "emergencyFlag": False,
    "isElastic": False,
    "isHistoryCollect": 0,
    # integers
    "imageFlag": 0,
    "enUpdateDataSet": 0,
    "taskType": 1,
    "shmSize": 1,
    "endTaskWay": 1,
    "timeoutFlag": 0,
    # strings
    "type": "other",
    "imageType": "other",
    "acceleratorCardKind": "GPU",
    "switchType": "ib",
    # lists/dicts
    "commandScriptList": [],
    "jobVolume": [],
    "env": None,
    "models": None,
}


@dataclass
class DiscoveryStep:
    """One iteration of probe / fix."""
    iteration: int
    err_code: str | None
    err_message: str | None
    action: str                  # "fix_missing" / "fix_regex" / "fix_range" / "give_up"
    field: str | None = None
    applied_value: Any = None


@dataclass
class DiscoveryReport:
    """Result of an auto-discovery session."""
    success: bool
    iterations: int
    steps: list[DiscoveryStep]
    final_payload: dict[str, Any]
    final_response: dict[str, Any] | None
    created_task_id: str | None
    constraints: dict[str, str] = field(default_factory=dict)   # field → regex/range text
    missing_fields: list[str] = field(default_factory=list)


def discover_payload_requirements(
    client: "AiStationClient",
    spec: "TaskSpec",
    *,
    max_iterations: int = 15,
    name_prefix: str = "sdkauto",
    auto_delete_created: bool = True,
    verbose: bool = False,
    dry_validate: bool = True,
    submit_timeout: float = 20.0,
) -> DiscoveryReport:
    """Iteratively refine the payload from ``spec`` against the live server.

    If ``dry_validate=True`` (default), uses ``/train/check-resources`` which
    validates the payload without creating a task — the safe choice for
    discovery. When ``dry_validate=False`` it uses the real submission endpoint,
    which WILL create a task on the final successful iteration (cleaned up if
    ``auto_delete_created=True``).

    The ``spec.name`` is overridden with a unique probe name to keep any
    side-effects identifiable.
    """
    from .tasks import TasksAPI  # local import to avoid cycles
    tasks_api: TasksAPI = client.tasks

    probe_name = f"{name_prefix}{uuid.uuid4().hex[:8]}"
    # Clone the spec and replace name with probe-unique value
    from dataclasses import replace
    safe_spec = replace(spec, name=probe_name)

    payload = tasks_api._build_payload(safe_spec)
    steps: list[DiscoveryStep] = []
    constraints: dict[str, str] = {}
    missing: list[str] = []

    success = False
    response: dict[str, Any] | None = None
    created_id: str | None = None
    endpoint = "/api/iresource/v1/train/check-resources" if dry_validate else "/api/iresource/v1/train"

    for i in range(1, max_iterations + 1):
        try:
            body = client._raw_request(
                "POST", endpoint,
                json=payload, timeout=submit_timeout,
            )
        except TransportError as e:
            steps.append(DiscoveryStep(
                iteration=i, err_code="TRANSPORT", err_message=str(e),
                action="give_up", field=None,
            ))
            response = {"flag": False, "errCode": "TRANSPORT", "errMessage": str(e)}
            break
        response = body

        if body.get("flag"):
            success = True
            rd = body.get("resData") if isinstance(body.get("resData"), dict) else None
            if rd:
                for k in ("id", "taskId", "jobId", "trainId"):
                    if rd.get(k):
                        created_id = rd[k]
                        break
            steps.append(DiscoveryStep(
                iteration=i, err_code=None, err_message=None,
                action="accepted", field=None,
            ))
            break

        code = str(body.get("errCode") or "")
        msg = str(body.get("errMessage") or "")
        if verbose:
            print(f"[discover iter {i}] code={code}  msg={msg[:180]}")

        # Extract field in error
        m = _FIELD_RE.search(msg)
        field_name = m.group(1) if m else None

        # Detect specific shapes
        is_not_null = "NOT_NULL_ILLEGAL" in code
        is_format   = "FORMAT_ILLEGAL" in code or "FRAMEWORK_ILLEGAL" in code
        is_range    = "OUT_OF_RANGE" in code or "越界" in msg
        is_cross    = ("LT_" in code) or ("必须大于等于" in msg) or ("必须小于等于" in msg)

        # Locate & store the regex constraint if present
        rm = _REGEX_RULE_RE.search(msg)
        if rm and field_name:
            constraints[field_name] = rm.group(1)

        action = "give_up"
        applied: Any = None

        if is_not_null and field_name:
            if field_name not in missing:
                missing.append(field_name)
            applied = _FIELD_DEFAULTS.get(field_name, "")
            payload[field_name] = applied
            action = "fix_missing"

        elif is_format and field_name and rm:
            applied = _first_regex_alternative(rm.group(1))
            if applied is not None:
                payload[field_name] = applied
                action = "fix_regex"

        elif is_range and field_name:
            # Try extracting range from message, else clamp to 1
            rr = _RANGE_RULE_RE.search(msg)
            if rr:
                lo, hi = int(rr.group(1)), int(rr.group(2))
                # pick a safe mid-ish value
                applied = max(lo, min(hi, 1))
                # store constraint
                constraints[field_name] = f"{lo}-{hi}"
            else:
                applied = 1
            # Apply to payload top-level first, then try config.worker
            if field_name in payload:
                payload[field_name] = applied
            else:
                _try_update_config(payload, field_name, applied)
            action = "fix_range"

        elif is_cross and "memory" in msg and "shm_size" in msg.lower():
            # memory must be >= shm_size * 2
            shm = int(payload.get("shmSize") or 1)
            _try_update_config(payload, "memory", max(shm * 2, 2))
            action = "fix_cross_mem_shm"

        elif code == "IRESOURCE_DUPLICATED_ACCOUNT_MOUNT_PATH":
            # mount path equals account name; set to subpath
            user = client.user or client.require_user()
            payload["mountDir"] = f"/{user.account}/{probe_name}"
            action = "fix_mount_path"

        elif code == "IRESOURCE_EXECUTION_DIRECTORY_ERROR":
            payload["execDir"] = ""
            action = "fix_exec_dir"

        elif code == "IRESOURCE_GPU_NUM_OUT_OF_RESOURCE_GROUP_LIMIT":
            # GPU group wants >= 1 card; CPU group wants = 0
            if "加速卡个数大于等于1" in msg or "大于等于1" in msg:
                _try_update_config(payload, "acceleratorCardNum", 1)
                action = "fix_gpu_min_card"
            elif "等于0" in msg or "必须为0" in msg:
                _try_update_config(payload, "acceleratorCardNum", 0)
                action = "fix_cpu_zero_card"

        # End of heuristics: if nothing applied, give up
        steps.append(DiscoveryStep(
            iteration=i, err_code=code, err_message=msg,
            action=action, field=field_name, applied_value=applied,
        ))
        if action == "give_up":
            break

    # Cleanup
    if success and created_id and auto_delete_created:
        try:
            client.tasks.delete(created_id)
        except AiStationError:
            pass

    return DiscoveryReport(
        success=success,
        iterations=len(steps),
        steps=steps,
        final_payload=payload,
        final_response=response,
        created_task_id=created_id,
        constraints=constraints,
        missing_fields=missing,
    )


# ---------- helpers ----------

def _first_regex_alternative(pattern: str) -> str | None:
    """Given a regex like '^a|b|c$' return 'a'."""
    inner = pattern.strip()
    if inner.startswith("^"):
        inner = inner[1:]
    if inner.endswith("$"):
        inner = inner[:-1]
    if "|" in inner:
        return inner.split("|", 1)[0]
    return inner or None


def _try_update_config(payload: dict[str, Any], key: str, value: Any) -> None:
    """Update a field either at the top level or inside the stringified
    ``config.worker`` / ``config.master`` etc.
    """
    if key in payload:
        payload[key] = value
        return
    raw_cfg = payload.get("config")
    if not isinstance(raw_cfg, str):
        return
    try:
        cfg = json.loads(raw_cfg)
    except json.JSONDecodeError:
        return
    changed = False
    for role in ("worker", "master", "ps", "server"):
        block = cfg.get(role)
        if isinstance(block, dict) and key in {"cpuNum", "memory", "acceleratorCardNum", "nodeNum", "minNodeNum"}:
            mapping = {"cpu": "cpuNum", "memory": "memory", "acceleratorCardNum": "acceleratorCardNum",
                       "nodeNum": "nodeNum", "minNodeNum": "minNodeNum", "cpuNum": "cpuNum"}
            real_key = mapping.get(key, key)
            block[real_key] = value
            changed = True
    if changed:
        payload["config"] = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
