from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests  # type: ignore[import-untyped]

from .. import auth as auth_mod
from ..config import AuthData, save_auth
from ..errors import AuthError, InvalidCredentials
from ..modeling.common import User
from .envelope import check_flag

if TYPE_CHECKING:
    from collections.abc import Callable


def login(
    *,
    base_url: str,
    session: requests.Session,
    auth: AuthData,
    auth_path: Path | None,
    raw_get: "Callable[[str, dict[str, Any] | None, float | None], dict[str, Any]]",
    raw_post: "Callable[[str, dict[str, Any] | None, float | None], dict[str, Any]]",
    account: str | None = None,
    password: str | None = None,
    captcha: str | None = None,
) -> User:
    acc = account or auth.account
    pwd = password or auth.password
    if not acc or not pwd:
        raise InvalidCredentials("missing account/password")

    secret_body = raw_get("/api/ibase/v1/system/secret", None, None)
    public_key = check_flag(secret_body, "/api/ibase/v1/system/secret")
    if not isinstance(public_key, str):
        raise AuthError("unexpected SM2 public key response", path="/api/ibase/v1/system/secret")

    encrypted_password = auth_mod.sm2_encrypt_password(pwd, public_key)
    login_body = raw_post(
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


def ensure_auth(session: requests.Session, auth: AuthData, user: User | None) -> User | None:
    if user is not None:
        set_token_header(session, user.token)
        return user
    if auth.token:
        restored = User(
            user_id="",
            account=auth.account,
            user_name="",
            group_id="",
            role_type=-1,
            user_type=-1,
            token=auth.token,
            is_first_login=False,
        )
        set_token_header(session, auth.token)
        return restored
    return None


def require_user(
    session: requests.Session,
    auth: AuthData,
    user: User | None,
    *,
    login_fn: "Callable[[], User]",
) -> User:
    if user is not None and user.group_id:
        set_token_header(session, user.token)
        return user
    if auth.account and auth.password:
        return login_fn()
    raise AuthError("must login first to populate user information")


def logout(session: requests.Session, auth: AuthData) -> None:
    auth.token = ""
    session.headers.pop("X-Auth-Token", None)


def set_token_header(session: requests.Session, token: str) -> None:
    if token:
        session.headers["X-Auth-Token"] = token


def prime_token_header(session: requests.Session, auth: AuthData, user: User | None) -> None:
    if session.headers.get("X-Auth-Token"):
        return
    if user is not None and user.token:
        set_token_header(session, user.token)
    elif auth.token:
        set_token_header(session, auth.token)
