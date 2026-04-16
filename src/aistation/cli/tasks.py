"""Task-oriented CLI commands."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from ..errors import ValidationError
from ..specs import TaskSpec
from . import _short
from ._client import make_client
from ._error import render_and_exit
from ._output import (
    OutputFormat,
    print_json,
    print_quiet,
    print_table,
    resolve_context_output,
    resolve_short_mode,
    success,
)
from ._spec import (
    build_spec,
    ensure_min_int,
    ensure_non_negative_int,
    ensure_port_list,
    ensure_positive_float,
    load_mapping_file,
    merge_spec_mapping,
    parse_bool_text,
    parse_env_assignments,
    parse_json_object_list,
    parse_json_object_merge,
)


STATUS_MAP = {
    "running": 0,
    "unfinished": 0,
    "pending": 0,
    "finished": 3,
    "done": 3,
}

TASK_FIELD_ALIASES = {
    "group": "resource_group",
    "resourceGroup": "resource_group",
    "resource-group": "resource_group",
    "memory": "memory_gb",
    "cardKind": "card_kind",
    "mountPath": "mount_path",
    "scriptDir": "script_dir",
    "logPath": "log_path",
    "shmSize": "shm_size",
    "switchType": "switch_type",
    "imageType": "image_type",
    "imageFlag": "image_flag",
    "isElastic": "is_elastic",
    "startScript": "start_script",
    "execDir": "exec_dir",
    "nodeNames": "node_names",
    "mountPathModel": "mount_path_model",
    "logStorageName": "log_storage_name",
    "taskType": "task_type",
    "minNodes": "min_nodes",
    "rawOverrides": "raw_overrides",
}


def _task_item(task: Any, *, short_mode: bool) -> Any:
    return _short.task(task) if short_mode else task


def _pod_item(pod: Any, *, short_mode: bool) -> Any:
    return _short.pod(pod) if short_mode else pod


def _task_bundle(task: Any, pods: list[Any], *, short_mode: bool) -> dict[str, Any]:
    return {
        "item": _task_item(task, short_mode=short_mode),
        "pods": [_pod_item(pod, short_mode=short_mode) for pod in pods],
        "pod_count": len(pods),
    }


def _task_action_payload(result: Any, *, short_mode: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": result.action,
        "resource_type": result.resource_type,
        "target_id": result.target_id,
        "target_ids": result.target_ids,
        "created": result.created,
        "reused": result.reused,
        "waited": result.waited,
    }
    if result.entity is not None:
        payload["item"] = _task_item(result.entity, short_mode=short_mode)
    if result.payload is not None and (not short_mode or result.entity is None):
        payload["payload"] = result.payload
    if result.raw is not None and not short_mode:
        payload["raw"] = result.raw
    pods = result.extras.get("pods")
    if isinstance(pods, list):
        payload["pods"] = [_pod_item(pod, short_mode=short_mode) for pod in pods]
        payload["pod_count"] = len(pods)
    elif result.extras and not short_mode:
        payload["extras"] = result.extras
    return payload


def _render_task_detail_table(task: Any, pods: list[Any]) -> None:
    print_table(
        f"Task {task.name}",
        ("FIELD", "VALUE"),
        [
            ("id", task.id),
            ("status", task.status),
            ("group", task.resource_group_name),
            ("node", task.node_name or "-"),
            ("image", task.image),
            ("command", (task.command or "")[:100]),
            ("create_time", task.create_time_ms),
            ("run_time_s", task.run_time_s),
            ("status_reason", (task.status_reason or "")[:100]),
        ],
    )
    if pods:
        rows = []
        for pod in pods:
            ports = ", ".join(pod.external_urls) if pod.external_urls else "-"
            rows.append((pod.pod_name_changed, pod.pod_status, pod.node_ip, pod.pod_gpu_type, ports))
        print_table(
            "Pods",
            ("POD", "STATUS", "NODE_IP", "CARD_TYPE", "EXTERNAL_URL"),
            rows,
        )


def _render_task_action_table(title: str, data: dict[str, Any]) -> None:
    rows = [(key, value) for key, value in data.items() if value not in (None, [], {})]
    print_table(title, ("FIELD", "VALUE"), rows)


def _dedupe_tasks(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        task_id = getattr(item, "id", "")
        if not task_id or task_id in seen:
            continue
        seen.add(task_id)
        result.append(item)
    return result


def _lookup_task(client: Any, query: str, *, include_finished: bool = True) -> Any:
    try:
        return client.tasks.resolve(query, include_finished=include_finished)
    except Exception:
        if query and (query.startswith("task-") or len(query) >= 8):
            try:
                return client.tasks.get(query)
            except Exception:
                pass
        raise


def _build_task_spec(
    *,
    file: Path | None,
    name: str | None,
    resource_group: str | None,
    image: str | None,
    command: str | None,
    cards: int | None,
    cpu: int | None,
    memory_gb: int | None,
    nodes: int | None,
    card_kind: str | None,
    mount_path: str | None,
    script_dir: str | None,
    log_path: str | None,
    ports: list[int] | None,
    env_vars: list[str] | None,
    dataset_json: list[str] | None,
    model_json: list[str] | None,
    shm_size: int | None,
    switch_type: str | None,
    image_type: str | None,
    image_flag: int | None,
    elastic: str | None,
    distributed: str | None,
    emergency: str | None,
    description: str | None,
    start_script: str | None,
    exec_dir: str | None,
    parameters: str | None,
    node_names: list[str] | None,
    mount_path_model: int | None,
    log_storage_name: str | None,
    task_type: int | None,
    min_nodes: int | None,
    raw_override_json: list[str] | None,
) -> TaskSpec:
    ensure_non_negative_int(cards, option_name="--cards")
    ensure_non_negative_int(cpu, option_name="--cpu")
    ensure_non_negative_int(memory_gb, option_name="--memory-gb")
    ensure_min_int(nodes, option_name="--nodes", minimum=1)
    ensure_non_negative_int(shm_size, option_name="--shm-size")
    ensure_min_int(task_type, option_name="--task-type", minimum=0)
    if min_nodes is not None and min_nodes < -1:
        raise ValidationError(
            "--min-nodes must be >= -1",
            field_name="--min-nodes",
            err_code="SDK_CLI_BAD_SPEC_INPUT",
            err_message=f"invalid value for --min-nodes: {min_nodes}",
        )
    ensure_port_list(ports)
    base = load_mapping_file(file, resource_name="task", unwrap_keys=("task", "spec"))
    merged = merge_spec_mapping(
        base,
        overrides={
            "name": name,
            "resource_group": resource_group,
            "image": image,
            "command": command,
            "cards": cards,
            "cpu": cpu,
            "memory_gb": memory_gb,
            "nodes": nodes,
            "card_kind": card_kind,
            "mount_path": mount_path,
            "script_dir": script_dir,
            "log_path": log_path,
            "shm_size": shm_size,
            "switch_type": switch_type,
            "image_type": image_type,
            "image_flag": image_flag,
            "is_elastic": parse_bool_text(elastic, option_name="--elastic"),
            "distributed": distributed,
            "emergency": parse_bool_text(emergency, option_name="--emergency"),
            "description": description,
            "start_script": start_script,
            "exec_dir": exec_dir,
            "parameters": parameters,
            "mount_path_model": mount_path_model,
            "log_storage_name": log_storage_name,
            "task_type": task_type,
            "min_nodes": min_nodes,
        },
        dict_merges={
            "env": parse_env_assignments(env_vars),
            "raw_overrides": parse_json_object_merge(
                raw_override_json,
                option_name="--raw-override-json",
            ),
        },
        list_replacements={
            "ports": list(ports or []),
            "datasets": parse_json_object_list(dataset_json, option_name="--dataset-json"),
            "models": parse_json_object_list(model_json, option_name="--model-json"),
            "node_names": list(node_names or []),
        },
    )
    return build_spec(
        TaskSpec,
        merged,
        field_aliases=TASK_FIELD_ALIASES,
        resource_name="task",
    )


def cmd_tasks(
    ctx: typer.Context,
    status: Annotated[str, typer.Option("--status", help="running / finished / all")] = "running",
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """List my training tasks."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    normalized_status = status.strip().lower()
    if normalized_status not in {*STATUS_MAP.keys(), "all"}:
        render_and_exit(
            ValidationError(
                "--status must be running, finished, pending, unfinished, done, or all",
                field_name="--status",
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message=f"unsupported task status filter: {status}",
            ),
            output=output,
        )
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        if normalized_status == "all":
            tasks = _dedupe_tasks(client.tasks.list(status_flag=0) + client.tasks.list(status_flag=3))
        else:
            flag = STATUS_MAP[normalized_status]
            tasks = client.tasks.list(status_flag=flag)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(
            {
                "items": [_task_item(task, short_mode=short_mode) for task in tasks],
                "count": len(tasks),
                "status": status,
            }
        )
    elif ctx.obj.get("quiet"):
        print_quiet([task.id for task in tasks])
    else:
        rows = []
        for task in tasks:
            rows.append(
                (
                    task.name,
                    task.status,
                    task.resource_group_name,
                    _short.task(task)["cards"],
                    task.node_name or "-",
                    task.id[:8] + "...",
                )
            )
        print_table(
            f"Tasks ({len(tasks)})",
            ("NAME", "STATUS", "GROUP", "CARDS", "NODE", "ID"),
            rows,
        )


def cmd_task_get(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Task ID or name")],
    include_finished: Annotated[
        bool, typer.Option("--include-finished/--active-only", help="Search finished tasks too")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Show a single task's detail and pods."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        task = _lookup_task(client, query, include_finished=include_finished)
        pods = client.tasks.pods(task)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(_task_bundle(task, pods, short_mode=short_mode))
    elif ctx.obj.get("quiet"):
        print_quiet(task.id)
    else:
        _render_task_detail_table(task, pods)


def cmd_task_resolve(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Task ID, prefix, or name")],
    include_finished: Annotated[
        bool, typer.Option("--include-finished/--active-only", help="Search finished tasks too")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Resolve a task reference to one canonical task object."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        task = _lookup_task(client, query, include_finished=include_finished)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json({"query": query, "item": _task_item(task, short_mode=short_mode)})
    elif ctx.obj.get("quiet"):
        print_quiet(task.id)
    else:
        _render_task_detail_table(task, [])


def cmd_task_pods(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Task ID or name")],
    include_finished: Annotated[
        bool, typer.Option("--include-finished/--active-only", help="Search finished tasks too")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """List pods for one task."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        task = _lookup_task(client, query, include_finished=include_finished)
        pods = client.tasks.pods(task)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(
            {
                "task_id": task.id,
                "items": [_pod_item(pod, short_mode=short_mode) for pod in pods],
                "count": len(pods),
            }
        )
    elif ctx.obj.get("quiet"):
        print_quiet([pod.pod_id for pod in pods])
    else:
        rows = []
        for pod in pods:
            rows.append(
                (
                    pod.pod_name_changed,
                    pod.pod_status,
                    pod.node_name or "-",
                    pod.node_ip or "-",
                    ", ".join(pod.external_urls) if pod.external_urls else "-",
                )
            )
        print_table(
            f"Task Pods ({len(pods)})",
            ("POD", "STATUS", "NODE", "NODE_IP", "EXTERNAL_URL"),
            rows,
        )


def cmd_task_logs(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Task ID or name")],
    pod: Annotated[str | None, typer.Option("--pod", help="Specific pod name")] = None,
    include_finished: Annotated[
        bool, typer.Option("--include-finished/--active-only", help="Search finished tasks too")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Read task logs."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    _ = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        task = _lookup_task(client, query, include_finished=include_finished)
        log = client.tasks.read_log(task, pod_name=pod)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json({"task_id": task.id, "pod": pod, "log": log})
    else:
        print(log)


def cmd_task_wait(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Task ID or name")],
    for_: Annotated[str, typer.Option("--for", help="running / pods")] = "running",
    include_finished: Annotated[
        bool, typer.Option("--include-finished/--active-only", help="Search finished tasks too")
    ] = True,
    timeout: Annotated[float, typer.Option("--timeout", help="Wait timeout in seconds")] = 600.0,
    interval: Annotated[float, typer.Option("--interval", help="Polling interval in seconds")] = 5.0,
    pod_timeout: Annotated[
        float, typer.Option("--pod-timeout", help="Pod wait timeout in seconds")
    ] = 120.0,
    pod_interval: Annotated[
        float, typer.Option("--pod-interval", help="Pod polling interval in seconds")
    ] = 3.0,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Wait until a task reaches a desired state."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    condition = for_.strip().lower()
    if condition not in {"running", "pods"}:
        render_and_exit(
            ValidationError(
                "--for must be running or pods",
                field_name="--for",
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message=f"unsupported task wait condition: {for_}",
            ),
            output=output,
        )
    try:
        ensure_positive_float(timeout, option_name="--timeout")
        ensure_positive_float(interval, option_name="--interval")
        ensure_positive_float(pod_timeout, option_name="--pod-timeout")
        ensure_positive_float(pod_interval, option_name="--pod-interval")
        client = make_client(
            require_token=True,
            allow_live_login=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        task = _lookup_task(client, query, include_finished=include_finished)
        if condition == "running":
            task = client.tasks.wait_running(task, timeout=timeout, interval=interval)
            pods: list[Any] = []
        else:
            pods = client.tasks.wait_pods(task, timeout=pod_timeout, interval=pod_interval)
            task = client.tasks.get(task.id)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        payload = {"target": task.id, "condition": condition}
        if condition == "running":
            payload["item"] = _task_item(task, short_mode=short_mode)
        else:
            payload.update(_task_bundle(task, pods, short_mode=short_mode))
        print_json(payload)
    elif ctx.obj.get("quiet"):
        print_quiet(task.id)
    else:
        if condition == "running":
            _render_task_action_table(
                "Task Wait",
                {"condition": condition, "task_id": task.id, "status": task.status, "name": task.name},
            )
        else:
            _render_task_detail_table(task, pods)


def cmd_task_create(
    ctx: typer.Context,
    file: Annotated[Path | None, typer.Option("--file", "-f", help="JSON/YAML task spec file")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Task name")] = None,
    resource_group: Annotated[
        str | None, typer.Option("--group", "--resource-group", help="Task resource group")
    ] = None,
    image: Annotated[str | None, typer.Option("--image", help="Image reference")] = None,
    command: Annotated[str | None, typer.Option("--command", help="Container command")] = None,
    cards: Annotated[int | None, typer.Option("--cards", help="Accelerator cards")] = None,
    cpu: Annotated[int | None, typer.Option("--cpu", help="CPU cores")] = None,
    memory_gb: Annotated[int | None, typer.Option("--memory-gb", help="Memory in GB")] = None,
    nodes: Annotated[int | None, typer.Option("--nodes", help="Worker node count")] = None,
    card_kind: Annotated[str | None, typer.Option("--card-kind", help="GPU or CPU")] = None,
    mount_path: Annotated[str | None, typer.Option("--mount-path", help="Workspace mount path")] = None,
    script_dir: Annotated[str | None, typer.Option("--script-dir", help="Script directory")] = None,
    log_path: Annotated[str | None, typer.Option("--log-path", help="Persistent log path")] = None,
    ports: Annotated[list[int] | None, typer.Option("--port", help="Expose container port; repeatable")] = None,
    env_vars: Annotated[list[str] | None, typer.Option("--env", help="KEY=VALUE; repeatable")] = None,
    dataset_json: Annotated[
        list[str] | None, typer.Option("--dataset-json", help="Dataset mount object; repeatable")
    ] = None,
    model_json: Annotated[
        list[str] | None, typer.Option("--model-json", help="Model object; repeatable")
    ] = None,
    shm_size: Annotated[int | None, typer.Option("--shm-size", help="Shared memory size")] = None,
    switch_type: Annotated[str | None, typer.Option("--switch-type", help="Switch type")] = None,
    image_type: Annotated[str | None, typer.Option("--image-type", help="Image type")] = None,
    image_flag: Annotated[int | None, typer.Option("--image-flag", help="Image flag")] = None,
    elastic: Annotated[str | None, typer.Option("--elastic", help="true or false")] = None,
    distributed: Annotated[
        str | None, typer.Option("--distributed", help="node / mpi / ps_worker / ...")
    ] = None,
    emergency: Annotated[str | None, typer.Option("--emergency", help="true or false")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Task description")] = None,
    start_script: Annotated[str | None, typer.Option("--start-script", help="Start script")] = None,
    exec_dir: Annotated[str | None, typer.Option("--exec-dir", help="Execution directory")] = None,
    parameters: Annotated[str | None, typer.Option("--parameters", help="Additional parameters")] = None,
    node_names: Annotated[
        list[str] | None, typer.Option("--node-name", help="Worker node name; repeatable")
    ] = None,
    mount_path_model: Annotated[
        int | None, typer.Option("--mount-path-model", help="Mount path model")
    ] = None,
    log_storage_name: Annotated[
        str | None, typer.Option("--log-storage-name", help="Log storage name")
    ] = None,
    task_type: Annotated[int | None, typer.Option("--task-type", help="Backend task type")] = None,
    min_nodes: Annotated[int | None, typer.Option("--min-nodes", help="Elastic min nodes")] = None,
    raw_override_json: Annotated[
        list[str] | None, typer.Option("--raw-override-json", help="Raw payload override object; repeatable")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Build payload only")] = False,
    validate: Annotated[bool, typer.Option("--validate/--no-validate", help="Client-side validate spec")] = True,
    precheck: Annotated[bool, typer.Option("--precheck/--no-precheck", help="Server-side precheck")] = True,
    idempotent: Annotated[
        bool, typer.Option("--idempotent/--no-idempotent", help="Reuse same-name active task")
    ] = True,
    wait: Annotated[bool, typer.Option("--wait", help="Wait until task is running")] = False,
    wait_for_pods: Annotated[
        bool, typer.Option("--wait-pods", help="Create then wait until pods are ready")
    ] = False,
    wait_timeout: Annotated[
        float, typer.Option("--wait-timeout", help="Running wait timeout in seconds")
    ] = 600.0,
    wait_interval: Annotated[
        float, typer.Option("--wait-interval", help="Running poll interval in seconds")
    ] = 5.0,
    pod_timeout: Annotated[
        float, typer.Option("--pod-timeout", help="Pod wait timeout in seconds")
    ] = 120.0,
    pod_interval: Annotated[
        float, typer.Option("--pod-interval", help="Pod poll interval in seconds")
    ] = 3.0,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Create a training task from CLI flags or a spec file."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    wait_requested = wait or wait_for_pods
    if dry_run and (wait or wait_for_pods):
        render_and_exit(
            ValidationError(
                "--dry-run cannot be combined with --wait/--wait-pods",
                field_name="--dry-run",
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message="cannot wait in dry-run mode",
            ),
            output=output,
        )
    if wait_requested:
        try:
            ensure_positive_float(wait_timeout, option_name="--wait-timeout")
            ensure_positive_float(wait_interval, option_name="--wait-interval")
            if wait_for_pods:
                ensure_positive_float(pod_timeout, option_name="--pod-timeout")
                ensure_positive_float(pod_interval, option_name="--pod-interval")
        except Exception as exc:  # noqa: BLE001
            render_and_exit(exc, output=output)
    try:
        spec = _build_task_spec(
            file=file,
            name=name,
            resource_group=resource_group,
            image=image,
            command=command,
            cards=cards,
            cpu=cpu,
            memory_gb=memory_gb,
            nodes=nodes,
            card_kind=card_kind,
            mount_path=mount_path,
            script_dir=script_dir,
            log_path=log_path,
            ports=ports,
            env_vars=env_vars,
            dataset_json=dataset_json,
            model_json=model_json,
            shm_size=shm_size,
            switch_type=switch_type,
            image_type=image_type,
            image_flag=image_flag,
            elastic=elastic,
            distributed=distributed,
            emergency=emergency,
            description=description,
            start_script=start_script,
            exec_dir=exec_dir,
            parameters=parameters,
            node_names=node_names,
            mount_path_model=mount_path_model,
            log_storage_name=log_storage_name,
            task_type=task_type,
            min_nodes=min_nodes,
            raw_override_json=raw_override_json,
        )
        client = make_client(
            require_token=True,
            allow_live_login=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        if dry_run:
            result = client.tasks.create(
                spec,
                dry_run=True,
                validate=validate,
                precheck=precheck,
                idempotent=idempotent,
            )
        elif wait_requested:
            result = client.tasks.create_and_wait(
                spec,
                validate=validate,
                precheck=precheck,
                idempotent=idempotent,
                timeout=wait_timeout,
                interval=wait_interval,
                wait_for_pods=wait_for_pods,
                pod_timeout=pod_timeout,
                pod_interval=pod_interval,
            )
        else:
            result = client.tasks.create(
                spec,
                validate=validate,
                precheck=precheck,
                idempotent=idempotent,
            )
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(_task_action_payload(result, short_mode=short_mode))
    elif ctx.obj.get("quiet"):
        print_quiet(result.target_id or (result.entity.id if result.entity is not None else None))
    else:
        summary = {
            "task_id": result.target_id or (result.entity.id if result.entity is not None else None),
            "name": result.entity.name if result.entity is not None else spec.name,
            "status": result.entity.status if result.entity is not None else None,
            "created": result.created,
            "reused": result.reused,
            "waited": result.waited,
            "dry_run": dry_run,
        }
        if dry_run:
            _render_task_action_table("Task Dry Run", summary)
        else:
            success("Task request completed")
            _render_task_action_table("Task Create", summary)


def cmd_task_delete(
    ctx: typer.Context,
    queries: Annotated[list[str], typer.Argument(help="One or more task IDs or names")],
    include_finished: Annotated[
        bool, typer.Option("--include-finished/--active-only", help="Resolve against finished tasks too")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Delete one or more task records."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            allow_live_login=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        if not queries:
            raise ValidationError(
                "at least one task reference is required",
                field_name="query",
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message="missing task delete target",
            )
        tasks = _dedupe_tasks(
            [_lookup_task(client, query, include_finished=include_finished) for query in queries]
        )
        result = client.tasks.delete(tasks if len(tasks) > 1 else tasks[0])
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        payload = _task_action_payload(result, short_mode=short_mode)
        payload["count"] = len(result.target_ids)
        print_json(payload)
    elif ctx.obj.get("quiet"):
        print_quiet(result.target_ids)
    else:
        success("Task delete request completed")
        _render_task_action_table(
            "Task Delete",
            {"target_ids": ", ".join(result.target_ids), "count": len(result.target_ids)},
        )


def cmd_task_stop(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Task ID or name")],
    include_finished: Annotated[
        bool, typer.Option("--include-finished/--active-only", help="Resolve against finished tasks too")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Stop a running task."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            allow_live_login=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        task = _lookup_task(client, query, include_finished=include_finished)
        result = client.tasks.stop(task)
        result.entity = task
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(_task_action_payload(result, short_mode=short_mode))
    elif ctx.obj.get("quiet"):
        print_quiet(result.target_id)
    else:
        success("Task stop request completed")
        _render_task_action_table(
            "Task Stop",
            {"task_id": result.target_id, "name": task.name, "status": task.status},
        )
