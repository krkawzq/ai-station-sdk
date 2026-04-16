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
from . import auth as auth_cmd
from . import envs as envs_cmd
from . import query as query_cmd
from . import status as status_cmd
from . import tasks as tasks_cmd
from ._output import print_json, resolve_format
from ..config import load_config


app = typer.Typer(
    name="aistation",
    help="Unofficial read-only CLI for the Westlake AI Station. "
         "Write operations (create/delete/stop) are SDK-only by design.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root(
    ctx: typer.Context,
    output: Annotated[
        str | None, typer.Option("--output", "-o", help="table / json (auto by default)")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Alias for --output json")] = False,
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
app.command("tasks", help="List my training tasks")(tasks_cmd.cmd_tasks)
app.command("task", help="Show a single task's detail + pods")(tasks_cmd.cmd_task_get)


@app.command("task-logs", help="Print task logs (plain text)")
def _task_logs_cmd(
    ctx: typer.Context,
    task_id: Annotated[str, typer.Argument(help="Task ID")],
    pod: Annotated[str | None, typer.Option("--pod", help="Specific pod name")] = None,
) -> None:
    tasks_cmd.cmd_task_logs(ctx, task_id, pod=pod)


# ---------- envs (read-only) ----------
app.command("envs", help="List my dev envs (workplatforms)")(envs_cmd.cmd_envs)
app.command("env", help="Show a single dev env's detail")(envs_cmd.cmd_env_get)
app.command("envs-history", help="List historical dev envs")(envs_cmd.cmd_envs_history)


# ---------- dashboard ----------
app.command("status", help="One-screen overview")(status_cmd.cmd_status)


# ---------- config / version ----------
@app.command("config", help="Print the loaded Config as JSON/table")
def _config_cmd(ctx: typer.Context) -> None:
    output = resolve_format(ctx.obj.get("output"))
    cfg = load_config(ctx.obj.get("config_path"))
    from dataclasses import asdict
    data = asdict(cfg)
    if output.value == "json":
        print_json(data)
    else:
        from ._output import print_table
        print_table("Config", ("FIELD", "VALUE"), list(data.items()))


@app.command("version", help="Print the installed version")
def _version_cmd(ctx: typer.Context) -> None:
    output = resolve_format(ctx.obj.get("output"))
    if output.value == "json":
        print_json({"version": __version__})
    else:
        print(__version__)


def main() -> None:
    """Module-level entry when someone runs ``python -m aistation``."""
    app()


if __name__ == "__main__":
    main()
