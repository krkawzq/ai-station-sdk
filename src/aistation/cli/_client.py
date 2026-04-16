"""Shared client builder — reads context options into an AiStationClient.

Key policy: for read commands we **only** restore a cached token. If no token
is cached we fail fast with a clear "please run `aistation login`" message
instead of silently attempting a login (which would hang if the saved password
on disk is stale or the network is slow).
"""
from __future__ import annotations

from pathlib import Path

from ..client import AiStationClient
from ..errors import TokenExpired


def make_client(
    *,
    config_path: Path | None = None,
    auth_path: Path | None = None,
    timeout: float | None = None,
    login: bool = True,
    require_token: bool = False,
) -> AiStationClient:
    """Construct a client from config files.

    Modes:
    - ``login=False, require_token=False``: no auth attempt; used by ``login``
      and ``ping`` which must work without a token.
    - ``login=True, require_token=True`` (default for read commands): restore
      the cached token into the session. If no token is cached, raise
      :class:`TokenExpired` immediately so the user sees a useful error rather
      than a silent login attempt with (possibly stale) saved credentials.
    """
    client = AiStationClient.from_config(auth_path=auth_path, config_path=config_path)
    if timeout is not None:
        client.config.default_timeout = timeout
    if login:
        if not client.auth.token:
            if require_token:
                raise TokenExpired(
                    "no cached token; run `aistation login` first",
                    err_code="SDK_CLI_NOT_LOGGED_IN",
                    err_message="no cached token on disk",
                )
            # Only fall through to live login when explicitly asked (login=True,
            # require_token=False) — e.g. a command that supports interactive login.
            client.ensure_auth()
        else:
            # Prime the session header from the cached token without hitting
            # the server. If the token is stale, the next real call will get
            # TokenExpired, which the client's retry logic handles.
            client.session.headers["X-Auth-Token"] = client.auth.token
    return client
