from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._coerce import as_bool, as_int


@dataclass
class User:
    user_id: str
    account: str
    user_name: str
    group_id: str
    role_type: int
    user_type: int
    token: str
    is_first_login: bool
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        return cls(
            user_id=str(d.get("userId", "")),
            account=str(d.get("account", "")),
            user_name=str(d.get("userName", "")),
            group_id=str(d.get("groupId", "")),
            role_type=as_int(d.get("roleType"), -1),
            user_type=as_int(d.get("userType"), -1),
            token=str(d.get("token", "")),
            is_first_login=as_bool(d.get("isFirstLogin")),
            raw=d,
        )


@dataclass
class Port:
    port: int
    target_port: int
    node_port: int
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        return cls(
            port=as_int(d.get("port")),
            target_port=as_int(d.get("targetPort")),
            node_port=as_int(d.get("nodePort")),
            raw=d,
        )
