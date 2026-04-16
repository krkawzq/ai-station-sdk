"""Map SDK exceptions to CLI exit codes and user-visible errors."""
from __future__ import annotations

import sys
from typing import NoReturn

from .. import errors as sdk_errors
from ._output import OutputFormat, err, print_json


EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_SPEC = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_PERMISSION = 5
EXIT_NETWORK = 6
EXIT_BUSINESS = 7


def classify(exc: BaseException) -> int:
    if isinstance(exc, (sdk_errors.NotFoundError, LookupError)):
        return EXIT_NOT_FOUND
    if isinstance(exc, sdk_errors.SpecValidationError):
        return EXIT_SPEC
    if isinstance(exc, sdk_errors.InvalidCredentials):
        return EXIT_AUTH
    if isinstance(exc, sdk_errors.TokenExpired):
        return EXIT_AUTH
    if isinstance(exc, sdk_errors.AuthError):
        return EXIT_AUTH
    if isinstance(exc, sdk_errors.PermissionDenied):
        return EXIT_PERMISSION
    if isinstance(exc, sdk_errors.TransportError):
        return EXIT_NETWORK
    if isinstance(exc, sdk_errors.ResourceError):
        return EXIT_BUSINESS
    if isinstance(exc, sdk_errors.ValidationError):
        return EXIT_SPEC
    if isinstance(exc, sdk_errors.AiStationError):
        return EXIT_BUSINESS
    if isinstance(exc, ValueError):
        return EXIT_NOT_FOUND
    return EXIT_GENERAL


def render_and_exit(exc: BaseException, *, output: OutputFormat) -> NoReturn:
    """Print the error in the appropriate format and call sys.exit with
    the classified code."""
    code = classify(exc)
    if output is OutputFormat.JSON:
        payload: dict[str, object] = {
            "error": {
                "code": getattr(exc, "err_code", None) or type(exc).__name__,
                "message": getattr(exc, "err_message", None) or str(exc),
                "path": getattr(exc, "path", None),
                "exit_code": code,
            }
        }
        hint = None
        if isinstance(exc, sdk_errors.AiStationError):
            hint = exc.hint()
        if hint:
            short, action = hint
            payload["error"]["hint"] = [short, action]   # type: ignore[index]
        field = getattr(exc, "field_name", None)
        if field:
            payload["error"]["field"] = field            # type: ignore[index]
        print_json(payload)
    else:
        err_code = getattr(exc, "err_code", None) or type(exc).__name__
        msg = getattr(exc, "err_message", None) or str(exc)
        err(f"[red]✗[/red] [{err_code}] {msg}")
        if isinstance(exc, sdk_errors.AiStationError):
            hint = exc.hint()
            if hint:
                short, action = hint
                err(f"   [cyan]→[/cyan] {short}")
                err(f"   [cyan]→ 建议：[/cyan]{action}")
            path = getattr(exc, "path", None)
            if path:
                err(f"   [dim]path: {path}[/dim]")
        field = getattr(exc, "field_name", None)
        if field:
            err(f"   [dim]field: {field}[/dim]")
    sys.exit(code)
