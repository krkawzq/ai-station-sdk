from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from ... import auth as auth_mod
from ...config import AuthData, save_auth
from ...errors import AuthError, InvalidCredentials
from ...modeling.common import User
from ...transport.auth_flow import set_token_header
from ...transport.envelope import check_flag

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def login(
    *,
    base_url: str,
    session: httpx.AsyncClient,
    auth: AuthData,
    auth_path: Path | None,
    raw_get: "Callable[[str, dict[str, Any] | None, float | None], Awaitable[dict[str, Any]]]",
    raw_post: "Callable[[str, dict[str, Any] | None, float | None], Awaitable[dict[str, Any]]]",
    account: str | None = None,
    password: str | None = None,
    captcha: str | None = None,
) -> User:
    acc = account or auth.account
    pwd = password or auth.password
    if not acc or not pwd:
        raise InvalidCredentials("missing account/password")

    secret_body = await raw_get("/api/ibase/v1/system/secret", None, None)
    public_key = check_flag(secret_body, "/api/ibase/v1/system/secret")
    if not isinstance(public_key, str):
        raise AuthError("unexpected SM2 public key response", path="/api/ibase/v1/system/secret")

    encrypted_password = auth_mod.sm2_encrypt_password(pwd, public_key)
    login_body = await raw_post(
        "/api/ibase/v1/login",
        auth_mod.build_login_payload(acc, encrypted_password, captcha=captcha),
        None,
    )
    user_data = check_flag(login_body, "/api/ibase/v1/login")
    if not isinstance(user_data, dict):
        raise AuthError("unexpected login response payload", path="/api/ibase/v1/login")

    user = User.from_api(user_data)
    auth.base_url = base_url
    auth.account = acc
    auth.password = pwd
    auth.token = user.token
    auth.token_saved_at = datetime.now().isoformat(timespec="seconds")
    set_token_header(session, user.token)
    save_auth(auth, auth_path)
    return user
