from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from ..enums import AuthMode, ReauthPolicy
from ..errors import AiStationError

T = TypeVar("T")


@dataclass
class AuthStatus:
    base_url: str
    account: str | None
    auth_mode: AuthMode
    reauth_policy: ReauthPolicy
    has_token: bool
    token_in_session: bool
    token_stale: bool
    can_login: bool
    user_loaded: bool
    user_profile_loaded: bool
    request_ready: bool
    needs_login: bool
    needs_user_refresh: bool


@dataclass
class OperationResult(Generic[T]):
    action: str | None = None
    resource_type: str | None = None
    entity: T | None = None
    payload: dict[str, Any] | None = None
    raw: Any | None = None
    target_id: str | None = None
    target_ids: list[str] = field(default_factory=list)
    created: bool = False
    reused: bool = False
    waited: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.entity is not None

    def require_entity(self, message: str | None = None) -> T:
        if self.entity is not None:
            return self.entity
        detail = message or self._default_unresolved_message()
        raise AiStationError(
            detail,
            err_code="SDK_RESULT_UNRESOLVED",
            err_message=detail,
        )

    def unwrap(self, message: str | None = None) -> T:
        return self.require_entity(message)

    def _default_unresolved_message(self) -> str:
        action = self.action or "operation"
        resource = self.resource_type or "resource"
        target = self.target_id or ", ".join(item for item in self.target_ids if item)
        if target:
            return f"{action} completed without resolved {resource} entity for {target}"
        return f"{action} completed without resolved {resource} entity"
