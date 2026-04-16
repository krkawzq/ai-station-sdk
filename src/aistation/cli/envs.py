"""Development-environment CLI commands."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from ..errors import ValidationError
from ..specs import WorkPlatformSpec
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
    parse_env_assignments,
    parse_json_object_list,
    parse_json_object_merge,
)


WORKPLATFORM_FIELD_ALIASES = {
    "group": "resource_group",
    "resourceGroup": "resource_group",
    "resource-group": "resource_group",
    "memory": "memory_gb",
    "cardKind": "card_kind",
    "podNum": "pod_num",
    "shmSize": "shm_size",
    "frameWork": "frame_work",
    "imageType": "image_type",
    "switchType": "switch_type",
    "wpType": "wp_type",
    "nodeList": "node_list",
    "rawOverrides": "raw_overrides",
}


def _env_item(env: Any, *, short_mode: bool) -> Any:
    return _short.workplatform(env) if short_mode else env


def _env_action_payload(result: Any, *, short_mode: bool) -> dict[str, Any]:
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
        payload["item"] = _env_item(result.entity, short_mode=short_mode)
    if result.payload is not None and (not short_mode or result.entity is None):
        payload["payload"] = result.payload
    if result.raw is not None and not short_mode:
        payload["raw"] = result.raw
    if result.extras and not short_mode:
        payload["extras"] = result.extras
    return payload


def _render_env_detail_table(env: Any) -> None:
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


def _render_env_action_table(title: str, data: dict[str, Any]) -> None:
    rows = [(key, value) for key, value in data.items() if value not in (None, [], {})]
    print_table(title, ("FIELD", "VALUE"), rows)


def _lookup_env(client: Any, query: str, *, include_halted: bool = True, search_history: bool = True) -> Any:
    return client.workplatforms.resolve(
        query,
        include_halted=include_halted,
        search_history=search_history,
    )


def _build_workplatform_spec(
    *,
    file: Path | None,
    name: str | None,
    resource_group: str | None,
    image: str | None,
    command: str | None,
    cards: int | None,
    cpu: int | None,
    memory_gb: int | None,
    card_kind: str | None,
    pod_num: int | None,
    shm_size: int | None,
    frame_work: str | None,
    image_type: str | None,
    ports: list[int] | None,
    env_vars: list[str] | None,
    volume_json: list[str] | None,
    model_json: list[str] | None,
    switch_type: str | None,
    wp_type: str | None,
    node_names: list[str] | None,
    raw_override_json: list[str] | None,
) -> WorkPlatformSpec:
    ensure_non_negative_int(cards, option_name="--cards")
    ensure_non_negative_int(cpu, option_name="--cpu")
    ensure_non_negative_int(memory_gb, option_name="--memory-gb")
    ensure_non_negative_int(shm_size, option_name="--shm-size")
    ensure_min_int(pod_num, option_name="--pod-num", minimum=1)
    ensure_port_list(ports)
    base = load_mapping_file(file, resource_name="env", unwrap_keys=("env", "workplatform", "spec"))
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
            "card_kind": card_kind,
            "pod_num": pod_num,
            "shm_size": shm_size,
            "frame_work": frame_work,
            "image_type": image_type,
            "switch_type": switch_type,
            "wp_type": wp_type,
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
            "volumes": parse_json_object_list(volume_json, option_name="--volume-json"),
            "models": parse_json_object_list(model_json, option_name="--model-json"),
            "node_list": list(node_names or []),
        },
    )
    return build_spec(
        WorkPlatformSpec,
        merged,
        field_aliases=WORKPLATFORM_FIELD_ALIASES,
        resource_name="env",
    )


def cmd_envs(
    ctx: typer.Context,
    include_halted: Annotated[bool, typer.Option("--include-halted", help="Include halted envs")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """List my development environments."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
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

    if output is OutputFormat.JSON:
        print_json(
            {
                "items": [_env_item(env, short_mode=short_mode) for env in envs],
                "count": len(envs),
                "include_halted": include_halted,
            }
        )
    elif ctx.obj.get("quiet"):
        print_quiet([env.wp_id for env in envs])
    else:
        rows = []
        for env in envs:
            rows.append((env.wp_name, env.wp_status or "-", env.group_name or "-", env.cpu, env.cards, env.wp_id[:8] + "..."))
        print_table(
            f"Dev Envs ({len(envs)})",
            ("NAME", "STATUS", "GROUP", "CPU", "CARDS", "WP_ID"),
            rows,
        )


def cmd_envs_history(
    ctx: typer.Context,
    size: Annotated[int, typer.Option("--size", help="Page size")] = 20,
    page: Annotated[int, typer.Option("--page", help="Page number")] = 1,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """List historical development environments."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        ensure_min_int(page, option_name="--page", minimum=1)
        ensure_min_int(size, option_name="--size", minimum=1)
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
        print_json(
            {
                "items": [_env_item(env, short_mode=short_mode) for env in envs],
                "count": len(envs),
                "page": page,
                "page_size": size,
            }
        )
    elif ctx.obj.get("quiet"):
        print_quiet([env.wp_id for env in envs])
    else:
        rows = []
        for env in envs:
            rows.append((env.wp_name, env.create_time, env.cpu, env.cards, env.wp_id[:8] + "..."))
        print_table(
            f"Dev Env History (page {page}, size {size})",
            ("NAME", "CREATED", "CPU", "CARDS", "WP_ID"),
            rows,
        )


def cmd_env_get(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Workplatform ID or name")],
    include_halted: Annotated[
        bool, typer.Option("--include-halted/--active-only", help="Search halted envs too")
    ] = True,
    search_history: Annotated[
        bool, typer.Option("--search-history/--active-list-only", help="Search history for matches")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Show one development environment."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        env = _lookup_env(client, query, include_halted=include_halted, search_history=search_history)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json({"item": _env_item(env, short_mode=short_mode)})
    elif ctx.obj.get("quiet"):
        print_quiet(env.wp_id)
    else:
        _render_env_detail_table(env)


def cmd_env_resolve(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Workplatform ID, prefix, or name")],
    include_halted: Annotated[
        bool, typer.Option("--include-halted/--active-only", help="Search halted envs too")
    ] = True,
    search_history: Annotated[
        bool, typer.Option("--search-history/--active-list-only", help="Search history for matches")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Resolve an env reference to one canonical env object."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        env = _lookup_env(client, query, include_halted=include_halted, search_history=search_history)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json({"query": query, "item": _env_item(env, short_mode=short_mode)})
    elif ctx.obj.get("quiet"):
        print_quiet(env.wp_id)
    else:
        _render_env_detail_table(env)


def cmd_env_urls(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Workplatform ID or name")],
    pod: Annotated[str | None, typer.Option("--pod", help="Specific pod ID for shell URL")] = None,
    include_halted: Annotated[
        bool, typer.Option("--include-halted/--active-only", help="Search halted envs too")
    ] = False,
    search_history: Annotated[
        bool, typer.Option("--search-history/--active-list-only", help="Search history for matches")
    ] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Get Jupyter and shell access info for an env."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    del short_mode
    try:
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        env = _lookup_env(client, query, include_halted=include_halted, search_history=search_history)
        jupyter = client.workplatforms.jupyter_url(env)
        shell = client.workplatforms.shell_url(env, pod_id=pod)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    payload = {"wp_id": env.wp_id, "jupyter": jupyter, "shell": shell}
    if output is OutputFormat.JSON:
        print_json(payload)
    elif ctx.obj.get("quiet"):
        for key in ("url", "jupyterUrl", "shellUrl"):
            value = jupyter.get(key)
            if isinstance(value, str) and value:
                print_quiet(value)
                return
        print_quiet(env.wp_id)
    else:
        rows = [("wp_id", env.wp_id), ("jupyter", jupyter), ("shell", shell)]
        print_table("Env URLs", ("FIELD", "VALUE"), rows)


def cmd_env_wait(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Workplatform ID or name")],
    timeout: Annotated[float, typer.Option("--timeout", help="Wait timeout in seconds")] = 600.0,
    interval: Annotated[float, typer.Option("--interval", help="Polling interval in seconds")] = 5.0,
    include_halted: Annotated[
        bool, typer.Option("--include-halted/--active-only", help="Search halted envs too")
    ] = True,
    search_history: Annotated[
        bool, typer.Option("--search-history/--active-list-only", help="Search history for matches")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Wait until an env becomes ready."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    try:
        ensure_positive_float(timeout, option_name="--timeout")
        ensure_positive_float(interval, option_name="--interval")
        client = make_client(
            require_token=True,
            allow_live_login=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
        )
        env = _lookup_env(client, query, include_halted=include_halted, search_history=search_history)
        env = client.workplatforms.wait_ready(env, timeout=timeout, interval=interval)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json({"target": env.wp_id, "condition": "ready", "item": _env_item(env, short_mode=short_mode)})
    elif ctx.obj.get("quiet"):
        print_quiet(env.wp_id)
    else:
        _render_env_action_table(
            "Env Wait",
            {"wp_id": env.wp_id, "name": env.wp_name, "status": env.wp_status},
        )


def cmd_env_create(
    ctx: typer.Context,
    file: Annotated[Path | None, typer.Option("--file", "-f", help="JSON/YAML env spec file")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Env name")] = None,
    resource_group: Annotated[
        str | None, typer.Option("--group", "--resource-group", help="Env resource group")
    ] = None,
    image: Annotated[str | None, typer.Option("--image", help="Image reference")] = None,
    command: Annotated[str | None, typer.Option("--command", help="Container command")] = None,
    cards: Annotated[int | None, typer.Option("--cards", help="Accelerator cards")] = None,
    cpu: Annotated[int | None, typer.Option("--cpu", help="CPU cores")] = None,
    memory_gb: Annotated[int | None, typer.Option("--memory-gb", help="Memory in GB")] = None,
    card_kind: Annotated[str | None, typer.Option("--card-kind", help="GPU or CPU")] = None,
    pod_num: Annotated[int | None, typer.Option("--pod-num", help="Pod count")] = None,
    shm_size: Annotated[int | None, typer.Option("--shm-size", help="Shared memory size")] = None,
    frame_work: Annotated[str | None, typer.Option("--frame-work", help="Framework label")] = None,
    image_type: Annotated[str | None, typer.Option("--image-type", help="Image type")] = None,
    ports: Annotated[list[int] | None, typer.Option("--port", help="Expose container port; repeatable")] = None,
    env_vars: Annotated[list[str] | None, typer.Option("--env", help="KEY=VALUE; repeatable")] = None,
    volume_json: Annotated[
        list[str] | None, typer.Option("--volume-json", help="Volume object; repeatable")
    ] = None,
    model_json: Annotated[
        list[str] | None, typer.Option("--model-json", help="Model object; repeatable")
    ] = None,
    switch_type: Annotated[str | None, typer.Option("--switch-type", help="Switch type")] = None,
    wp_type: Annotated[str | None, typer.Option("--wp-type", help="Workplatform type")] = None,
    node_names: Annotated[
        list[str] | None, typer.Option("--node-name", help="Preferred node name; repeatable")
    ] = None,
    raw_override_json: Annotated[
        list[str] | None, typer.Option("--raw-override-json", help="Raw payload override object; repeatable")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Build payload only")] = False,
    idempotent: Annotated[
        bool, typer.Option("--idempotent/--no-idempotent", help="Reuse same-name active env")
    ] = True,
    wait: Annotated[bool, typer.Option("--wait", help="Wait until the env is ready")] = False,
    wait_timeout: Annotated[
        float, typer.Option("--wait-timeout", help="Ready wait timeout in seconds")
    ] = 600.0,
    wait_interval: Annotated[
        float, typer.Option("--wait-interval", help="Ready poll interval in seconds")
    ] = 5.0,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Create a development environment from CLI flags or a spec file."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    short_mode = resolve_short_mode(ctx.obj, output=output, short_out=short_out)
    if dry_run and wait:
        render_and_exit(
            ValidationError(
                "--dry-run cannot be combined with --wait",
                field_name="--dry-run",
                err_code="SDK_CLI_BAD_SPEC_INPUT",
                err_message="cannot wait in dry-run mode",
            ),
            output=output,
        )
    if wait:
        try:
            ensure_positive_float(wait_timeout, option_name="--wait-timeout")
            ensure_positive_float(wait_interval, option_name="--wait-interval")
        except Exception as exc:  # noqa: BLE001
            render_and_exit(exc, output=output)
    try:
        spec = _build_workplatform_spec(
            file=file,
            name=name,
            resource_group=resource_group,
            image=image,
            command=command,
            cards=cards,
            cpu=cpu,
            memory_gb=memory_gb,
            card_kind=card_kind,
            pod_num=pod_num,
            shm_size=shm_size,
            frame_work=frame_work,
            image_type=image_type,
            ports=ports,
            env_vars=env_vars,
            volume_json=volume_json,
            model_json=model_json,
            switch_type=switch_type,
            wp_type=wp_type,
            node_names=node_names,
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
            result = client.workplatforms.create(spec, dry_run=True, idempotent=idempotent)
        elif wait:
            result = client.workplatforms.create_and_wait_ready(
                spec,
                idempotent=idempotent,
                timeout=wait_timeout,
                interval=wait_interval,
            )
        else:
            result = client.workplatforms.create(spec, idempotent=idempotent)
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(_env_action_payload(result, short_mode=short_mode))
    elif ctx.obj.get("quiet"):
        print_quiet(result.target_id or (result.entity.wp_id if result.entity is not None else None))
    else:
        summary = {
            "wp_id": result.target_id or (result.entity.wp_id if result.entity is not None else None),
            "name": result.entity.wp_name if result.entity is not None else spec.name,
            "status": result.entity.wp_status if result.entity is not None else None,
            "created": result.created,
            "reused": result.reused,
            "waited": result.waited,
            "dry_run": dry_run,
        }
        if dry_run:
            _render_env_action_table("Env Dry Run", summary)
        else:
            success("Env request completed")
            _render_env_action_table("Env Create", summary)


def cmd_env_delete(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Workplatform ID or name")],
    include_halted: Annotated[
        bool, typer.Option("--include-halted/--active-only", help="Search halted envs too")
    ] = True,
    search_history: Annotated[
        bool, typer.Option("--search-history/--active-list-only", help="Search history for matches")
    ] = True,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
) -> None:
    """Delete a development environment."""
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
        env = _lookup_env(client, query, include_halted=include_halted, search_history=search_history)
        result = client.workplatforms.delete(env)
        result.entity = env
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(_env_action_payload(result, short_mode=short_mode))
    elif ctx.obj.get("quiet"):
        print_quiet(result.target_id)
    else:
        success("Env delete request completed")
        _render_env_action_table(
            "Env Delete",
            {"wp_id": result.target_id, "name": env.wp_name, "status": env.wp_status},
        )
