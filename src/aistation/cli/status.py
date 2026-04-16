"""Dashboard: one-screen summary."""
from __future__ import annotations

from typing import Annotated

import typer

from ._client import make_client
from ._error import render_and_exit
from ._output import OutputFormat, err, print_json, print_table, resolve_context_output


def cmd_status(
    ctx: typer.Context,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """One-screen overview: user, free groups, running tasks, active envs."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    _ = short_out
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        user = client.require_user()
        groups = client.groups.list()
        running_tasks = client.tasks.list(status_flag=0)
        envs = []
        try:
            envs = client.workplatforms.list()
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    free_groups = [g for g in groups if g.free_cards > 0]
    summary = {
        "user": {
            "account": user.account,
            "role_type": user.role_type,
            "group_id": user.group_id,
        },
        "groups": {
            "total": len(groups),
            "with_free_cards": len(free_groups),
            "free_groups": [
                {"name": g.group_name, "free": g.free_cards, "total": g.total_cards, "card_type": g.card_type}
                for g in free_groups
            ],
        },
        "running_tasks": [
            {"name": t.name, "status": t.status, "group": t.resource_group_name, "id": t.id}
            for t in running_tasks
        ],
        "active_envs": [
            {"name": e.wp_name, "status": e.wp_status, "group": e.group_name, "wp_id": e.wp_id}
            for e in envs
        ],
    }

    if output is OutputFormat.JSON:
        print_json(summary)
        return

    err(f"[bold cyan]▸ User[/bold cyan] {user.account} (role={user.role_type})")
    err("")

    if free_groups:
        group_rows: list[tuple[str, str, str]] = [
            (g.group_name, f"{g.free_cards}/{g.total_cards}", g.card_type or g.card_kind)
            for g in free_groups
        ]
        print_table("Groups with free cards", ("GROUP", "FREE/TOTAL", "CARD TYPE"), group_rows)
    else:
        err("[dim]▸ No groups with free cards[/dim]")
    err("")

    if running_tasks:
        task_rows: list[tuple[str, str, str, str, str]] = []
        for t in running_tasks:
            task_rows.append((t.name, t.status, t.resource_group_name, t.node_name or "-", t.id[:8] + "..."))
        print_table(f"Running tasks ({len(running_tasks)})",
                    ("NAME", "STATUS", "GROUP", "NODE", "ID"), task_rows)
    else:
        err("[dim]▸ No running tasks[/dim]")
    err("")

    if envs:
        env_rows: list[tuple[str, str, str, str]] = [
            (e.wp_name, e.wp_status or "-", e.group_name or "-", e.wp_id[:8] + "...")
            for e in envs
        ]
        print_table(f"Active dev envs ({len(envs)})",
                    ("NAME", "STATUS", "GROUP", "WP_ID"), env_rows)
    else:
        err("[dim]▸ No active dev envs[/dim]")
