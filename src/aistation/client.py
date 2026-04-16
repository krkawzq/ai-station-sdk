from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import _http, pagination
from .config import AuthData, Config, load_auth, load_config
from .images import ImagesAPI
from .modeling.common import User
from .resources import GroupsAPI, NodesAPI
from .tasks import TasksAPI
from .transport import auth_flow, runtime, session as session_mod
from .workplatform import WorkPlatformsAPI


class AiStationClient:
    """Main SDK entrypoint."""

    def __init__(
        self,
        base_url: str,
        config: Config | None = None,
        auth: AuthData | None = None,
        *,
        auth_path: Path | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config = config or Config()
        self.auth = auth or AuthData(base_url=self.base_url)
        self._auth_path = auth_path
        self._config_path = config_path
        self.session = session_mod.build_session(verify=self.config.verify_ssl)
        self.user: User | None = None

        self.nodes = NodesAPI(self)
        self.groups = GroupsAPI(self)
        self.images = ImagesAPI(self)
        self.tasks = TasksAPI(self)
        self.workplatforms = WorkPlatformsAPI(self)

    @classmethod
    def from_config(
        cls,
        auth_path: Path | None = None,
        config_path: Path | None = None,
    ) -> AiStationClient:
        auth = load_auth(auth_path)
        config = load_config(config_path)
        return cls(
            base_url=auth.base_url,
            config=config,
            auth=auth,
            auth_path=auth_path,
            config_path=config_path,
        )

    def login(
        self,
        account: str | None = None,
        password: str | None = None,
        *,
        captcha: str | None = None,
    ) -> User:
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

    def fetch_captcha(self) -> str:
        """Fetch a fresh captcha image. Returns base64-encoded PNG."""
        from .transport.envelope import check_flag as _check_flag
        body = self._raw_get("/api/ibase/v1/captcha")
        data = _check_flag(body, "/api/ibase/v1/captcha")
        if not isinstance(data, str):
            from .errors import AiStationError
            raise AiStationError("unexpected captcha response", path="/api/ibase/v1/captcha")
        return data

    def ensure_auth(self) -> User:
        restored = auth_flow.ensure_auth(self.session, self.auth, self.user)
        if restored is not None:
            self.user = restored
            return restored
        return self.login()

    def require_user(self) -> User:
        self.user = auth_flow.require_user(
            self.session,
            self.auth,
            self.user,
            login_fn=self.login,
        )
        return self.user

    def logout(self) -> None:
        self.user = None
        auth_flow.logout(self.session, self.auth)

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

    def delete(self, path: str, *, timeout: float | None = None) -> Any:
        return self._request_with_retry("DELETE", path, timeout=timeout)

    def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int = 50,
        page_param: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Legacy page-by-page iterator. Prefer ``list_all`` unless the endpoint
        doesn't accept the ``page=-1`` magic."""
        self._prime_token_header()
        return _http.paginate(
            self.session,
            self.base_url,
            path,
            params=params,
            page_size=page_size,
            timeout=self.config.default_timeout,
            page_param=page_param,
        )

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
        return runtime.request_with_retry(
            raw_request_fn=self._raw_request,
            login_fn=self.login,
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
        self.workplatforms.invalidate_cache()

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
                # Token-valid if request succeeded with flag=true (no auth error)
                result["token_valid"] = bool(body.get("flag"))
            except Exception:
                result["token_valid"] = False
        return result
