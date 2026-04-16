from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import pagination
from .config import AuthData, Config, load_auth, load_config, save_auth
from .enums import AuthMode, ReauthPolicy
from .errors import AiStationError, AuthError
from .images import ImagesAPI
from .modeling.common import User
from .modeling.runtime import AuthStatus
from .resources import GroupsAPI, NodesAPI
from .tasks import TasksAPI
from .transport import auth_flow, runtime, session as session_mod
from .workplatform import WorkPlatformsAPI


def _coerce_auth_mode(value: AuthMode | str | None) -> AuthMode:
    if value is None:
        return AuthMode.AUTO
    if isinstance(value, str):
        return AuthMode(value.lower())
    return value


def _coerce_reauth_policy(value: ReauthPolicy | str | None) -> ReauthPolicy:
    if value is None:
        return ReauthPolicy.AUTO
    if isinstance(value, str):
        return ReauthPolicy(value.lower())
    return value


class AiStationClient:
    """Main SDK entrypoint.

    Default behavior is ergonomic:

    - ``AiStationClient()`` automatically loads ``auth.json`` and ``config.json``
    - cached tokens are restored into the session automatically
    - stale cached tokens are refreshed before the next real request when login is possible

    ``auth_mode`` controls auth preparation:

    - ``AUTO``: sensible default for SDK use
    - ``TOKEN_ONLY``: restore cached token only, no eager login
    - ``LOGIN_IF_POSSIBLE``: eagerly refresh auth when credentials exist
    - ``MANUAL``: no automatic restore/login
    """

    def __init__(
        self,
        base_url: str | None = None,
        config: Config | None = None,
        auth: AuthData | None = None,
        *,
        auth_path: Path | None = None,
        config_path: Path | None = None,
        auth_mode: AuthMode | str | None = None,
        reauth_policy: ReauthPolicy | str | None = None,
    ) -> None:
        loaded_auth_from_disk = auth is None
        loaded_auth = auth or load_auth(auth_path)
        loaded_config = config or load_config(config_path)
        resolved_base_url = (base_url or loaded_auth.base_url or AuthData.base_url).rstrip("/")
        loaded_auth.base_url = resolved_base_url

        self.base_url = resolved_base_url
        self.config = loaded_config
        self.auth = loaded_auth
        self._auth_path = auth_path
        self._config_path = config_path
        self._loaded_auth_from_disk = loaded_auth_from_disk
        self._auth_mode = _coerce_auth_mode(auth_mode)
        self._configured_reauth_policy = _coerce_reauth_policy(reauth_policy)
        self.session = session_mod.build_session(verify=self.config.verify_ssl)
        self.user: User | None = None

        self.nodes = NodesAPI(self)
        self.groups = GroupsAPI(self)
        self.images = ImagesAPI(self)
        self.tasks = TasksAPI(self)
        self.workplatforms = WorkPlatformsAPI(self)

        if self._should_prepare_auth():
            self.prepare_auth()

    @classmethod
    def from_config(
        cls,
        auth_path: Path | None = None,
        config_path: Path | None = None,
        *,
        auth_mode: AuthMode | str | None = None,
        reauth_policy: ReauthPolicy | str | None = None,
    ) -> AiStationClient:
        return cls(
            auth_path=auth_path,
            config_path=config_path,
            auth_mode=auth_mode,
            reauth_policy=reauth_policy,
        )

    def login(
        self,
        account: str | None = None,
        password: str | None = None,
        *,
        captcha: str | None = None,
    ) -> User:
        reused = self._reuse_fresh_auth(
            account=account,
            password=password,
            captcha=captcha,
        )
        if reused is not None:
            return reused
        self.user = auth_flow.login(
            base_url=self.base_url,
            session=self.session,
            auth=self.auth,
            auth_path=self._auth_path,
            raw_get=self._raw_get,
            raw_post=self._raw_post,
            account=account,
            password=password,
            captcha=captcha,
        )
        return self.user

    @property
    def auth_mode(self) -> AuthMode:
        return self._auth_mode

    @property
    def configured_reauth_policy(self) -> ReauthPolicy:
        return self._configured_reauth_policy

    @property
    def reauth_policy(self) -> ReauthPolicy:
        return self._effective_reauth_policy()

    @property
    def can_login(self) -> bool:
        return bool(self.auth.account and self.auth.password)

    @property
    def is_authenticated(self) -> bool:
        return self.auth_status().has_token

    def auth_status(self) -> AuthStatus:
        has_token = bool(self.session.headers.get("X-Auth-Token") or self.auth.token)
        token_in_session = bool(self.session.headers.get("X-Auth-Token"))
        token_stale = self._token_is_stale()
        can_login = self._can_live_login()
        user_loaded = self.user is not None
        user_profile_loaded = auth_flow.has_user_profile(self.user)
        effective_reauth = self._effective_reauth_policy()
        request_ready = (
            (has_token and (not token_stale or effective_reauth is not ReauthPolicy.NEVER))
            or (not has_token and effective_reauth is ReauthPolicy.IF_POSSIBLE and can_login)
        )
        needs_login = not request_ready
        needs_user_refresh = has_token and not user_profile_loaded
        return AuthStatus(
            base_url=self.base_url,
            account=self.auth.account or None,
            auth_mode=self.auth_mode,
            reauth_policy=effective_reauth,
            has_token=has_token,
            token_in_session=token_in_session,
            token_stale=token_stale,
            can_login=can_login,
            user_loaded=user_loaded,
            user_profile_loaded=user_profile_loaded,
            request_ready=request_ready,
            needs_login=needs_login,
            needs_user_refresh=needs_user_refresh,
        )

    def prepare_auth(self) -> User | None:
        if not self._should_prepare_auth():
            return self.user

        restored = auth_flow.ensure_auth(self.session, self.auth, self.user)
        token_stale = self._token_is_stale()

        if restored is not None and not token_stale:
            self.user = restored
            return restored

        if self._should_eager_login() and (restored is None or token_stale):
            return self.login()

        if restored is not None:
            self.user = restored
            return restored
        return None

    def fetch_captcha(self) -> str:
        """Fetch a fresh captcha image. Returns base64-encoded PNG."""
        from .transport.envelope import check_flag as _check_flag

        body = self._raw_get("/api/ibase/v1/captcha")
        data = _check_flag(body, "/api/ibase/v1/captcha")
        if not isinstance(data, str):
            from .errors import AiStationError

            raise AiStationError("unexpected captcha response", path="/api/ibase/v1/captcha")
        return data

    def refresh_user(self) -> User:
        """Load the current user profile from the server using the active token."""
        self.prepare_auth()
        data = self.get("/api/ibase/v1/user/base", timeout=10)
        if not isinstance(data, dict):
            raise AuthError("unexpected user profile payload", path="/api/ibase/v1/user/base")
        self.user = auth_flow.merge_user(self.auth, data)
        return self.user

    def ensure_auth(self) -> User:
        restored = auth_flow.ensure_auth(self.session, self.auth, self.user)
        if restored is not None and not self._token_is_stale():
            self.user = restored
            return restored
        if self._can_live_login():
            return self.login()
        if restored is not None:
            self.user = restored
            return restored
        return self.login()

    def require_user(self) -> User:
        self.user = auth_flow.require_user(
            self.session,
            self.auth,
            self.user,
            login_fn=self._reauth_login,
            fetch_user_fn=self.refresh_user,
        )
        return self.user

    def logout(self, *, persist: bool = True) -> None:
        self.user = None
        auth_flow.logout(self.session, self.auth)
        if persist:
            save_auth(self.auth, self._auth_path)

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> AiStationClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        return self._request_with_retry("GET", path, params=params, timeout=timeout)

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        return self._request_with_retry("POST", path, json=json, timeout=timeout)

    def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        return self._request_with_retry("PUT", path, json=json, timeout=timeout)

    def delete(self, path: str, *, timeout: float | None = None) -> Any:
        return self._request_with_retry("DELETE", path, timeout=timeout)

    def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int = 50,
        page_param: str | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Legacy page-by-page iterator. Prefer ``list_all`` unless the endpoint
        doesn't accept the ``page=-1`` magic."""

        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be >= 1 or None")
        if self._should_prepare_auth():
            self.prepare_auth()
        self._prime_token_header()
        query: dict[str, Any] = dict(params or {})
        query.setdefault("pageSize", page_size)
        resolved_page_param = page_param or pagination.page_param_for(path)
        page = 1
        while True:
            if max_pages is not None and page > max_pages:
                raise AiStationError(
                    f"pagination exceeded configured max_pages={max_pages}",
                    err_code="SDK_MAX_PAGES_EXCEEDED",
                    err_message=f"pagination exceeded configured max_pages={max_pages}",
                    path=path,
                )
            query[resolved_page_param] = page
            data = self.get(path, params=query, timeout=self.config.default_timeout)
            if not isinstance(data, dict):
                break
            rows = data.get("data")
            if not isinstance(rows, list):
                break
            for row in rows:
                if isinstance(row, dict):
                    yield row
            total_pages = int(data.get("totalPages") or 1)
            if page >= total_pages:
                break
            page += 1

    def list_all(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch every row in a single request via AI Station's ``page=-1, pageSize=-1``
        fast path (observed in the official front-end's NodemonitorList / UserIndex).

        Falls back to page-by-page iteration if the response suggests the server
        did not honor the magic values (``total > len(data)``).
        """

        self._prime_token_header()
        policy = pagination.policy_for(path)
        query = pagination.build_fast_list_query(path, params)
        data = self.get(path, params=query, timeout=timeout)

        rows: list[dict[str, Any]]
        total: int | None = None
        if isinstance(data, dict):
            raw = data.get("data")
            rows = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
            total_val = data.get("total")
            if isinstance(total_val, int):
                total = total_val
        elif isinstance(data, list):
            rows = [r for r in data if isinstance(r, dict)]
        else:
            rows = []

        if total is not None and len(rows) < total:
            fallback_params = pagination.strip_pagination_params(params)
            rows = list(
                self.paginate(
                    path,
                    params=fallback_params,
                    page_size=50,
                    page_param=policy.page_param,
                )
            )
        return rows

    def _set_token_header(self, token: str) -> None:
        auth_flow.set_token_header(self.session, token)

    def _prime_token_header(self) -> None:
        auth_flow.prime_token_header(self.session, self.auth, self.user)

    def _raw_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return runtime.raw_request(
            self.session,
            self.base_url,
            self.config,
            method,
            path,
            params=params,
            json=json,
            timeout=timeout,
        )

    def _raw_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._raw_request("GET", path, params=params, timeout=timeout)

    def _raw_post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._raw_request("POST", path, json=json, timeout=timeout)

    def _raw_put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._raw_request("PUT", path, json=json, timeout=timeout)

    def _raw_delete(self, path: str, timeout: float | None = None) -> dict[str, Any]:
        return self._raw_request("DELETE", path, timeout=timeout)

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        if self._should_prepare_auth():
            self.prepare_auth()
        return runtime.request_with_retry(
            raw_request_fn=self._raw_request,
            reauth_fn=self._reauth_login if self._can_reauth_on_expiry() else None,
            prime_token_header_fn=self._prime_token_header,
            config=self.config,
            method=method,
            path=path,
            params=params,
            json=json,
            timeout=timeout,
        )

    def _timeout_for(self, path: str) -> float:
        return runtime.timeout_for(self.config, path)

    def invalidate_caches(self) -> None:
        """Clear SDK-managed hot caches."""

        self.nodes.invalidate_cache()
        self.images.invalidate_cache()
        self.tasks.invalidate_cache()
        self.workplatforms.invalidate_cache()

    def _should_prepare_auth(self) -> bool:
        return self._auth_mode is not AuthMode.MANUAL

    def _should_eager_login(self) -> bool:
        if not self._can_live_login():
            return False
        if self._auth_mode is AuthMode.LOGIN_IF_POSSIBLE:
            return True
        return self._auth_mode is AuthMode.AUTO and self._loaded_auth_from_disk

    def _can_live_login(self) -> bool:
        return self.can_login and self.base_url != AuthData.base_url

    def _effective_reauth_policy(self) -> ReauthPolicy:
        if self._configured_reauth_policy is not ReauthPolicy.AUTO:
            return self._configured_reauth_policy
        if self._auth_mode in {AuthMode.AUTO, AuthMode.LOGIN_IF_POSSIBLE}:
            return ReauthPolicy.IF_POSSIBLE
        return ReauthPolicy.NEVER

    def _can_reauth_on_expiry(self) -> bool:
        return self._effective_reauth_policy() is ReauthPolicy.IF_POSSIBLE and self._can_live_login()

    def _reauth_login(self) -> User:
        if not self._can_reauth_on_expiry():
            raise AuthError(
                "automatic re-login is disabled for this client",
                err_code="SDK_REAUTH_DISABLED",
                err_message="automatic re-login is disabled for this client",
            )
        return self.login(
            account=self.auth.account or None,
            password=self.auth.password or None,
        )

    def _token_is_stale(self) -> bool:
        return auth_flow.token_is_stale(self.auth, self.config)

    def _reuse_fresh_auth(
        self,
        *,
        account: str | None = None,
        password: str | None = None,
        captcha: str | None = None,
    ) -> User | None:
        if account is not None or password is not None or captcha is not None:
            return None
        restored = auth_flow.ensure_auth(self.session, self.auth, self.user)
        if restored is None or self._token_is_stale():
            return None
        self.user = restored
        return restored

    def ping(self) -> dict[str, Any]:
        """Quick health check. Returns a dict with:

        - ``reachable`` — server responded (200 + valid JSON envelope)
        - ``latency_ms`` — round-trip for /system/secret
        - ``token_valid`` — cached token still authenticates
        - ``account`` — loaded account (if any)

        Does not raise; diagnostic use.
        """

        import time as _time

        result: dict[str, Any] = {
            "reachable": False,
            "latency_ms": None,
            "token_valid": None,
            "account": self.auth.account or None,
            "base_url": self.base_url,
        }
        status = self.auth_status()
        result.update(
            {
                "auth_mode": status.auth_mode,
                "reauth_policy": status.reauth_policy,
                "token_stale": status.token_stale,
                "can_login": status.can_login,
                "user_profile_loaded": status.user_profile_loaded,
            }
        )
        t0 = _time.time()
        try:
            body = self._raw_get("/api/ibase/v1/system/secret", timeout=10)
            result["latency_ms"] = int((_time.time() - t0) * 1000)
            result["reachable"] = bool(body.get("flag"))
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result
        if self.auth.token:
            self._prime_token_header()
            try:
                body = self._raw_get("/api/ibase/v1/system/identity-source/type", timeout=10)
                result["token_valid"] = bool(body.get("flag"))
            except Exception:
                result["token_valid"] = False
        return result
