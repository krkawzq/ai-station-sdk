"""Auth subcommands: login / logout / whoami / ping."""
from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

from ..config import load_auth, save_auth
from ..errors import InvalidCredentials
from ._client import make_client
from ._error import EXIT_AUTH, render_and_exit
from ._output import OutputFormat, err, print_json, print_quiet, resolve_context_output, success


def _resolve_credentials(
    account: str | None,
    password: str | None,
    *,
    interactive: bool,
) -> tuple[str, str]:
    """Pick credentials from (args > env > interactive prompt). Validate non-empty.

    Raises :class:`InvalidCredentials` if still missing after all sources.
    """
    acc = account or os.environ.get("AISTATION_ACCOUNT")
    pwd = password
    if pwd == "-":
        pwd = sys.stdin.readline().rstrip("\n")
    if not pwd:
        pwd = os.environ.get("AISTATION_PASSWORD")

    # Interactive prompt — TTY only, and only when --quiet not set
    if interactive and sys.stdin.isatty() and sys.stdout.isatty():
        if not acc:
            try:
                acc = typer.prompt("Account")
            except (KeyboardInterrupt, EOFError):
                raise InvalidCredentials("login cancelled") from None
        if not pwd:
            try:
                pwd = typer.prompt("Password", hide_input=True)
            except (KeyboardInterrupt, EOFError):
                raise InvalidCredentials("login cancelled") from None

    acc = (acc or "").strip()
    pwd = pwd or ""
    if not acc:
        raise InvalidCredentials(
            "missing account (use -u / env AISTATION_ACCOUNT)",
            err_code="SDK_CLI_MISSING_ACCOUNT",
            err_message="account is empty",
        )
    if not pwd:
        raise InvalidCredentials(
            "missing password (use -p / env AISTATION_PASSWORD)",
            err_code="SDK_CLI_MISSING_PASSWORD",
            err_message="password is empty",
        )
    return acc, pwd


def _prompt_captcha(client: "object", *, max_refresh: int = 5) -> str:
    """Render a captcha image in the terminal and prompt the user.

    The user can type ``r`` / ``refresh`` / empty to request a new captcha,
    up to ``max_refresh`` times.
    """
    from . import _captcha
    for _ in range(max_refresh):
        b64 = client.fetch_captcha()   # type: ignore[attr-defined]
        path = _captcha.save_png(b64)
        art = _captcha.render(path, max_width=60)
        err("")
        err(f"[cyan]▸ Captcha required (saved: {path})[/cyan]")
        if art:
            err("")
            print(art)  # stdout for exact escape passthrough
            err("")
        else:
            err(
                "[yellow]⚠ No image renderer available.[/yellow] Install pillow "
                "(or chafa) for inline display, or open the file above.",
            )
        try:
            code = typer.prompt(
                "Enter captcha (or 'r' to refresh)", default="", show_default=False
            ).strip()
        except (KeyboardInterrupt, EOFError):
            raise InvalidCredentials("captcha entry cancelled") from None
        if not code or code.lower() in ("r", "refresh"):
            err("[dim]refreshing captcha…[/dim]")
            continue
        return code
    raise InvalidCredentials(
        "captcha entry abandoned after too many refreshes",
        err_code="SDK_CLI_CAPTCHA_ABANDONED",
    )


def cmd_login(
    ctx: typer.Context,
    account: Annotated[str | None, typer.Option("--account", "-u", help="Account name")] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", "-p", help="Password (env AISTATION_PASSWORD or '-' for stdin)"),
    ] = None,
    captcha: Annotated[
        str | None, typer.Option("--captcha", "-c", help="Captcha code (skip to auto-prompt)")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """Log in with SM2-encrypted password and cache the token.

    - Credentials: args → env vars → interactive prompt (TTY only).
    - On ``IBASE_IAUTH_CAPTCHA_EMPTY`` / ``IBASE_IAUTH_CAPTCHA_ERROR``: fetches
      the captcha image, renders it in the terminal, and prompts for the text.
      User may type ``r`` to refresh or press Enter for a new image.
    - Empty credentials / repeated captcha abandonment abort without hitting
      the network.
    """
    output = resolve_context_output(ctx.obj, json_out=json_out)
    interactive = not ctx.obj.get("quiet") and output is not OutputFormat.JSON
    CAPTCHA_CODES = {
        "IBASE_IAUTH_CAPTCHA_EMPTY",
        "IBASE_IAUTH_CAPTCHA_ERROR",
        "IBASE_IAUTH_CAPTCHA_EXPIRED",
    }
    try:
        acc, pwd = _resolve_credentials(account, password, interactive=interactive)
        client = make_client(
            require_token=True,
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
            login=False,
        )
        user = None
        attempts = 0
        while True:
            attempts += 1
            try:
                user = client.login(account=acc, password=pwd, captcha=captcha)
                break
            except Exception as exc:  # noqa: BLE001
                code = getattr(exc, "err_code", "") or ""
                if code in CAPTCHA_CODES and interactive and attempts <= 3:
                    captcha = _prompt_captcha(client)
                    continue
                raise
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)
    assert user is not None  # narrow for type-checker
    _ = short_out

    if output is OutputFormat.JSON:
        print_json({
            "account": user.account,
            "user_name": user.user_name,
            "user_id": user.user_id,
            "group_id": user.group_id,
            "role_type": user.role_type,
            "token": user.token,
        })
    elif ctx.obj.get("quiet"):
        print_quiet(user.token)
    else:
        success(f"Logged in as [bold]{user.account}[/bold] ({user.user_name}), role={user.role_type}")


def cmd_logout(
    ctx: typer.Context,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """Clear the cached token (keeps account/password on disk)."""
    output = resolve_context_output(ctx.obj, json_out=json_out)
    _ = short_out
    try:
        auth = load_auth(ctx.obj.get("auth_path"))
        auth.token = ""
        auth.token_saved_at = ""
        save_auth(auth, ctx.obj.get("auth_path"))
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)
    if output is OutputFormat.JSON:
        print_json({"logged_out": True})
    else:
        success("Token cleared")


def cmd_whoami(
    ctx: typer.Context,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """Print the currently-logged-in account (from local token cache).

    Does not hit the server. If you want to verify the token is still valid
    call ``aistation ping`` instead.
    """
    output = resolve_context_output(ctx.obj, json_out=json_out)
    _ = short_out
    try:
        auth = load_auth(ctx.obj.get("auth_path"))
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if not auth.token:
        err("[red]✗[/red] Not logged in. Run `aistation login` first.")
        sys.exit(EXIT_AUTH)

    info = {
        "account": auth.account,
        "base_url": auth.base_url,
        "token_cached": bool(auth.token),
        "token_saved_at": auth.token_saved_at or None,
    }
    if output is OutputFormat.JSON:
        print_json(info)
    elif ctx.obj.get("quiet"):
        print_quiet(auth.account)
    else:
        from ._output import print_table
        print_table("Current User", ("FIELD", "VALUE"), list(info.items()))


def cmd_ping(
    ctx: typer.Context,
    json_out: Annotated[bool, typer.Option("--json", help="Output formatted JSON")] = False,
    short_out: Annotated[bool, typer.Option("--short", help="When output is JSON, only print key fields")] = False,
) -> None:
    """Health check: server reachable? token valid?

    Does not require a token — if no token is cached, ``token_valid`` is
    simply reported as ``null``.
    """
    output = resolve_context_output(ctx.obj, json_out=json_out)
    _ = short_out
    try:
        client = make_client(
            auth_path=ctx.obj.get("auth_path"),
            config_path=ctx.obj.get("config_path"),
            timeout=ctx.obj.get("timeout"),
            login=False,
        )
        result = client.ping()
    except Exception as exc:  # noqa: BLE001
        render_and_exit(exc, output=output)

    if output is OutputFormat.JSON:
        print_json(result)
    else:
        from ._output import print_table
        rows = [(k, v) for k, v in result.items() if k not in ("error",)]
        print_table("Ping", ("FIELD", "VALUE"), rows)
        if result.get("error"):
            from ._output import warn
            warn(f"underlying error: {result['error']}")
