"""Read-only resource queries: gpus / nodes / images."""
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


def cmd_gpus(
    ctx: typer.Context,
    free: Annotated[bool, typer.Option("--free", help="Only groups with free_cards > 0")] = False,
    kind: Annotated[str | None, typer.Option("--kind", help="Filter by card kind: GPU / CPU")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """List resource groups with real utilization."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        groups = client.groups.list()
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if kind:
        groups = [g for g in groups if g.card_kind == kind]
    if free:
        groups = [g for g in groups if g.free_cards > 0]

    if output is OutputFormat.JSON:
        print_json([_short.group(g) for g in groups] if short_mode else groups)
    elif ctx.obj.get("quiet"):
        print_quiet([g.group_name for g in groups])
    else:
        rows = []
        for g in groups:
            marker = " ⭐" if g.free_cards > 0 else ""
            rows.append((
                g.group_name,
                f"{g.used_cards}/{g.total_cards}",
                f"{g.free_cards}{marker}",
                g.card_type or g.card_kind,
                g.node_count,
            ))
        print_table(
            "Resource Groups",
            ("GROUP", "CARDS (USED/TOTAL)", "FREE", "CARD TYPE", "NODES"),
            rows,
        )


def cmd_nodes(
    ctx: typer.Context,
    group: Annotated[str | None, typer.Option("--group", help="Filter by group name or id")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """List cluster nodes (with real occupancy)."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        group_id = client.groups.resolve_id(group) if group else None
        nodes = client.nodes.list(group_id=group_id)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json([_short.node(n) for n in nodes] if short_mode else nodes)
    elif ctx.obj.get("quiet"):
        print_quiet([n.node_name for n in nodes])
    else:
        rows = []
        for n in nodes:
            rows.append((
                n.node_name,
                n.group_name,
                f"{n.cards_used}/{n.cards_total}",
                n.cards_free,
                f"{n.cpu_used}/{n.cpu}",
                n.memory_gb,
                n.status,
            ))
        print_table(
            "Nodes",
            ("NODE", "GROUP", "CARDS", "FREE", "CPU", "MEM(GB)", "STATUS"),
            rows,
        )


def cmd_images(
    ctx: typer.Context,
    image_type: Annotated[str | None, typer.Option("--type", help="pytorch / tensorflow / other / ...")] = None,
    share: Annotated[int | None, typer.Option("--share", help="1=private, 2=public")] = None,
    search: Annotated[str | None, typer.Option("--search", "-s", help="Substring match on name:tag")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max rows to show")] = 50,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """List images (defaults to all, newest update first)."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        images = client.images.list(image_type=image_type, share=share)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if search:
        needle = search.lower()
        images = [i for i in images if needle in i.full_ref.lower()]
    # sort by pull_count descending for relevance
    images.sort(key=lambda i: (i.pull_count, i.update_time), reverse=True)
    if limit > 0:
        images = images[:limit]

    if output is OutputFormat.JSON:
        print_json([_short.image(i) for i in images] if short_mode else images)
    elif ctx.obj.get("quiet"):
        print_quiet([i.full_ref for i in images])
    else:
        rows = []
        for i in images:
            share_s = "public" if i.share == 2 else "private"
            size_mb = i.size_bytes / (1024 * 1024) if i.size_bytes else 0
            rows.append((
                i.full_ref,
                i.image_type,
                share_s,
                i.pull_count,
                f"{size_mb:.0f} MB" if size_mb else "-",
                i.owner,
            ))
        print_table(
            f"Images ({len(images)} shown)",
            ("REF", "TYPE", "SHARE", "PULLS", "SIZE", "OWNER"),
            rows,
        )
