# Reference

This document is the low-level reference for the SDK's supporting objects:

- configuration and auth containers
- persistence helpers
- runtime/result wrappers
- public data models
- enums
- errors

Higher-level workflow objects such as `TaskSpec`, `WorkPlatformSpec`, and the client-attached APIs are documented in the other tutorial files.

## Configuration and Persistence

The configuration layer lives in `aistation.config`.

### Module constants

These constants are useful when you want to inspect or override the SDK's default storage locations.

| Constant | Type | Meaning |
| --- | --- | --- |
| `CONFIG_DIR` | `Path` | Base configuration directory resolved with `platformdirs.user_config_dir("aistation")`. |
| `AUTH_FILE` | `Path` | Default auth file path, normally `CONFIG_DIR / "auth.json"`. |
| `CONFIG_FILE` | `Path` | Default config file path, normally `CONFIG_DIR / "config.json"`. |

## `AuthData`

```python
AuthData(
    base_url: str = "https://aistation.example.invalid",
    account: str = "",
    password: str = "",
    token: str = "",
    token_saved_at: str = "",
)
```

`AuthData` is the persisted auth container used by both sync and async clients.

### Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `base_url` | `str` | API base URL used for requests and persisted auth state. |
| `account` | `str` | Login account name. |
| `password` | `str` | Login password stored in plain text if you choose to persist it. |
| `token` | `str` | Cached auth token. |
| `token_saved_at` | `str` | Token timestamp string used for TTL checks. |

### Notes

- The SDK mutates this object during login, logout, and token restore flows.
- The client may load it from disk automatically.
- `load_auth()` can override `account`, `password`, and `base_url` from environment variables.

## `Config`

```python
Config(
    default_timeout: float = 15.0,
    verify_ssl: bool = False,
    image_registry_prefix: str = "192.168.108.1:5000",
    default_project_id: str | None = None,
    log_level: str = "INFO",
    max_retries: int = 0,
    token_ttl_hours: int = 24,
)
```

`Config` holds general runtime settings rather than credentials.

### Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `default_timeout` | `float` | Default request timeout used by client helpers when no explicit timeout is passed. |
| `verify_ssl` | `bool` | Whether HTTPS certificate verification is enabled for the HTTP client/session. |
| `image_registry_prefix` | `str` | Registry prefix used when the SDK needs to normalize or compare image references. |
| `default_project_id` | `str \| None` | Optional default project/group identifier used by some payload-building paths. |
| `log_level` | `str` | General runtime log level string. |
| `max_retries` | `int` | Maximum low-level retry count for request flows that support retries. |
| `token_ttl_hours` | `int` | Age threshold used when deciding whether a cached token is stale. |

## `load_auth(path=None)`

```python
load_auth(path: Path | None = None) -> AuthData
```

Loads auth state from JSON and returns a fully populated `AuthData`.

### Behavior

- If `path` is omitted, the function reads from `AUTH_FILE`.
- If the file does not exist, it returns a default `AuthData`.
- The file must contain a JSON object. Non-object payloads raise `ValueError`.
- After file loading, selected environment variables override the file values.

### Environment-variable overrides

`load_auth()` applies these overrides after reading the file:

| Variable | Effect |
| --- | --- |
| `AISTATION_ACCOUNT` | Replaces `AuthData.account` |
| `AISTATION_PASSWORD` | Replaces `AuthData.password` |
| `AISTATION_BASE_URL` | Replaces `AuthData.base_url` |
| `AI_STATION_URL` | Fallback override for `base_url` if `AISTATION_BASE_URL` is not set |

### Return value

Always returns an `AuthData` object, even when the file is absent.

## `save_auth(data, path=None)`

```python
save_auth(data: AuthData, path: Path | None = None) -> None
```

Persists an `AuthData` object to disk.

### Behavior

- If `path` is omitted, the function writes to `AUTH_FILE`.
- Parent directories are created automatically when missing.
- The write is atomic: the SDK writes to a temporary file and then replaces the final path.
- The SDK attempts to set restrictive filesystem permissions on the directory and file.

### File format

The output is JSON with:

- UTF-8 encoding
- `indent=2`
- `sort_keys=True`

## `load_config(path=None)`

```python
load_config(path: Path | None = None) -> Config
```

Loads the runtime configuration file.

### Behavior

- If `path` is omitted, the function reads from `CONFIG_FILE`.
- If the file does not exist, it returns a default `Config`.
- Values are type-coerced rather than trusted blindly.
- Non-object JSON raises `ValueError`.

### Coercion behavior

The loader attempts to coerce values into the expected types:

- numeric strings can become `float` or `int`
- common truthy/falsey strings such as `"true"` and `"false"` can become `bool`
- invalid values fall back to the dataclass defaults

### No `save_config()`

The SDK currently exposes `load_config()` but not a public `save_config()` helper.

## `TTLCache[T]`

```python
TTLCache(ttl: float = 60.0)
```

`TTLCache` is a small in-memory cache used by the SDK's read-heavy APIs.

It is exported because advanced users may want to reuse the same behavior in custom wrappers.

### Constructor parameter

| Parameter | Meaning |
| --- | --- |
| `ttl` | Entry lifetime in seconds. |

### Cache model

- Each cache entry stores a value plus the monotonic timestamp when it was set.
- The cache can store one default unnamed entry or multiple keyed entries.
- Expired entries are removed lazily when you query them.

### Methods

#### `get(key=_DEFAULT_SLOT)`

```python
get(key: object = _DEFAULT_SLOT) -> T | None
```

Returns the cached value or `None` if the key is absent or expired.

#### `set(value, key=_DEFAULT_SLOT)`

```python
set(value: T, key: object = _DEFAULT_SLOT) -> None
```

Stores `value` under `key`.

#### `expired(key=_DEFAULT_SLOT)`

```python
expired(key: object = _DEFAULT_SLOT) -> bool
```

Returns `True` when:

- the key is missing
- the key exists but the entry age is at least `ttl`

If the entry is expired, the cache removes it.

#### `invalidate(key=_ALL_SLOTS)`

```python
invalidate(key: object = _ALL_SLOTS) -> None
```

Clears:

- the whole cache when called with the default sentinel
- one keyed slot when called with an explicit key

#### `age(key=_DEFAULT_SLOT)`

```python
age(key: object = _DEFAULT_SLOT) -> float | None
```

Returns the current age in seconds or `None` if the key was never set.

## Runtime and Result Models

These objects live under `aistation.modeling.runtime` and are also re-exported from the top-level package.

## `AuthStatus`

```python
AuthStatus(
    base_url: str,
    account: str | None,
    auth_mode: AuthMode,
    reauth_policy: ReauthPolicy,
    has_token: bool,
    token_in_session: bool,
    token_stale: bool,
    can_login: bool,
    user_loaded: bool,
    user_profile_loaded: bool,
    request_ready: bool,
    needs_login: bool,
    needs_user_refresh: bool,
)
```

`AuthStatus` is the structured return type of `client.auth_status()`.

### Fields

| Field | Meaning |
| --- | --- |
| `base_url` | Effective API base URL used by the client. |
| `account` | Known account name or `None` if unavailable. |
| `auth_mode` | Effective startup auth mode. |
| `reauth_policy` | Effective reauth policy after automatic derivation. |
| `has_token` | Whether the client currently has a token in memory or persisted auth. |
| `token_in_session` | Whether the active HTTP session already carries the token header. |
| `token_stale` | Whether the token is older than the configured TTL. |
| `can_login` | Whether account and password are available for a real login. |
| `user_loaded` | Whether `client.user` is non-`None`. |
| `user_profile_loaded` | Whether the SDK considers the loaded `User` sufficiently populated. |
| `request_ready` | Whether the client is in a state where a normal request can reasonably proceed. |
| `needs_login` | Whether the caller should expect an auth failure unless login happens first. |
| `needs_user_refresh` | Whether a token exists but the user profile is not fully loaded. |

## `OperationResult[T]`

```python
OperationResult[T](
    action: str | None = None,
    resource_type: str | None = None,
    entity: T | None = None,
    payload: dict[str, Any] | None = None,
    raw: Any | None = None,
    target_id: str | None = None,
    target_ids: list[str] = [],
    created: bool = False,
    reused: bool = False,
    waited: bool = False,
    extras: dict[str, Any] = {},
)
```

`OperationResult` is the common wrapper returned by mutating operations such as task creation, deletion, image import, and workplatform actions.

### Fields

| Field | Meaning |
| --- | --- |
| `action` | Short action label such as `"create"`, `"delete"`, `"stop"`, or `"check"`. |
| `resource_type` | Logical resource label such as `"task"`, `"image"`, or `"workplatform"`. |
| `entity` | Resolved model object when the SDK was able to fetch or infer it. |
| `payload` | Payload sent by the SDK, when relevant. |
| `raw` | Raw API response or operation-specific raw data. |
| `target_id` | Single primary target identifier. |
| `target_ids` | Multiple target identifiers for batch-style operations. |
| `created` | Whether the operation created a new resource. |
| `reused` | Whether the SDK reused an existing matching resource instead of creating a new one. |
| `waited` | Whether the SDK performed an additional wait/poll step. |
| `extras` | Operation-specific metadata that does not fit the standard fields. |

### Property

#### `resolved`

```python
result.resolved -> bool
```

Returns `True` when `entity` is not `None`.

### Methods

#### `require_entity(message=None)`

```python
require_entity(message: str | None = None) -> T
```

Returns `entity` when present. Otherwise raises `AiStationError` with `err_code="SDK_RESULT_UNRESOLVED"`.

#### `unwrap(message=None)`

```python
unwrap(message: str | None = None) -> T
```

Alias of `require_entity()`.

## Data Models

The SDK exposes plain dataclasses for parsed API responses. In almost all cases:

- the dataclass fields contain normalized values
- the original API payload remains available in `.raw`
- classmethod constructors such as `from_api()` accept one raw server dictionary

## `User`

```python
User(
    user_id: str,
    account: str,
    user_name: str,
    group_id: str,
    role_type: int,
    user_type: int,
    token: str,
    is_first_login: bool,
    raw: dict[str, Any] = {},
)
```

### Fields

| Field | Meaning |
| --- | --- |
| `user_id` | User identifier from the backend. |
| `account` | Login account string. |
| `user_name` | Human-readable display name. |
| `group_id` | Primary group identifier associated with the user. |
| `role_type` | Numeric role type. See `RoleType` in the enums section for common values. |
| `user_type` | Backend user-type integer. |
| `token` | Token value when returned by the auth/user endpoints. |
| `is_first_login` | Whether the backend considers this the first login. |
| `raw` | Original server dictionary. |

### Classmethod

```python
User.from_api(d: dict[str, Any]) -> User
```

Builds a `User` from one API dictionary.

## `Port`

```python
Port(
    port: int,
    target_port: int,
    node_port: int,
    raw: dict[str, Any] = {},
)
```

### Fields

| Field | Meaning |
| --- | --- |
| `port` | Declared container/service port. |
| `target_port` | Target port inside the container/service definition. |
| `node_port` | Externally reachable node port exposed by the cluster. |
| `raw` | Original server dictionary. |

### Classmethod

```python
Port.from_api(d: dict[str, Any]) -> Port
```

## `Node`

```python
Node(
    node_id: str,
    node_name: str,
    node_ip: str,
    group_id: str,
    group_name: str,
    card_type: str,
    card_kind: str,
    card_memory_gb: int,
    cards_total: int,
    cards_used: int,
    cpu: int,
    cpu_used: int,
    memory_gb: int,
    disk_gb: int,
    switch_type: str,
    status: str,
    resource_status: str,
    role: str,
    task_count: int,
    task_users: list[str],
    is_mig: bool,
    raw: dict[str, Any] = {},
)
```

### Fields

| Field | Meaning |
| --- | --- |
| `node_id` | Node identifier. |
| `node_name` | Node hostname or logical name. |
| `node_ip` | Node IP address. |
| `group_id` | Resource-group identifier. |
| `group_name` | Resource-group display name. |
| `card_type` | Accelerator model string. |
| `card_kind` | Accelerator kind such as `GPU` or `CPU`. |
| `card_memory_gb` | Per-card memory in GB-like backend units. |
| `cards_total` | Total accelerator cards on the node. |
| `cards_used` | Cards currently marked as used. |
| `cpu` | Total CPU cores. |
| `cpu_used` | Used CPU cores. |
| `memory_gb` | Total memory in GB-like backend units. |
| `disk_gb` | Total disk size in GB-like backend units. |
| `switch_type` | Interconnect string, normalized to lowercase by `from_api()`. |
| `status` | Node status string from the backend. |
| `resource_status` | Backend resource-availability status string. |
| `role` | Backend node-role string. |
| `task_count` | Number of tasks currently associated with the node. |
| `task_users` | User list derived from the backend payload. |
| `is_mig` | Whether the node is flagged as MIG-capable or MIG-configured. |
| `raw` | Original server dictionary. |

### Property

```python
node.cards_free -> int
```

Returns `max(0, cards_total - cards_used)`.

### Classmethod

```python
Node.from_api(d: dict[str, Any]) -> Node
```

## `ResourceGroup`

```python
ResourceGroup(
    group_id: str,
    group_name: str,
    card_type: str,
    card_kind: str,
    switch_type: str,
    node_count: int = 0,
    total_cards: int = 0,
    used_cards: int = 0,
    total_cpu: int = 0,
    total_memory_gb: int = 0,
    node_names: list[str] = [],
    raw: dict[str, Any] = {},
)
```

`ResourceGroup` is usually synthesized by the SDK by aggregating node rows rather than parsed directly from one backend payload.

### Fields

| Field | Meaning |
| --- | --- |
| `group_id` | Group identifier. |
| `group_name` | Group display name. |
| `card_type` | Primary accelerator model string for the group. |
| `card_kind` | Group accelerator kind such as `GPU` or `CPU`. |
| `switch_type` | Interconnect type string. |
| `node_count` | Number of nodes in the aggregated group. |
| `total_cards` | Total accelerator cards across the group. |
| `used_cards` | Used accelerator cards across the group. |
| `total_cpu` | Total CPU cores across the group. |
| `total_memory_gb` | Total memory across the group. |
| `node_names` | Node names belonging to the group. |
| `raw` | Aggregated or raw backing data, depending on how the object was produced. |

### Property

```python
group.free_cards -> int
```

Returns `max(0, total_cards - used_cards)`.

## `Image`

```python
Image(
    id: str,
    name: str,
    tag: str,
    image_type: str,
    share: int,
    size_bytes: int,
    pull_count: int,
    owner: str,
    make_type: int,
    logo_id: str | None,
    create_time: str,
    update_time: str,
    raw: dict[str, Any] = {},
)
```

### Fields

| Field | Meaning |
| --- | --- |
| `id` | Image identifier. |
| `name` | Image name without the tag. |
| `tag` | Image tag. |
| `image_type` | Framework/category string such as `pytorch` or `other`. |
| `share` | Share mode integer. See `ShareType`. |
| `size_bytes` | Image size in bytes-like backend units. |
| `pull_count` | Popularity metric used by recommendation helpers. |
| `owner` | Image owner/user name. |
| `make_type` | Image build/make type integer. See `MakeType`. |
| `logo_id` | Optional logo identifier. |
| `create_time` | Creation-time string from the backend. |
| `update_time` | Update-time string from the backend. |
| `raw` | Original server dictionary. |

### Property

```python
image.full_ref -> str
```

Returns:

- `"name:tag"` when `tag` is non-empty
- `name` when `tag` is empty

### Classmethod

```python
Image.from_api(d: dict[str, Any]) -> Image
```

## `ImageType_`

```python
ImageType_(
    id: str,
    name: str,
    raw: dict[str, Any] = {},
)
```

`ImageType_` is the parsed object returned by image-type metadata queries such as `images.types()` and `enumerate_form_context()`.

### Fields

| Field | Meaning |
| --- | --- |
| `id` | Backend type identifier. |
| `name` | Backend type name string. |
| `raw` | Original server dictionary. |

### Classmethod

```python
ImageType_.from_api(d: dict[str, Any]) -> ImageType_
```

## `JobVolume`

```python
JobVolume(
    file_model: int,
    function_model: int,
    volume_mount: str,
    storage_name: str,
    bucket: str = "",
    origin_path: str | None = None,
    dataset_cache_type: str | None = None,
    file_type: str | None = None,
    is_unzip: bool = False,
    volume_mount_alias: str | None = None,
    storage_type: str | None = None,
    raw: dict[str, Any] = {},
)
```

`JobVolume` describes one task-mounted storage attachment.

### Fields

| Field | Meaning |
| --- | --- |
| `file_model` | Backend file-model integer. |
| `function_model` | Backend function-model integer. See `FunctionModel`. |
| `volume_mount` | Mount path inside the workload. |
| `storage_name` | Storage backend name. |
| `bucket` | Bucket or namespace name. |
| `origin_path` | Optional original dataset/model path. |
| `dataset_cache_type` | Optional dataset-cache mode. |
| `file_type` | Optional file-type string. |
| `is_unzip` | Whether the backend should unzip the mounted content. |
| `volume_mount_alias` | Optional alias used by some backend flows. |
| `storage_type` | Optional storage-type string. |
| `raw` | Original server dictionary. |

### Methods

#### `to_api()`

```python
to_api() -> dict[str, Any]
```

Builds the backend payload dictionary for this volume.

#### `from_api(d)`

```python
JobVolume.from_api(d: dict[str, Any]) -> JobVolume
```

## `Pod`

```python
Pod(
    pod_id: str,
    pod_name: str,
    pod_name_changed: str,
    pod_status: str,
    node_name: str,
    node_ip: str,
    pod_ip: str,
    gpu_ids: str,
    gpu_names: str,
    pod_gpu_type: str,
    ports: list[Port],
    restart_count: int,
    switch_type: str,
    create_time_ms: int,
    raw: dict[str, Any] = {},
)
```

### Fields

| Field | Meaning |
| --- | --- |
| `pod_id` | Pod identifier. |
| `pod_name` | Current pod name. |
| `pod_name_changed` | Alternate or renamed pod name field exposed by the backend. |
| `pod_status` | Pod lifecycle status string. See `PodStatus` for common values. |
| `node_name` | Host node name. |
| `node_ip` | Host node IP address. |
| `pod_ip` | Pod IP address. |
| `gpu_ids` | Raw GPU-ID string from the backend. |
| `gpu_names` | Raw GPU-name string from the backend. |
| `pod_gpu_type` | Pod GPU type string. |
| `ports` | Parsed list of `Port` objects. |
| `restart_count` | Pod restart count. |
| `switch_type` | Interconnect type string. |
| `create_time_ms` | Creation timestamp in milliseconds-like backend units. |
| `raw` | Original server dictionary. |

### Property

```python
pod.external_urls -> list[str]
```

Returns `["node_ip:node_port", ...]` for each parsed port with a usable `node_port`.

### Classmethod

```python
Pod.from_api(d: dict[str, Any]) -> Pod
```

## `Task`

```python
Task(
    id: str,
    name: str,
    status: str,
    user_id: str,
    user_name: str,
    project_id: str,
    project_name: str,
    resource_group_id: str,
    resource_group_name: str,
    job_type: str,
    image: str,
    image_type: str,
    image_flag: int,
    command: str,
    start_script: str,
    exec_dir: str,
    mount_dir: str,
    script_dir: str,
    log_out: str,
    log_persistence: str,
    config: str,
    gpu_info: str,
    pod_info: str,
    switch_type: str,
    dist_flag: bool,
    mpi_flag: bool,
    is_elastic: bool,
    shm_size: int,
    ports: str,
    emergency_flag: bool,
    task_type: int,
    task_type_name: str,
    create_time_ms: int,
    start_time_ms: int | None,
    end_time_ms: int | None,
    run_time_s: int,
    node_name: str,
    job_volume: list[JobVolume],
    status_reason: str,
    raw: dict[str, Any] = {},
)
```

`Task` is the parsed model for training or batch workloads.

### Identity and ownership fields

| Field | Meaning |
| --- | --- |
| `id` | Task identifier. |
| `name` | Task name. |
| `status` | Backend task status string. See `TaskStatus` for common values. |
| `user_id` | Owner user identifier. |
| `user_name` | Owner user name. |
| `project_id` | Project/group identifier associated with the task. |
| `project_name` | Project/group display name. |
| `resource_group_id` | Training resource-group identifier. |
| `resource_group_name` | Training resource-group name. |
| `job_type` | Backend job-type string. |

### Image and execution fields

| Field | Meaning |
| --- | --- |
| `image` | Full image reference string. |
| `image_type` | Framework/category string. |
| `image_flag` | Backend image-flag integer. |
| `command` | Container command string. |
| `start_script` | Start-script string. |
| `exec_dir` | Execution directory string. |
| `mount_dir` | Working mount directory. |
| `script_dir` | Script directory metadata. |
| `log_out` | Log output path. |
| `log_persistence` | Log persistence configuration string. |

### Raw payload and topology fields

| Field | Meaning |
| --- | --- |
| `config` | JSON-serialized backend `config` field. |
| `gpu_info` | JSON-serialized backend GPU information. |
| `pod_info` | JSON-serialized backend pod information. |
| `switch_type` | Interconnect string. |
| `dist_flag` | Distributed-training flag. |
| `mpi_flag` | MPI flag. |
| `is_elastic` | Elastic-training flag. |
| `shm_size` | Shared-memory size. |
| `ports` | Comma-separated port string. |
| `emergency_flag` | Emergency scheduling flag. |
| `task_type` | Backend task-type integer. |
| `task_type_name` | Human-readable task-type name. |
| `node_name` | Node name string when available. |
| `job_volume` | Parsed list of attached `JobVolume` objects. |
| `status_reason` | Backend status-reason string. |

### Timing fields

| Field | Meaning |
| --- | --- |
| `create_time_ms` | Creation timestamp. |
| `start_time_ms` | Start timestamp or `None`. |
| `end_time_ms` | End timestamp or `None`. |
| `run_time_s` | Runtime duration in seconds-like backend units. |
| `raw` | Original server dictionary. |

### Classmethod

```python
Task.from_api(d: dict[str, Any]) -> Task
```

## `TaskType`

```python
TaskType(
    type_code: str,
    type_name: str,
    platform: str,
    raw: dict[str, Any] = {},
)
```

`TaskType` represents one entry from the backend task-type metadata list returned by form-context helpers.

### Fields

| Field | Meaning |
| --- | --- |
| `type_code` | Backend task-type code. |
| `type_name` | Human-readable task-type name. |
| `platform` | Platform label. |
| `raw` | Original server dictionary. |

### Classmethod

```python
TaskType.from_api(d: dict[str, Any]) -> TaskType
```

## `WorkPlatform`

```python
WorkPlatform(
    wp_id: str,
    wp_name: str,
    wp_status: str,
    group_id: str,
    group_name: str,
    image: str,
    image_type: str,
    frame_work: str,
    cpu: int,
    memory_gb: int,
    cards: int,
    card_kind: str,
    card_type: str,
    card_memory_gb: int,
    shm_size: int,
    command: str,
    pod_num: int,
    user_id: str,
    create_time: str,
    env: list[dict[str, Any]] | None = None,
    models: list[dict[str, Any]] = [],
    volumes: list[dict[str, Any]] = [],
    mig_num: int | None = None,
    mig_type: int | None = None,
    raw: dict[str, Any] = {},
)
```

`WorkPlatform` is the parsed model for development environments.

### Identity and status fields

| Field | Meaning |
| --- | --- |
| `wp_id` | Workplatform identifier. |
| `wp_name` | Workplatform name. |
| `wp_status` | Workplatform status string. |
| `group_id` | Resource-group identifier. |
| `group_name` | Resource-group name. |
| `user_id` | Owner identifier. |
| `create_time` | Creation-time string. |

### Runtime and resource fields

| Field | Meaning |
| --- | --- |
| `image` | Workplatform image reference. |
| `image_type` | Backend image-type label. |
| `frame_work` | Backend framework label. |
| `cpu` | Requested CPU cores. |
| `memory_gb` | Requested memory. |
| `cards` | Requested accelerator-card count. |
| `card_kind` | Accelerator kind string. |
| `card_type` | Accelerator model string. |
| `card_memory_gb` | Per-card memory. |
| `shm_size` | Shared-memory size. |
| `command` | Startup command. |
| `pod_num` | Number of pods in the workplatform. |

### Extra metadata fields

| Field | Meaning |
| --- | --- |
| `env` | Raw environment-variable entry list or `None`. |
| `models` | Raw model metadata list. |
| `volumes` | Raw volume list. |
| `mig_num` | Optional MIG count. |
| `mig_type` | Optional MIG type. |
| `raw` | Original server dictionary. |

### Classmethod

```python
WorkPlatform.from_api(d: dict[str, Any]) -> WorkPlatform
```

## `FormContext`

```python
FormContext(
    user: User,
    resource_groups: list[ResourceGroup],
    images: list[Image],
    image_types: list[ImageType_],
    task_types: list[TaskType],
    start_scripts: list[dict[str, Any]],
    shm_editable: bool,
    missing: list[str] = [],
)
```

`FormContext` is the aggregate object returned by `enumerate_form_context()`.

### Fields

| Field | Meaning |
| --- | --- |
| `user` | Current authenticated user. |
| `resource_groups` | Visible training resource groups. |
| `images` | Visible image list. |
| `image_types` | Image-type metadata list. |
| `task_types` | Task-type metadata list. |
| `start_scripts` | Raw start-script metadata list from the backend. |
| `shm_editable` | Whether the shared-memory setting is currently editable. |
| `missing` | Human-readable descriptions of sub-requests that failed or were denied. |

## Discovery Models

These objects live in `aistation.discovery` and are also re-exported from the package root.

## `DiscoveryStep`

```python
DiscoveryStep(
    iteration: int,
    err_code: str | None,
    err_message: str | None,
    action: str,
    field: str | None = None,
    applied_value: Any = None,
)
```

Represents one probe/fix iteration inside `discover_payload_requirements()`.

### Fields

| Field | Meaning |
| --- | --- |
| `iteration` | 1-based iteration number. |
| `err_code` | Backend error code for the failed probe, or `None` for an accepted iteration. |
| `err_message` | Backend error message for the failed probe, or `None` for an accepted iteration. |
| `action` | Action the helper chose for this step, such as `fix_missing` or `accepted`. |
| `field` | Parsed field name when the helper could infer one from the backend message. |
| `applied_value` | Value written back into the payload for this step, when any. |

## `DiscoveryReport`

```python
DiscoveryReport(
    success: bool,
    iterations: int,
    steps: list[DiscoveryStep],
    final_payload: dict[str, Any],
    final_response: dict[str, Any] | None,
    created_task_id: str | None,
    constraints: dict[str, str] = {},
    missing_fields: list[str] = [],
)
```

Represents the full result of one discovery session.

### Fields

| Field | Meaning |
| --- | --- |
| `success` | Whether the final probe was accepted. |
| `iterations` | Number of recorded steps. |
| `steps` | Full iteration history. |
| `final_payload` | The last payload state after all applied fixes. |
| `final_response` | The final raw server response, if any request completed. |
| `created_task_id` | Task identifier extracted from the final successful response, if available. |
| `constraints` | Learned field constraints, usually regex or numeric-range strings. |
| `missing_fields` | Field names that the backend reported as missing required inputs. |

## Enums

The SDK exports a small set of `StrEnum` and `IntEnum` types for common literals.

## `AuthMode`

Type: `StrEnum`

| Member | Value | Meaning |
| --- | --- | --- |
| `AuthMode.AUTO` | `"auto"` | Default ergonomic behavior. Restore cached auth and re-login when appropriate. |
| `AuthMode.TOKEN_ONLY` | `"token_only"` | Restore token state only. |
| `AuthMode.LOGIN_IF_POSSIBLE` | `"login_if_possible"` | Eagerly log in when credentials exist. |
| `AuthMode.MANUAL` | `"manual"` | Disable automatic restore/login preparation. |

## `ReauthPolicy`

Type: `StrEnum`

| Member | Value | Meaning |
| --- | --- | --- |
| `ReauthPolicy.AUTO` | `"auto"` | Let the client derive reauth behavior from `auth_mode`. |
| `ReauthPolicy.NEVER` | `"never"` | Never auto-login during request execution. |
| `ReauthPolicy.IF_POSSIBLE` | `"if_possible"` | Auto-login when credentials are available. |

## `SwitchType`

Type: `StrEnum`

| Member | Value | Meaning |
| --- | --- | --- |
| `SwitchType.IB` | `"ib"` | Infiniband-style interconnect label. |
| `SwitchType.ETH` | `"eth"` | Ethernet-style interconnect label. |

## `CardKind`

Type: `StrEnum`

| Member | Value | Meaning |
| --- | --- | --- |
| `CardKind.GPU` | `"GPU"` | GPU resource kind. |
| `CardKind.CPU` | `"CPU"` | CPU-only resource kind. |
| `CardKind.NONE` | `"-"` | Placeholder/empty card-kind marker seen in some payloads. |

## `PodStatus`

Type: `StrEnum`

| Member | Value |
| --- | --- |
| `PodStatus.RUNNING` | `"Running"` |
| `PodStatus.PENDING` | `"Pending"` |
| `PodStatus.QUEUING` | `"Queuing"` |
| `PodStatus.SUCCEEDED` | `"Succeeded"` |
| `PodStatus.FAILED` | `"Failed"` |
| `PodStatus.OOM_KILLED` | `"OOMKilled"` |
| `PodStatus.STOPPED` | `"Stopped"` |

## `TaskStatus`

Type: `StrEnum`

| Member | Value |
| --- | --- |
| `TaskStatus.RUNNING` | `"Running"` |
| `TaskStatus.PENDING` | `"Pending"` |
| `TaskStatus.SUCCEEDED` | `"Succeeded"` |
| `TaskStatus.FAILED` | `"Failed"` |
| `TaskStatus.TERMINATING` | `"Terminating"` |

## `ImageType`

Type: `StrEnum`

| Member | Value |
| --- | --- |
| `ImageType.PYTORCH` | `"pytorch"` |
| `ImageType.TENSORFLOW` | `"tensorflow"` |
| `ImageType.CAFFE` | `"caffe"` |
| `ImageType.MXNET` | `"mxnet"` |
| `ImageType.PADDLEPADDLE` | `"paddlepaddle"` |
| `ImageType.OTHER` | `"other"` |

## `ShareType`

Type: `IntEnum`

| Member | Value | Meaning |
| --- | --- | --- |
| `ShareType.PRIVATE` | `1` | Private image visibility. |
| `ShareType.PUBLIC` | `2` | Public image visibility. |

## `FunctionModel`

Type: `IntEnum`

| Member | Value | Meaning |
| --- | --- | --- |
| `FunctionModel.DATASET` | `1` | Dataset-style volume attachment. |
| `FunctionModel.MOUNT_DIR` | `2` | General mount-directory attachment. |
| `FunctionModel.LOG_DIR` | `3` | Log-directory attachment. |

## `MakeType`

Type: `IntEnum`

| Member | Value | Meaning |
| --- | --- | --- |
| `MakeType.NATIVE` | `0` | Native/internal image source. |
| `MakeType.DOCKERFILE` | `1` | Dockerfile build. |
| `MakeType.COMMIT` | `4` | Commit/export style image generation. |

## `RoleType`

Type: `IntEnum`

| Member | Value | Meaning |
| --- | --- | --- |
| `RoleType.ADMIN` | `0` | Administrative role. |
| `RoleType.USER` | `2` | Normal user role. |

## Errors

All SDK-specific exceptions inherit from `AiStationError`, which itself inherits from `RuntimeError`.

### Hierarchy

- `AiStationError`
- `TransportError`
- `AuthError`
- `InvalidCredentials`
- `TokenExpired`
- `NotFoundError`
- `AmbiguousMatchError`
- `PermissionDenied`
- `ValidationError`
- `SpecValidationError`
- `ResourceError`

## `AiStationError`

```python
AiStationError(
    message: str,
    *,
    err_code: str | None = None,
    err_message: str | None = None,
    path: str | None = None,
)
```

Base class for SDK-originated failures.

### Attributes

| Attribute | Meaning |
| --- | --- |
| `err_code` | Backend or SDK-specific error code. |
| `err_message` | Human-facing error message from the backend or SDK. |
| `path` | API path associated with the error, when known. |

### Methods

#### `hint()`

```python
hint() -> tuple[str, str] | None
```

Looks up `err_code` in the SDK's error guide and returns:

- short description
- suggested action

or `None` if the code is unknown.

#### `describe()`

```python
describe() -> str
```

Returns a multi-line human-readable string containing:

- the error code and message
- the API path when available
- the mapped hint text when the error code is known

The current hint strings are written in Chinese because they are tailored to the server's native error ecosystem.

## `TransportError`

```python
TransportError(message: str, *, err_code=None, err_message=None, path=None)
```

Raised for network, timeout, TLS, DNS, or other request-transport failures.

## `AuthError`

```python
AuthError(message: str, *, err_code=None, err_message=None, path=None)
```

Base class for login and token-related failures.

## `InvalidCredentials`

```python
InvalidCredentials(message: str, *, err_code=None, err_message=None, path=None)
```

Specialized auth error for bad account/password combinations.

## `TokenExpired`

```python
TokenExpired(message: str, *, err_code=None, err_message=None, path=None)
```

Specialized auth error for missing or expired tokens.

## `NotFoundError`

```python
NotFoundError(resource_type: str, query: str)
```

Raised when a lookup did not match any resource.

### Extra attributes

| Attribute | Meaning |
| --- | --- |
| `resource_type` | Logical resource label such as `"task"` or `"image"`. |
| `query` | Original lookup query. |

This class always sets:

- `err_code="SDK_NOT_FOUND"`
- `err_message` to a synthesized not-found message

## `AmbiguousMatchError`

```python
AmbiguousMatchError(
    resource_type: str,
    query: str,
    *,
    matches: list[str],
)
```

Raised when a lookup matched multiple candidate resources.

### Extra attributes

| Attribute | Meaning |
| --- | --- |
| `resource_type` | Logical resource label. |
| `query` | Original lookup query. |
| `matches` | Matching candidate summaries. |

This class always sets:

- `err_code="SDK_AMBIGUOUS_MATCH"`
- `err_message` to a synthesized ambiguity message

## `PermissionDenied`

```python
PermissionDenied(message: str, *, err_code=None, err_message=None, path=None)
```

Raised when the current account or role cannot access an endpoint or resource.

## `ValidationError`

```python
ValidationError(
    message: str,
    *,
    field_name: str | None = None,
    err_code: str | None = None,
    err_message: str | None = None,
    path: str | None = None,
)
```

Raised when input validation fails, either client-side or server-side.

### Extra attribute

| Attribute | Meaning |
| --- | --- |
| `field_name` | Name of the offending field when known. |

## `ResourceError`

```python
ResourceError(message: str, *, err_code=None, err_message=None, path=None)
```

Raised for quota, scheduling, or resource business-logic failures.

## `SpecValidationError`

```python
SpecValidationError(message: str, *, field_name: str | None = None)
```

Specialized `ValidationError` raised by `validation.validate_spec()` and related local checks.

This class always sets:

- `err_code="SDK_SPEC_VALIDATION"`
- `err_message=message`

## `lookup_error_guide(err_code)`

```python
lookup_error_guide(err_code: str) -> tuple[str, str] | None
```

Looks up a known error-code hint without needing an exception instance.

### Return value

- Returns `(short_description, suggested_action)` when the code is known.
- Returns `None` otherwise.

### Typical usage

```python
from aistation import lookup_error_guide

guide = lookup_error_guide("IBASE_IAUTH_TOKEN_NOT_FOUND")
if guide is not None:
    short_desc, next_step = guide
```
