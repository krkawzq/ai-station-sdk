from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .. import auth as auth_mod
from ..config import AuthData, Config, save_auth
from ..errors import AuthError, InvalidCredentials
from ..modeling.common import User
from .envelope import check_flag

if TYPE_CHECKING:
    from collections.abc import Callable


class HeaderSession(Protocol):
    headers: Any


def login(
    *,
    base_url: str,
    session: HeaderSession,
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


def user_from_auth(auth: AuthData) -> User | None:
    if not auth.token:
        return None
    return User(
        user_id="",
        account=auth.account,
        user_name="",
        group_id="",
        role_type=-1,
        user_type=-1,
        token=auth.token,
        is_first_login=False,
    )


def merge_user(auth: AuthData, payload: dict[str, Any]) -> User:
    data = dict(payload)
    if not data.get("token"):
        data["token"] = auth.token
    if not data.get("account"):
        data["account"] = auth.account
    return User.from_api(data)


def has_user_profile(user: User | None) -> bool:
    return bool(user is not None and user.account and user.group_id)


def token_is_stale(auth: AuthData, config: Config, *, now: datetime | None = None) -> bool:
    if not auth.token or not auth.token_saved_at:
        return False
    ttl_hours = max(0, int(getattr(config, "token_ttl_hours", 0)))
    if ttl_hours <= 0:
        return False
    saved_at = _parse_saved_at(auth.token_saved_at)
    if saved_at is None:
        return False
    if now is None:
        now = datetime.now(saved_at.tzinfo) if saved_at.tzinfo is not None else datetime.now()
    return now - saved_at >= timedelta(hours=ttl_hours)


def ensure_auth(session: HeaderSession, auth: AuthData, user: User | None) -> User | None:
    if user is not None:
        set_token_header(session, user.token)
        return user
    restored = user_from_auth(auth)
    if restored is not None:
        set_token_header(session, auth.token)
        return restored
    return None


def require_user(
    session: HeaderSession,
    auth: AuthData,
    user: User | None,
    *,
    login_fn: "Callable[[], User]",
    fetch_user_fn: "Callable[[], User] | None" = None,
) -> User:
    if has_user_profile(user):
        assert user is not None
        set_token_header(session, user.token)
        return user
    restored = ensure_auth(session, auth, user)
    if has_user_profile(restored):
        assert restored is not None
        return restored
    if restored is not None and fetch_user_fn is not None:
        try:
            return fetch_user_fn()
        except AuthError:
            if auth.account and auth.password:
                return login_fn()
            raise
    if auth.account and auth.password:
        return login_fn()
    raise AuthError("must login first to populate user information")


def logout(session: HeaderSession, auth: AuthData) -> None:
    auth.token = ""
    auth.token_saved_at = ""
    session.headers.pop("X-Auth-Token", None)


def set_token_header(session: HeaderSession, token: str) -> None:
    if token:
        session.headers["X-Auth-Token"] = token


def prime_token_header(session: HeaderSession, auth: AuthData, user: User | None) -> None:
    if session.headers.get("X-Auth-Token"):
        return
    if user is not None and user.token:
        set_token_header(session, user.token)
    elif auth.token:
        set_token_header(session, auth.token)


def _parse_saved_at(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
