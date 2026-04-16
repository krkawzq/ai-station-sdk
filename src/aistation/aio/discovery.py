from __future__ import annotations

import uuid
from dataclasses import replace

from ..discovery import (
    DiscoveryReport,
    DiscoveryStep,
    _FIELD_DEFAULTS,
    _FIELD_RE,
    _RANGE_RULE_RE,
    _REGEX_RULE_RE,
    _first_regex_alternative,
    _try_update_config,
)
from ..errors import AiStationError, TransportError
from ..specs import TaskSpec
from .client import AsyncAiStationClient


async def discover_payload_requirements(
    client: AsyncAiStationClient,
    spec: TaskSpec,
    *,
    max_iterations: int = 15,
    name_prefix: str = "sdkauto",
    auto_delete_created: bool = True,
    verbose: bool = False,
    dry_validate: bool = True,
    submit_timeout: float = 20.0,
) -> DiscoveryReport:
    probe_name = f"{name_prefix}{uuid.uuid4().hex[:8]}"
    safe_spec = replace(spec, name=probe_name)

    payload = await client.tasks._build_payload(safe_spec)
    steps: list[DiscoveryStep] = []
    constraints: dict[str, str] = {}
    missing: list[str] = []

    success = False
    response: dict[str, object] | None = None
    created_id: str | None = None
    endpoint = "/api/iresource/v1/train/check-resources" if dry_validate else "/api/iresource/v1/train"

    for iteration in range(1, max_iterations + 1):
        try:
            body = await client._raw_request(
                "POST",
                endpoint,
                json=payload,
                timeout=submit_timeout,
            )
        except TransportError as exc:
            steps.append(
                DiscoveryStep(
                    iteration=iteration,
                    err_code="TRANSPORT",
                    err_message=str(exc),
                    action="give_up",
                    field=None,
                )
            )
            response = {"flag": False, "errCode": "TRANSPORT", "errMessage": str(exc)}
            break
        response = body

        if body.get("flag"):
            success = True
            res_data = body.get("resData") if isinstance(body.get("resData"), dict) else None
            if res_data:
                for key in ("id", "taskId", "jobId", "trainId"):
                    value = res_data.get(key)
                    if isinstance(value, str) and value:
                        created_id = value
                        break
            steps.append(
                DiscoveryStep(
                    iteration=iteration,
                    err_code=None,
                    err_message=None,
                    action="accepted",
                    field=None,
                )
            )
            break

        code = str(body.get("errCode") or "")
        message = str(body.get("errMessage") or "")
        if verbose:
            print(f"[discover iter {iteration}] code={code}  msg={message[:180]}")

        match = _FIELD_RE.search(message)
        field_name = match.group(1) if match else None

        is_not_null = "NOT_NULL_ILLEGAL" in code
        is_format = "FORMAT_ILLEGAL" in code or "FRAMEWORK_ILLEGAL" in code
        is_range = "OUT_OF_RANGE" in code or "越界" in message
        is_cross = ("LT_" in code) or ("必须大于等于" in message) or ("必须小于等于" in message)

        regex_match = _REGEX_RULE_RE.search(message)
        if regex_match and field_name:
            constraints[field_name] = regex_match.group(1)

        action = "give_up"
        applied: object = None

        if is_not_null and field_name:
            if field_name not in missing:
                missing.append(field_name)
            applied = _FIELD_DEFAULTS.get(field_name, "")
            payload[field_name] = applied
            action = "fix_missing"

        elif is_format and field_name and regex_match:
            applied = _first_regex_alternative(regex_match.group(1))
            if applied is not None:
                payload[field_name] = applied
                action = "fix_regex"

        elif is_range and field_name:
            range_match = _RANGE_RULE_RE.search(message)
            if range_match:
                lo, hi = int(range_match.group(1)), int(range_match.group(2))
                applied = max(lo, min(hi, 1))
                constraints[field_name] = f"{lo}-{hi}"
            else:
                applied = 1
            if field_name in payload:
                payload[field_name] = applied
            else:
                _try_update_config(payload, field_name, applied)
            action = "fix_range"

        elif is_cross and "memory" in message and "shm_size" in message.lower():
            shm = int(payload.get("shmSize") or 1)
            _try_update_config(payload, "memory", max(shm * 2, 2))
            action = "fix_cross_mem_shm"

        elif code == "IRESOURCE_DUPLICATED_ACCOUNT_MOUNT_PATH":
            user = client.user or await client.require_user()
            payload["mountDir"] = f"/{user.account}/{probe_name}"
            action = "fix_mount_path"

        elif code == "IRESOURCE_EXECUTION_DIRECTORY_ERROR":
            payload["execDir"] = ""
            action = "fix_exec_dir"

        elif code == "IRESOURCE_GPU_NUM_OUT_OF_RESOURCE_GROUP_LIMIT":
            if "加速卡个数大于等于1" in message or "大于等于1" in message:
                _try_update_config(payload, "acceleratorCardNum", 1)
                action = "fix_gpu_min_card"
            elif "等于0" in message or "必须为0" in message:
                _try_update_config(payload, "acceleratorCardNum", 0)
                action = "fix_cpu_zero_card"

        steps.append(
            DiscoveryStep(
                iteration=iteration,
                err_code=code,
                err_message=message,
                action=action,
                field=field_name,
                applied_value=applied,
            )
        )
        if action == "give_up":
            break

    if success and created_id and auto_delete_created:
        try:
            await client.tasks.delete(created_id)
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
