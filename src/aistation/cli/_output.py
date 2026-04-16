"""Unified output rendering: table / json / quiet.

Auto-detects TTY: when stdout is a terminal, defaults to ``table``; otherwise
defaults to ``json`` so piping into ``jq`` / Skills Just Works.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Iterable, Sequence
from enum import Enum
from typing import Any

from rich.console import Console
from rich.table import Table

_err_console = Console(stderr=True)
_out_console = Console()


class OutputFormat(str, Enum):
    TABLE = "table"
    JSON = "json"
    AUTO = "auto"


def resolve_format(fmt: OutputFormat | str | None) -> OutputFormat:
    if isinstance(fmt, str):
        fmt = OutputFormat(fmt.lower())
    if fmt is None or fmt is OutputFormat.AUTO:
        return OutputFormat.TABLE if sys.stdout.isatty() else OutputFormat.JSON
    return fmt


def resolve_context_output(
    ctx_obj: dict[str, Any] | None,
    *,
    json_out: bool = False,
) -> OutputFormat:
    if json_out:
        return OutputFormat.JSON
    if not isinstance(ctx_obj, dict):
        return resolve_format(None)
    return resolve_format(ctx_obj.get("output"))


def resolve_short_mode(
    ctx_obj: dict[str, Any] | None,
    *,
    output: OutputFormat,
    short_out: bool = False,
) -> bool:
    if output is not OutputFormat.JSON:
        return False
    if short_out:
        return True
    return isinstance(ctx_obj, dict) and bool(ctx_obj.get("short"))


def _as_serializable(obj: Any) -> Any:
    """Coerce a SDK dataclass or nested structure to JSON-ready form."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _as_serializable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [_as_serializable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _as_serializable(v) for k, v in obj.items()}
    return obj


def print_json(data: Any) -> None:
    """Print stable, pretty JSON without terminal color codes."""
    print(json.dumps(_as_serializable(data), ensure_ascii=False, indent=2))


def print_table(
    title: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    caption: str | None = None,
) -> None:
    """Render a rich table."""
    table = Table(title=title, caption=caption, show_lines=False, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    any_row = False
    for row in rows:
        any_row = True
        table.add_row(*[_fmt_cell(v) for v in row])
    if not any_row:
        _out_console.print(f"[dim]{title}: no rows[/dim]")
        return
    _out_console.print(table)


def _fmt_cell(value: Any) -> str:
    if value is None:
        return "[dim]-[/dim]"
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(x) for x in value) if value else "[dim]-[/dim]"
    return str(value)


def print_quiet(value: Any) -> None:
    """Print only the core value (one-line, no formatting), for shell pipelines."""
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            print(v)
    else:
        print(value)


def err(*args: Any, **kwargs: Any) -> None:
    """Print to stderr via rich."""
    _err_console.print(*args, **kwargs)


def info(message: str) -> None:
    err(f"[dim]ℹ[/dim] {message}")


def success(message: str) -> None:
    err(f"[green]✓[/green] {message}")


def warn(message: str) -> None:
    err(f"[yellow]⚠[/yellow] {message}")
