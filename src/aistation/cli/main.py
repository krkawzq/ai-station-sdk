"""aistation CLI entrypoint.

Registered as console script ``aistation`` via pyproject.toml::

    [project.scripts]
    aistation = "aistation.cli.main:app"
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .. import __version__
from . import _short
from . import auth as auth_cmd
from . import envs as envs_cmd
from . import query as query_cmd
from . import status as status_cmd
from . import tasks as tasks_cmd
from ._output import print_json, resolve_context_output
from ..config import load_config


app = typer.Typer(
    name="aistation",
    help="Unofficial CLI for the Westlake AI Station. "
         "Supports read operations plus task/env lifecycle helpers.",
    no_args_is_help=True,
    add_completion=False,
)
task_app = typer.Typer(help="Training task operations", no_args_is_help=True, add_completion=False)
env_app = typer.Typer(help="Development environment operations", no_args_is_help=True, add_completion=False)


@app.callback()
def _root(
    ctx: typer.Context,
    output: Annotated[
        str | None, typer.Option("--output", "-o", help="table / json (auto by default)")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Alias for --output json")] = False,
    short_out: Annotated[
        bool, typer.Option("--short", help="When output is JSON, only print key fields")
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Print only core values")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose logging to stderr")] = False,
    timeout: Annotated[float | None, typer.Option("--timeout", help="Override default_timeout (s)")] = None,
    config_path: Annotated[Path | None, typer.Option("--config", help="Path to config.json")] = None,
    auth_path: Annotated[Path | None, typer.Option("--auth", help="Path to auth.json")] = None,
) -> None:
    """Global options propagated via ctx.obj."""
    fmt_str = output
    if json_out:
        fmt_str = "json"
    ctx.obj = {
        "output": fmt_str,
        "short": short_out,
        "quiet": quiet,
        "verbose": verbose,
        "timeout": timeout,
        "config_path": config_path,
        "auth_path": auth_path,
    }


# ---------- auth ----------
app.command("login", help="Log in with SM2-encrypted password")(auth_cmd.cmd_login)
app.command("logout", help="Clear the cached token")(auth_cmd.cmd_logout)
app.command("whoami", help="Print the current account")(auth_cmd.cmd_whoami)
app.command("ping", help="Server reachability + token health")(auth_cmd.cmd_ping)


# ---------- resource queries ----------
app.command("gpus", help="List resource groups with real usage")(query_cmd.cmd_gpus)
app.command("groups", help="Alias of 'gpus'", hidden=True)(query_cmd.cmd_gpus)
app.command("nodes", help="List cluster nodes")(query_cmd.cmd_nodes)
app.command("images", help="List images")(query_cmd.cmd_images)


# ---------- tasks (read-only) ----------
task_app.command("list", help="List my training tasks")(tasks_cmd.cmd_tasks)
task_app.command("get", help="Show one task's detail + pods")(tasks_cmd.cmd_task_get)
task_app.command("resolve", help="Resolve a task query to one canonical task")(tasks_cmd.cmd_task_resolve)
task_app.command("pods", help="List pods for one task")(tasks_cmd.cmd_task_pods)
task_app.command("logs", help="Read task logs")(tasks_cmd.cmd_task_logs)
task_app.command("wait", help="Wait until a task reaches a desired state")(tasks_cmd.cmd_task_wait)
task_app.command("create", help="Create a training task from flags or a spec file")(tasks_cmd.cmd_task_create)
task_app.command("delete", help="Delete one or more task records")(tasks_cmd.cmd_task_delete)
task_app.command("stop", help="Stop a running task")(tasks_cmd.cmd_task_stop)
app.add_typer(task_app, name="task")

# Legacy flat aliases.
app.command("tasks", hidden=True)(tasks_cmd.cmd_tasks)
app.command("task-get", hidden=True)(tasks_cmd.cmd_task_get)
app.command("task-resolve", hidden=True)(tasks_cmd.cmd_task_resolve)
app.command("task-pods", hidden=True)(tasks_cmd.cmd_task_pods)
app.command("task-wait", hidden=True)(tasks_cmd.cmd_task_wait)
app.command("task-create", hidden=True)(tasks_cmd.cmd_task_create)
app.command("task-delete", hidden=True)(tasks_cmd.cmd_task_delete)
app.command("task-stop", hidden=True)(tasks_cmd.cmd_task_stop)


@app.command("task-logs", hidden=True)
def _task_logs_cmd(
    ctx: typer.Context,
    task_id: Annotated[str, typer.Argument(help="Task ID or name")],
    pod: Annotated[str | None, typer.Option("--pod", help="Specific pod name")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    tasks_cmd.cmd_task_logs(ctx, task_id, pod=pod, json_out=json_out, short_out=short_out)


# ---------- envs ----------
env_app.command("list", help="List my dev envs")(envs_cmd.cmd_envs)
env_app.command("get", help="Show one dev env")(envs_cmd.cmd_env_get)
env_app.command("history", help="List historical dev envs")(envs_cmd.cmd_envs_history)
env_app.command("resolve", help="Resolve an env query to one canonical env")(envs_cmd.cmd_env_resolve)
env_app.command("urls", help="Get Jupyter and shell access info")(envs_cmd.cmd_env_urls)
env_app.command("wait", help="Wait until a dev env is ready")(envs_cmd.cmd_env_wait)
env_app.command("create", help="Create a dev env from flags or a spec file")(envs_cmd.cmd_env_create)
env_app.command("delete", help="Delete a dev env")(envs_cmd.cmd_env_delete)
app.add_typer(env_app, name="env")

app.command("envs", hidden=True)(envs_cmd.cmd_envs)
app.command("env-get", hidden=True)(envs_cmd.cmd_env_get)
app.command("envs-history", hidden=True)(envs_cmd.cmd_envs_history)
app.command("env-resolve", hidden=True)(envs_cmd.cmd_env_resolve)
app.command("env-urls", hidden=True)(envs_cmd.cmd_env_urls)
app.command("env-wait", hidden=True)(envs_cmd.cmd_env_wait)
app.command("env-create", hidden=True)(envs_cmd.cmd_env_create)
app.command("env-delete", hidden=True)(envs_cmd.cmd_env_delete)


# ---------- dashboard ----------
app.command("status", help="One-screen overview")(status_cmd.cmd_status)


# ---------- config / version ----------
@app.command("config", help="Print the loaded Config as JSON/table")
def _config_cmd(
    ctx: typer.Context,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    output = resolve_context_output(ctx.obj, json_out=json_out)
    cfg = load_config(ctx.obj.get("config_path"))
    from dataclasses import asdict
    data = _short.config(cfg) if output.value == "json" and (short_out or ctx.obj.get("short")) else asdict(cfg)
    if output.value == "json":
        print_json(data)
    else:
        from ._output import print_table
        print_table("Config", ("FIELD", "VALUE"), list(data.items()))


@app.command("version", help="Print the installed version")
def _version_cmd(
    ctx: typer.Context,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    output = resolve_context_output(ctx.obj, json_out=json_out)
    _ = short_out
    if output.value == "json":
        print_json({"version": __version__})
    else:
        print(__version__)


def main() -> None:
    """Module-level entry for direct module execution."""
    app()


if __name__ == "__main__":
    main()
