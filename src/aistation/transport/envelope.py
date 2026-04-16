from __future__ import annotations

import re
from typing import Any

from ..errors import (
    AiStationError,
    AuthError,
    InvalidCredentials,
    PermissionDenied,
    ResourceError,
    TokenExpired,
    ValidationError,
)

_ERR_CODE_MAP = {
    "IBASE_IAUTH_TOKEN_NOT_FOUND": TokenExpired,
    "IBASE_NO_PERMISSION": PermissionDenied,
    "IRESOURCE_NOT_NULL_ILLEGAL": ValidationError,
    "IRESOURCE_QUERY_USER_QUOTA_FAILED": ResourceError,
}
_FIELD_RE = re.compile(r"入参\[[^()（）]*[(（](\w+)[)）]\]")
_INVALID_LOGIN_RE = re.compile(r"(用户名|账号|密码|password|account)", re.IGNORECASE)


def check_flag(body: dict[str, Any], path: str) -> Any:
    if not isinstance(body, dict):
        raise AiStationError(f"non-JSON response from {path}: {body!r}", path=path)
    if body.get("flag"):
        return body.get("resData")

    code = str(body.get("errCode") or "")
    message = str(body.get("errMessage") or "")

    if "BadBlockException" in code or "BadBlockException" in message:
        raise AuthError(message or code, err_code=code, err_message=message, path=path)

    if path == "/api/ibase/v1/login" and _INVALID_LOGIN_RE.search(message):
        raise InvalidCredentials(
            message or "invalid account/password",
            err_code=code,
            err_message=message,
            path=path,
        )

    exc_cls = _ERR_CODE_MAP.get(code, AiStationError)
    kwargs: dict[str, Any] = {"err_code": code or None, "err_message": message or None, "path": path}

    if exc_cls is ValidationError:
        match = _FIELD_RE.search(message)
        field_name = match.group(1) if match else None
        raise ValidationError(message, field_name=field_name, **kwargs)

    raise exc_cls(message or code or f"request failed: {path}", **kwargs)
