"""Read-only task subcommands."""
from __future__ import annotations

from typing import Annotated

import typer

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
)


STATUS_MAP = {
    "running": 0,
    "unfinished": 0,
    "pending": 0,
    "finished": 3,
    "done": 3,
}


def cmd_tasks(
    ctx: typer.Context,
    status: Annotated[str, typer.Option("--status", help="running / finished / all")] = "running",
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """List my training tasks."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        if status == "all":
            tasks = client.tasks.list(status_flag=0) + client.tasks.list(status_flag=3)
        else:
            flag = STATUS_MAP.get(status.lower(), 0)
            tasks = client.tasks.list(status_flag=flag)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json([_short.task(t) for t in tasks] if short_mode else tasks)
    elif ctx.obj.get("quiet"):
        print_quiet([t.id for t in tasks])
    else:
        rows = []
        for t in tasks:
            import json as _json
            try:
                cfg = _json.loads(t.config) if t.config else {}
            except _json.JSONDecodeError:
                cfg = {}
            worker = cfg.get("worker", {}) if isinstance(cfg, dict) else {}
            cards = worker.get("acceleratorCardNum", 0) or 0
            rows.append((
                t.name,
                t.status,
                t.resource_group_name,
                cards,
                t.node_name or "-",
                t.id[:8] + "...",
            ))
        print_table(
            f"Tasks ({len(tasks)})",
            ("NAME", "STATUS", "GROUP", "CARDS", "NODE", "ID"),
            rows,
        )


def cmd_task_get(
    ctx: typer.Context,
    task_id: Annotated[str, typer.Argument(help="Task ID")],
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """Show a single task's detail + pods."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        task = client.tasks.get(task_id)
        pods = []
        try:
            pods = client.tasks.pods(task_id)
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(
            {
                "task": _short.task(task),
                "pods": [_short.pod(p) for p in pods],
            }
            if short_mode
            else {
                "task": task,
                "pods": pods,
            }
        )
    else:
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
            for p in pods:
                ports = ", ".join(p.external_urls) if p.external_urls else "-"
                rows.append((p.pod_name_changed, p.pod_status, p.node_ip, p.pod_gpu_type, ports))
            print_table(
                "Pods",
                ("POD", "STATUS", "NODE_IP", "CARD_TYPE", "EXTERNAL_URL"),
                rows,
            )


def cmd_task_logs(
    ctx: typer.Context,
    task_id: Annotated[str, typer.Argument(help="Task ID")],
    pod: Annotated[str | None, typer.Option("--pod", help="Specific pod name")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """Print task logs (plain text)."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    _ = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        log = client.tasks.read_log(task_id, pod_name=pod)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json({"task_id": task_id, "pod": pod, "log": log})
    else:
        print(log)
