from __future__ import annotations

import pytest

from aistation.errors import (
    AiStationError,
    AmbiguousMatchError,
    AuthError,
    InvalidCredentials,
    NotFoundError,
    PermissionDenied,
    ResourceError,
    SpecValidationError,
    TokenExpired,
    ValidationError,
    lookup_error_guide,
)
from aistation.transport import check_flag


def test_error_mapping_token_expired() -> None:
    with pytest.raises(TokenExpired):
        check_flag({"flag": False, "errCode": "IBASE_IAUTH_TOKEN_NOT_FOUND", "errMessage": "token missing"}, "/x")


def test_error_mapping_permission_denied() -> None:
    with pytest.raises(PermissionDenied):
        check_flag({"flag": False, "errCode": "IBASE_NO_PERMISSION", "errMessage": "权限不足"}, "/x")


def test_validation_error_extracts_field_name() -> None:
    with pytest.raises(ValidationError) as exc_info:
        check_flag(
            {
                "flag": False,
                "errCode": "IRESOURCE_NOT_NULL_ILLEGAL",
                "errMessage": "入参[CPU(cpuNum)] 不满足规则：不能为空",
            },
            "/x",
        )
    assert exc_info.value.field_name == "cpuNum"


def test_resource_error_mapping() -> None:
    with pytest.raises(ResourceError):
        check_flag(
            {
                "flag": False,
                "errCode": "IRESOURCE_QUERY_USER_QUOTA_FAILED",
                "errMessage": "配额查询失败",
            },
            "/x",
        )


def test_bad_block_maps_to_auth_error() -> None:
    with pytest.raises(AuthError):
        check_flag({"flag": False, "errCode": "BadBlockException", "errMessage": "oops"}, "/x")


def test_login_message_maps_to_invalid_credentials() -> None:
    with pytest.raises(InvalidCredentials):
        check_flag({"flag": False, "errCode": "X", "errMessage": "用户名或密码错误"}, "/api/ibase/v1/login")


def test_unknown_error_falls_back_to_base_class() -> None:
    with pytest.raises(AiStationError):
        check_flag({"flag": False, "errCode": "UNKNOWN", "errMessage": "boom"}, "/x")


def test_error_hint_and_describe() -> None:
    err = AiStationError(
        "failed",
        err_code="IBASE_NO_PERMISSION",
        err_message="权限不足",
        path="/api/iresource/v1/node",
    )

    assert err.hint() == ("权限不足", "当前账号（role=2 普通用户）无法访问该接口，或该资源组对你不可见")
    text = err.describe()
    assert "[IBASE_NO_PERMISSION] 权限不足" in text
    assert "path: /api/iresource/v1/node" in text
    assert "建议：" in text


def test_lookup_error_guide_and_spec_validation_error() -> None:
    assert lookup_error_guide("IRESOURCE_VALID_JOB_NAME") is not None
    err = SpecValidationError("bad spec", field_name="name")
    assert err.err_code == "SDK_SPEC_VALIDATION"
    assert err.field_name == "name"


def test_not_found_and_ambiguous_match_use_sdk_error_codes() -> None:
    missing = NotFoundError("task", "abc")
    ambiguous = AmbiguousMatchError("image", "pytorch", matches=["x", "y"])

    assert missing.err_code == "SDK_NOT_FOUND"
    assert ambiguous.err_code == "SDK_AMBIGUOUS_MATCH"
    assert missing.hint() is not None
    assert ambiguous.hint() is not None
