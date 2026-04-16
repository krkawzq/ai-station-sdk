# Clients

This document describes the two primary entry points of the SDK:

- `aistation.AiStationClient`
- `aistation.AsyncAiStationClient`

Both clients expose the same logical API surface. The async client mirrors the sync client closely and differs mainly in awaitability, async context management, and auth-lock behavior.

## Overview

### Sync client

```python
import aistation as A

with A.AiStationClient() as client:
    tasks = client.tasks.list()
```

### Async client

```python
import aistation as A

async with A.AsyncAiStationClient() as client:
    tasks = await client.tasks.list()
```

## Construction

### `AiStationClient(...)`

```python
AiStationClient(
    base_url: str | None = None,
    config: Config | None = None,
    auth: AuthData | None = None,
    *,
    auth_path: Path | None = None,
    config_path: Path | None = None,
    auth_mode: AuthMode | str | None = None,
    reauth_policy: ReauthPolicy | str | None = None,
)
```

### `AsyncAiStationClient(...)`

```python
AsyncAiStationClient(
    base_url: str | None = None,
    config: Config | None = None,
    auth: AuthData | None = None,
    *,
    auth_path: Path | None = None,
    config_path: Path | None = None,
    auth_mode: AuthMode | str | None = None,
    reauth_policy: ReauthPolicy | str | None = None,
)
```

### Constructor behavior

The constructor is intentionally ergonomic:

- If you do not pass `auth`, the client loads auth data from disk with `load_auth()`.
- If you do not pass `config`, the client loads config from disk with `load_config()`.
- If a cached token exists, the client restores it into the HTTP session automatically.
- If the token is stale and login is possible, the client may re-login automatically depending on `auth_mode` and `reauth_policy`.

### Constructor parameters

| Parameter | Type | Meaning |
| --- | --- | --- |
| `base_url` | `str | None` | Overrides the API base URL. If omitted, the client uses `auth.base_url` or the default in `AuthData`. |
| `config` | `Config | None` | Prebuilt runtime configuration. Use this when you want to override values programmatically instead of relying on disk files. |
| `auth` | `AuthData | None` | Prebuilt auth state. Useful in tests or when embedding the SDK into another application. |
| `auth_path` | `Path | None` | Explicit path to the auth JSON file. |
| `config_path` | `Path | None` | Explicit path to the config JSON file. |
| `auth_mode` | `AuthMode | str | None` | Controls startup auth behavior. Strings are accepted and coerced. |
| `reauth_policy` | `ReauthPolicy | str | None` | Controls whether token expiry can trigger an automatic login during requests. Strings are accepted and coerced. |

## Attached API Objects

Both client classes attach the following API objects during construction:

| Attribute | Sync type | Async type | Purpose |
| --- | --- | --- | --- |
| `nodes` | `NodesAPI` | `AsyncNodesAPI` | Raw node inventory and occupancy data |
| `groups` | `GroupsAPI` | `AsyncGroupsAPI` | Aggregated resource groups |
| `images` | `ImagesAPI` | `AsyncImagesAPI` | Image catalog and image operations |
| `tasks` | `TasksAPI` | `AsyncTasksAPI` | Training task operations |
| `workplatforms` | `WorkPlatformsAPI` | `AsyncWorkPlatformsAPI` | Development environment operations |

These objects are the main way you interact with the API after the client is created.

## Authentication Model

The client maintains three related pieces of auth state:

1. `client.auth`
   - The persisted auth container loaded from disk or injected by the caller.
   - Stores `account`, `password`, `token`, and `token_saved_at`.

2. `client.session`
   - The HTTP session object with live headers.
   - Holds the active `X-Auth-Token` header when a token is available.

3. `client.user`
   - The resolved user profile object when the SDK has enough information.
   - May be `None`, token-only, or a fully populated `User`.

### `auth_mode`

`auth_mode` controls what the client does when it starts.

| Value | Meaning |
| --- | --- |
| `AuthMode.AUTO` | Default. Restore disk auth automatically, and eagerly re-login only when it makes sense. |
| `AuthMode.TOKEN_ONLY` | Restore cached token only. No eager login. |
| `AuthMode.LOGIN_IF_POSSIBLE` | If credentials are available, login eagerly. |
| `AuthMode.MANUAL` | Do not automatically restore or login. The caller controls auth manually. |

### `reauth_policy`

`reauth_policy` controls what happens if an API call discovers an expired token.

| Value | Meaning |
| --- | --- |
| `ReauthPolicy.AUTO` | Derived from `auth_mode`. |
| `ReauthPolicy.IF_POSSIBLE` | Re-login automatically when credentials are available. |
| `ReauthPolicy.NEVER` | Never auto-login during a request. |

## Public Properties

### `client.auth_mode`

Returns the resolved `AuthMode`.

### `client.configured_reauth_policy`

Returns the policy passed by the caller, before automatic derivation.

### `client.reauth_policy`

Returns the effective policy after automatic derivation.

### `client.can_login`

Returns `True` when both `account` and `password` are present.

### `client.is_authenticated`

Returns `True` when `auth_status().has_token` is true.

This does not guarantee that the token is valid. It only means a token exists either in the session or in stored auth.

## Authentication Methods

### `from_config(...)`

Sync:

```python
AiStationClient.from_config(
    auth_path: Path | None = None,
    config_path: Path | None = None,
    *,
    auth_mode: AuthMode | str | None = None,
    reauth_policy: ReauthPolicy | str | None = None,
) -> AiStationClient
```

Async:

```python
AsyncAiStationClient.from_config(
    auth_path: Path | None = None,
    config_path: Path | None = None,
    *,
    auth_mode: AuthMode | str | None = None,
    reauth_policy: ReauthPolicy | str | None = None,
) -> AsyncAiStationClient
```

This is a convenience constructor that makes the intent explicit. It behaves the same as calling the constructor without injected `auth` or `config`.

### `login(account=None, password=None, *, captcha=None)`

Sync:

```python
login(
    account: str | None = None,
    password: str | None = None,
    *,
    captcha: str | None = None,
) -> User
```

Async:

```python
await login(
    account: str | None = None,
    password: str | None = None,
    *,
    captcha: str | None = None,
) -> User
```

Behavior:

- If no explicit credentials are passed and the existing cached auth is still fresh, the client may reuse it instead of performing a network login.
- Otherwise the client requests the server login public key, encrypts the password, and performs the real login flow.
- Successful login updates:
  - `client.auth`
  - `client.session` headers
  - `client.user`
  - the auth file on disk

Use `captcha=` when the server demands a captcha after repeated login failures.

### `auth_status() -> AuthStatus`

Returns a structured snapshot of the client auth state.

Important fields:

| Field | Meaning |
| --- | --- |
| `has_token` | A token exists either in the session or in stored auth |
| `token_in_session` | The live session currently carries `X-Auth-Token` |
| `token_stale` | The token is older than `Config.token_ttl_hours` |
| `can_login` | Credentials are available for a real login |
| `request_ready` | The client is in a state where a request can reasonably proceed |
| `needs_login` | The caller should expect auth to fail unless login happens |
| `needs_user_refresh` | A token exists but the user profile has not been fully loaded |

### `prepare_auth()`

Sync:

```python
prepare_auth() -> User | None
```

Async:

```python
await prepare_auth() -> User | None
```

This is the client’s startup/auth-prep helper.

It may:

- restore auth state from disk into the session
- keep a fresh restored token as-is
- eagerly re-login if `auth_mode` allows it
- do nothing in manual mode

Use this when you want to force the client to do its normal automatic auth preparation early.

### `fetch_captcha()`

Sync:

```python
fetch_captcha() -> str
```

Async:

```python
await fetch_captcha() -> str
```

Returns a base64-encoded PNG captcha image fetched from the server.

This is mainly useful when a manual login flow needs to collect captcha input outside the CLI.

### `refresh_user()`

Sync:

```python
refresh_user() -> User
```

Async:

```python
await refresh_user() -> User
```

Loads the current user profile from `/api/ibase/v1/user/base` using the active token.

Use this when:

- you already have a valid token
- `client.user` is incomplete
- you need account metadata such as `group_id` or `role_type`

### `ensure_auth()`

Sync:

```python
ensure_auth() -> User
```

Async:

```python
await ensure_auth() -> User
```

Guarantees that the client ends in an authenticated state or raises an auth-related exception.

Compared to `prepare_auth()`:

- `prepare_auth()` is opportunistic
- `ensure_auth()` is mandatory

### `require_user()`

Sync:

```python
require_user() -> User
```

Async:

```python
await require_user() -> User
```

Guarantees a fully usable `User` object, not just a token.

This method is commonly needed before building task or workplatform payloads because those payloads require user-derived values such as `account` or `group_id`.

### `logout(*, persist=True)`

Sync and async clients both expose the same synchronous method:

```python
logout(*, persist: bool = True) -> None
```

Behavior:

- clears `client.user`
- clears token state from the session and `client.auth`
- optionally writes the cleared auth state back to disk

## Request Methods

These methods expose the low-level request path. They are useful for endpoints that do not yet have a wrapper.

### `get(path, params=None, *, timeout=None)`
### `post(path, json=None, *, timeout=None)`
### `put(path, json=None, *, timeout=None)`
### `delete(path, *, timeout=None)`

Return type: `Any`

The return value is the unwrapped `resData` portion of the server envelope after:

- authentication handling
- token re-login if configured
- retry behavior for transport errors
- envelope validation via `flag`, `errCode`, and `errMessage`

You should only call these directly when:

- there is no higher-level wrapper in the SDK
- you are exploring a newly discovered endpoint
- you need raw endpoint access during debugging

## Pagination Helpers

### `paginate(...)`

Sync:

```python
paginate(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    page_size: int = 50,
    page_param: str | None = None,
    max_pages: int | None = None,
) -> Iterator[dict[str, Any]]
```

Async:

```python
paginate(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    page_size: int = 50,
    page_param: str | None = None,
    max_pages: int | None = None,
) -> AsyncIterator[dict[str, Any]]
```

This is the conservative page-by-page iterator.

Use it when:

- the endpoint does not support the AI Station fast-list convention
- you want explicit page-by-page control

Notes:

- `max_pages` must be `None` or at least `1`
- exceeding `max_pages` raises `AiStationError` with `SDK_MAX_PAGES_EXCEEDED`

### `list_all(...)`

Sync:

```python
list_all(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> list[dict[str, Any]]
```

Async:

```python
list_all(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> list[dict[str, Any]]
```

This is the preferred bulk-list helper.

Behavior:

- it first tries the AI Station fast-list query convention, typically `page=-1&pageSize=-1`
- if the server returns fewer rows than the declared `total`, it falls back to `paginate()`

Prefer `list_all()` unless you already know the endpoint requires manual paging.

## Diagnostics and Maintenance

### `invalidate_caches()`

Sync and async:

```python
invalidate_caches() -> None
```

Clears all SDK-managed hot caches:

- nodes
- images
- tasks
- workplatforms

Use this when you know out-of-band changes happened and you do not want to wait for cache TTLs.

### `ping()`

Sync:

```python
ping() -> dict[str, Any]
```

Async:

```python
await ping() -> dict[str, Any]
```

Returns a diagnostic dictionary and does not raise on failure.

Typical keys:

| Key | Meaning |
| --- | --- |
| `reachable` | Whether `/system/secret` returned a valid envelope |
| `latency_ms` | Measured round-trip latency |
| `token_valid` | Whether a follow-up token-protected endpoint succeeded |
| `account` | Loaded account, if any |
| `base_url` | Effective API base URL |
| `auth_mode` | Effective auth mode |
| `reauth_policy` | Effective reauth policy |
| `token_stale` | Whether the token is considered old |
| `can_login` | Whether credentials exist |
| `user_profile_loaded` | Whether `client.user` is fully populated |
| `error` | Present when reachability probing fails |

## Context Management

### Sync

```python
with AiStationClient() as client:
    ...
```

This closes the underlying `requests.Session` on exit.

### Async

```python
async with AsyncAiStationClient() as client:
    ...
```

This closes the underlying `httpx.AsyncClient` on exit.

The async client also exposes:

```python
await client.close()
await client.aclose()
```

## Sync vs Async Differences

| Topic | Sync | Async |
| --- | --- | --- |
| Context manager | `with` | `async with` |
| Network methods | direct return | `await` required |
| Pagination | `Iterator` | `AsyncIterator` |
| Auth deduplication | no explicit lock | uses an internal `asyncio.Lock` to avoid duplicate concurrent login |
| Shutdown | `close()` | `await close()` or `await aclose()` |

## Recommended Usage Pattern

For normal SDK usage, prefer this pattern:

1. Create the client with default auth loading.
2. Use high-level APIs on `client.tasks`, `client.workplatforms`, `client.images`, and so on.
3. Fall back to `client.get()` / `client.post()` only for endpoints that are not wrapped yet.
4. Use `invalidate_caches()` or per-API `refresh=True` when you need fresh reads immediately.
