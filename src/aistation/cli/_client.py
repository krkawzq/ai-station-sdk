"""Shared client builder — reads context options into an AiStationClient.

Key policy: for read commands we **only** restore a cached token. If no token
is cached we fail fast with a clear "please run `aistation login`" message
instead of silently attempting a login (which would hang if the saved password
on disk is stale or the network is slow).
"""
from __future__ import annotations

from pathlib import Path

from ..client import AiStationClient
from ..enums import AuthMode
from ..config import AuthData
from ..errors import InvalidCredentials, TokenExpired


def make_client(
    *,
    config_path: Path | None = None,
    auth_path: Path | None = None,
    timeout: float | None = None,
    login: bool = True,
    require_token: bool = False,
    allow_live_login: bool = False,
) -> AiStationClient:
    """Construct a client from config files.

    Modes:
    - ``login=False, require_token=False``: no auth attempt; used by ``login``
      and ``ping`` which must work without a token.
    - ``login=True, require_token=True, allow_live_login=False``: restore only
      the cached token. If no token is cached, fail fast with
      :class:`TokenExpired`.
    - ``login=True, allow_live_login=True``: allow the client to refresh auth
      automatically, but only when login is actually possible.
    """
    client = AiStationClient.from_config(
        auth_path=auth_path,
        config_path=config_path,
        auth_mode=AuthMode.AUTO if allow_live_login else AuthMode.MANUAL,
    )
    if timeout is not None:
        client.config.default_timeout = timeout
    if login:
        if not client.auth.token:
            can_live_login = bool(
                allow_live_login
                and client.auth.account
                and client.auth.password
                and client.base_url != AuthData.base_url
            )
            if require_token and not allow_live_login:
                raise TokenExpired(
                    "no cached token; run `aistation login` first",
                    err_code="SDK_CLI_NOT_LOGGED_IN",
                    err_message="no cached token on disk",
                )
            if require_token and allow_live_login and not can_live_login:
                raise InvalidCredentials(
                    "no cached token and no saved credentials; run `aistation login` first",
                    err_code="SDK_CLI_NOT_LOGGED_IN",
                    err_message="no cached token or reusable saved credentials",
                )
            if not can_live_login and not require_token:
                return client
            client.ensure_auth()
        else:
            # Prime the session header from the cached token without hitting
            # the server. If the token is stale, the next real call will surface
            # TokenExpired and the CLI can ask the user to log in explicitly.
            client.session.headers["X-Auth-Token"] = client.auth.token
            can_live_login = bool(
                allow_live_login
                and client.auth.account
                and client.auth.password
                and client.base_url != AuthData.base_url
            )
            if can_live_login and client.auth_status().token_stale:
                client.ensure_auth()
    return client
