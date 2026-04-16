"""Read-only dev-env subcommands."""
from __future__ import annotations

from typing import Annotated

import typer

from ._client import make_client
from ._error import render_and_exit
from ._output import OutputFormat, print_json, print_quiet, print_table, resolve_format


def cmd_envs(
    ctx: typer.Context,
    include_halted: Annotated[bool, typer.Option("--include-halted", help="Include Halt/stopped")] = False,
) -> None:
    """List my dev envs (workplatforms)."""
    output = resolve_format(ctx.obj.get("output"))
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        envs = client.workplatforms.list(include_halted=include_halted)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if ctx.obj.get("quiet"):
        print_quiet([e.wp_id for e in envs])
    elif output is OutputFormat.JSON:
        print_json(envs)
    else:
        rows = []
        for e in envs:
            rows.append((e.wp_name, e.wp_status or "-", e.group_name or "-", e.cpu, e.cards, e.wp_id[:8] + "..."))
        print_table(
            f"Dev Envs ({len(envs)})",
            ("NAME", "STATUS", "GROUP", "CPU", "CARDS", "WP_ID"),
            rows,
        )


def cmd_envs_history(
    ctx: typer.Context,
    size: Annotated[int, typer.Option("--size", help="Page size")] = 20,
    page: Annotated[int, typer.Option("--page", help="Page number")] = 1,
) -> None:
    """List historical dev envs."""
    output = resolve_format(ctx.obj.get("output"))
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        envs = client.workplatforms.list_history(page=page, page_size=size)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(envs)
    else:
        rows = []
        for e in envs:
            rows.append((e.wp_name, e.create_time, e.cpu, e.cards, e.wp_id[:8] + "..."))
        print_table(
            f"Dev Env History (page {page}, size {size})",
            ("NAME", "CREATED", "CPU", "CARDS", "WP_ID"),
            rows,
        )


def cmd_env_get(
    ctx: typer.Context,
    wp_id: Annotated[str, typer.Argument(help="WorkPlatform ID")],
) -> None:
    """Show a single dev env's detail."""
    output = resolve_format(ctx.obj.get("output"))
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        env = client.workplatforms.get(wp_id)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(env)
    else:
        print_table(
            f"Dev Env {env.wp_name}",
            ("FIELD", "VALUE"),
            [
                ("wp_id", env.wp_id),
                ("status", env.wp_status),
                ("group", env.group_name),
                ("image", env.image),
                ("frame_work", env.frame_work),
                ("cpu", env.cpu),
                ("cards", env.cards),
                ("card_kind", env.card_kind),
                ("memory_gb", env.memory_gb),
                ("shm_size", env.shm_size),
                ("command", (env.command or "")[:100]),
                ("created", env.create_time),
            ],
        )
