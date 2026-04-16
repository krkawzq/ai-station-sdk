# WorkPlatforms

This document covers:

- `WorkPlatformSpec`
- `client.workplatforms` / `async_client.workplatforms`
- workplatform wait and watch helpers

In the SDK, “workplatform” refers to the AI Station development-environment product: notebook-like or shell-like interactive environments created by the `/work-platform` backend.

## `WorkPlatformSpec`

`WorkPlatformSpec` is the user-facing spec object for development environments.

### Constructor

```python
WorkPlatformSpec(
    name: str,
    resource_group: str | ResourceGroup,
    image: str | Image,
    command: str = "sleep 3600",
    cards: int = 0,
    cpu: int = 1,
    memory_gb: int = 0,
    card_kind: str = "CPU",
    pod_num: int = 1,
    shm_size: int = 1,
    frame_work: str = "other",
    image_type: str = "INNER_IMAGE",
    ports: list[int] = [],
    env: dict[str, str] | None = None,
    volumes: list[dict[str, Any]] = [],
    models: list[dict[str, Any]] = [],
    switch_type: str = "ib",
    wp_type: str = "COMMON_WP",
    node_list: list[str] = [],
    raw_overrides: dict[str, Any] = {},
)
```

### Required fields

| Field | Meaning |
| --- | --- |
| `name` | Environment name |
| `resource_group` | Group name, group ID, or `ResourceGroup` object |
| `image` | Image reference or `Image` object |

### Scheduling fields

| Field | Meaning |
| --- | --- |
| `cards` | Number of accelerator cards |
| `cpu` | CPU cores |
| `memory_gb` | Memory in GB |
| `card_kind` | `"CPU"` or `"GPU"` in normal usage |
| `pod_num` | Number of pods for the environment |
| `shm_size` | Shared memory size |
| `switch_type` | Interconnect hint |
| `node_list` | Explicit node placement list |

### Runtime fields

| Field | Meaning |
| --- | --- |
| `command` | Container startup command |
| `frame_work` | Backend framework label |
| `image_type` | Backend image type label |
| `wp_type` | Workplatform type, normally `COMMON_WP` |
| `ports` | Exposed ports |
| `env` | Environment variables |

### Storage and model fields

| Field | Meaning |
| --- | --- |
| `volumes` | Explicit volume declarations |
| `models` | Model metadata |

### Escape hatch

| Field | Meaning |
| --- | --- |
| `raw_overrides` | Raw payload overrides merged after the SDK builds the payload |

## `WorkPlatformSpec` convenience constructors

### `WorkPlatformSpec.notebook(...)`

```python
WorkPlatformSpec.notebook(
    *,
    resource_group: str | ResourceGroup,
    image: str | Image,
    name: str | None = None,
    name_prefix: str = "notebook",
    cards: int = 0,
    cpu: int = 2,
    memory_gb: int = 8,
    command: str = "sleep infinity",
    ports: list[int] | None = None,
    env: dict[str, str] | None = None,
    card_kind: str | None = None,
    frame_work: str = "other",
    image_type: str = "INNER_IMAGE",
    shm_size: int = 1,
    pod_num: int = 1,
    switch_type: str = "ib",
) -> WorkPlatformSpec
```

This is the preferred entry point for most development environments.

Behavior:

- generates a name automatically if `name` is omitted
- defaults to CPU-only notebook-like settings
- infers `card_kind="GPU"` when `cards > 0`
- fills `ports` and `env` with empty containers when omitted

### `WorkPlatformSpec.from_existing(workplatform, ...)`

```python
WorkPlatformSpec.from_existing(
    workplatform: WorkPlatform,
    *,
    name: str | None = None,
    name_prefix: str = "clone",
) -> WorkPlatformSpec
```

Reverse-engineers a new spec from an existing workplatform.

This is the easiest way to clone a working environment and change only a small number of fields.

## WorkPlatforms API

Access:

```python
api = client.workplatforms
```

or:

```python
api = async_client.workplatforms
```

## Listing and lookup

### `workplatforms.list(...)`

Sync:

```python
list(
    *,
    include_halted: bool = False,
    refresh: bool = False,
    max_history_pages: int = 10,
    history_page_size: int = 50,
) -> list[WorkPlatform]
```

Async:

```python
await list(
    *,
    include_halted: bool = False,
    refresh: bool = False,
    max_history_pages: int = 10,
    history_page_size: int = 50,
) -> list[WorkPlatform]
```

Behavior:

- prefers the workplatform history endpoint because it gives a more reliable environment view
- filters terminal statuses by default
- falls back to the active endpoint when history is empty

### Parameters

| Parameter | Meaning |
| --- | --- |
| `include_halted` | Include stopped or halted environments |
| `refresh` | Bypass caches |
| `max_history_pages` | Maximum history pages to fetch in all-pages mode |
| `history_page_size` | Page size used for history scanning |

### Caching

The SDK uses separate TTL caches for:

- active list view
- active fallback view
- history pages

## `workplatforms.list_history(...)`

Sync:

```python
list_history(
    *,
    page: int = 1,
    page_size: int = 50,
    all_pages: bool = False,
    max_pages: int | None = None,
    refresh: bool = False,
) -> list[WorkPlatform]
```

Async:

```python
await list_history(
    *,
    page: int = 1,
    page_size: int = 50,
    all_pages: bool = False,
    max_pages: int | None = None,
    refresh: bool = False,
) -> list[WorkPlatform]
```

Use this when you explicitly need historical development environments.

## `workplatforms.get(wp_id)`

Sync:

```python
get(wp_id: str | WorkPlatform) -> WorkPlatform
```

Async:

```python
await get(wp_id: str | WorkPlatform) -> WorkPlatform
```

Accepts either a workplatform ID or a `WorkPlatform` object.

This always fetches the detail endpoint.

## `workplatforms.exists(name, *, refresh=False)`

Sync:

```python
exists(name: str, *, refresh: bool = False) -> WorkPlatform | None
```

Async:

```python
await exists(name: str, *, refresh: bool = False) -> WorkPlatform | None
```

Returns an active workplatform with the exact name, or `None`.

## `workplatforms.resolve_many(...)`

Sync:

```python
resolve_many(
    query: str,
    *,
    include_halted: bool = True,
    search_history: bool = True,
    refresh: bool = False,
    max_history_pages: int = 10,
) -> list[WorkPlatform]
```

Async:

```python
await resolve_many(
    query: str,
    *,
    include_halted: bool = True,
    search_history: bool = True,
    refresh: bool = False,
    max_history_pages: int = 10,
) -> list[WorkPlatform]
```

Matches against:

- `wp_id`
- `wp_name`

## `workplatforms.resolve(...)`

Sync:

```python
resolve(
    query: str | WorkPlatform,
    *,
    include_halted: bool = True,
    search_history: bool = True,
    refresh: bool = False,
    max_history_pages: int = 10,
) -> WorkPlatform
```

Async:

```python
await resolve(
    query: str | WorkPlatform,
    *,
    include_halted: bool = True,
    search_history: bool = True,
    refresh: bool = False,
    max_history_pages: int = 10,
) -> WorkPlatform
```

Important behavior:

- the SDK now tries local candidate resolution first
- it only falls back to a direct detail fetch if local lookup does not find a match

This avoids an unnecessary detail request when the caller is resolving by name.

## Group discovery for dev environments

Training groups and workplatform groups are not the same thing.

Use the workplatform group helpers for development environments.

### `workplatforms.list_groups(*, refresh=False)`

Sync:

```python
list_groups(*, refresh: bool = False) -> list[ResourceGroup]
```

Async:

```python
await list_groups(*, refresh: bool = False) -> list[ResourceGroup]
```

Queries the dedicated `groupLabel=develop` endpoint and returns dev-eligible groups.

### `workplatforms.resolve_group(name_or_id)`

Sync:

```python
resolve_group(name_or_id: str) -> ResourceGroup
```

Async:

```python
await resolve_group(name_or_id: str) -> ResourceGroup
```

### `workplatforms.resolve_group_id(name_or_id)`

Sync:

```python
resolve_group_id(name_or_id: str) -> str
```

Async:

```python
await resolve_group_id(name_or_id: str) -> str
```

## Templates and raw payloads

### `workplatforms.rebuild_template(wp_id)`

Sync:

```python
rebuild_template(wp_id: str | WorkPlatform) -> dict[str, Any]
```

Async:

```python
await rebuild_template(wp_id: str | WorkPlatform) -> dict[str, Any]
```

Fetches the backend “rebuild” template for an existing environment.

This is one of the easiest ways to discover a backend-acceptable payload for a complex environment.

### `workplatforms.create_raw(payload)`

Sync:

```python
create_raw(payload: dict[str, Any]) -> OperationResult[WorkPlatform]
```

Async:

```python
await create_raw(payload: dict[str, Any]) -> OperationResult[WorkPlatform]
```

Submits an already assembled backend payload verbatim.

Use this only when:

- you already know the exact backend schema
- you are working from a rebuild template
- the high-level spec does not yet cover a required field combination

## Create flow

### `workplatforms.create(...)`

Sync:

```python
create(
    spec: WorkPlatformSpec,
    *,
    dry_run: bool = False,
    idempotent: bool = True,
) -> OperationResult[WorkPlatform]
```

Async:

```python
await create(
    spec: WorkPlatformSpec,
    *,
    dry_run: bool = False,
    idempotent: bool = True,
) -> OperationResult[WorkPlatform]
```

### Parameters

| Parameter | Meaning |
| --- | --- |
| `dry_run` | Return the generated payload without contacting the server |
| `idempotent` | Reuse an existing active environment with the same name instead of creating a duplicate |

### Behavior

The create path:

1. Optionally checks for an existing environment by name.
2. Builds the backend payload.
3. Optionally returns early for `dry_run=True`.
4. Submits the create request.
5. Invalidates caches.
6. Resolves the created workplatform, with a short eventual-consistency retry.

### `OperationResult` states

You should expect the same semantics as task creation:

- `created=True` when the SDK actually submitted a create request
- `reused=True` when an existing environment was returned
- `entity` may or may not be resolved depending on server behavior

## `workplatforms.create_and_wait_ready(...)`

Sync:

```python
create_and_wait_ready(
    spec: WorkPlatformSpec,
    *,
    idempotent: bool = True,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> OperationResult[WorkPlatform]
```

Async:

```python
await create_and_wait_ready(
    spec: WorkPlatformSpec,
    *,
    idempotent: bool = True,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> OperationResult[WorkPlatform]
```

Creates the environment and waits until it is ready or terminal.

The returned `OperationResult` has:

- `waited=True`
- `entity` replaced by the waited final state

## Delete and access URLs

### `workplatforms.delete(wp_id)`

Sync:

```python
delete(wp_id: str | WorkPlatform) -> OperationResult[WorkPlatform]
```

Async:

```python
await delete(wp_id: str | WorkPlatform) -> OperationResult[WorkPlatform]
```

Deletes the environment and invalidates caches.

### `workplatforms.jupyter_url(wp_id)`

Sync:

```python
jupyter_url(wp_id: str | WorkPlatform) -> dict[str, Any]
```

Async:

```python
await jupyter_url(wp_id: str | WorkPlatform) -> dict[str, Any]
```

Returns the raw Jupyter access payload for the environment.

### `workplatforms.shell_url(wp_id, *, pod_id=None)`

Sync:

```python
shell_url(wp_id: str | WorkPlatform, *, pod_id: str | None = None) -> dict[str, Any]
```

Async:

```python
await shell_url(wp_id: str | WorkPlatform, *, pod_id: str | None = None) -> dict[str, Any]
```

Returns the raw shell access payload.

If `pod_id` is provided, the SDK asks for the shell URL of a specific pod.

## Image and history actions

### `workplatforms.commit_image(...)`

Sync:

```python
commit_image(
    wp_id: str | WorkPlatform,
    *,
    image_name: str,
    image_tag: str,
    pod_id: str,
    comment: str = "",
    image_type: str = "other",
) -> OperationResult[WorkPlatform]
```

Async:

```python
await commit_image(
    wp_id: str | WorkPlatform,
    *,
    image_name: str,
    image_tag: str,
    pod_id: str,
    comment: str = "",
    image_type: str = "other",
) -> OperationResult[WorkPlatform]
```

Commits the filesystem of a running workplatform pod into a new internal image.

The returned `OperationResult` stores the originating workplatform ID in:

```python
result.extras["workplatform_id"]
```

### `workplatforms.toggle_history_collect(wp_id, collected)`

Sync:

```python
toggle_history_collect(
    wp_id: str | WorkPlatform,
    collected: bool,
) -> OperationResult[WorkPlatform]
```

Async:

```python
await toggle_history_collect(
    wp_id: str | WorkPlatform,
    collected: bool,
) -> OperationResult[WorkPlatform]
```

Marks or unmarks a history entry as collected/starred.

## Waiting helpers

### `workplatforms.wait_ready(wp_id, *, timeout=600.0, interval=5.0)`

Sync:

```python
wait_ready(
    wp_id: str | WorkPlatform,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> WorkPlatform
```

Async:

```python
await wait_ready(
    wp_id: str | WorkPlatform,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> WorkPlatform
```

Waits until the environment reaches one of the ready or terminal states recognized by the SDK.

## Watch helpers

These helpers live in `aistation.watch` and `aistation.aio.watch`.

### `watch.watch_workplatform(...)`

Sync:

```python
watch_workplatform(
    client: AiStationClient,
    wp_id: str,
    *,
    interval: float = 5.0,
    timeout: float = 600.0,
    until: set[str] | None = None,
) -> Iterator[WorkPlatform]
```

Async:

```python
watch_workplatform(
    client: AsyncAiStationClient,
    wp_id: str,
    *,
    interval: float = 5.0,
    timeout: float = 600.0,
    until: set[str] | None = None,
) -> AsyncIterator[WorkPlatform]
```

Yields a new `WorkPlatform` each time the status changes.

### `watch.wait_workplatform_ready(...)`

Sync:

```python
wait_workplatform_ready(
    client: AiStationClient,
    wp_id: str,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> WorkPlatform
```

Async:

```python
await wait_workplatform_ready(
    client: AsyncAiStationClient,
    wp_id: str,
    *,
    timeout: float = 600.0,
    interval: float = 5.0,
) -> WorkPlatform
```

This is the lower-level helper underlying `workplatforms.wait_ready()` and `create_and_wait_ready()`.

## Typical patterns

### Create a CPU notebook environment

```python
spec = A.WorkPlatformSpec.notebook(
    resource_group="DEV-POOL",
    image="registry.example.invalid/ml/dev:latest",
    cpu=2,
    memory_gb=8,
)
wp = client.workplatforms.create_and_wait_ready(spec).unwrap()
```

### Clone an existing environment

```python
existing = client.workplatforms.resolve("team-notebook")
spec = A.WorkPlatformSpec.from_existing(existing)
spec.name = "team-notebook-clone"
clone = client.workplatforms.create(spec)
```

### Use a rebuild template

```python
template = client.workplatforms.rebuild_template(existing)
template["wpName"] = "template-clone"
result = client.workplatforms.create_raw(template)
```

### Open Jupyter or shell URLs

```python
wp = client.workplatforms.resolve("team-notebook")
jupyter = client.workplatforms.jupyter_url(wp)
shell = client.workplatforms.shell_url(wp)
```

## Related modules

- Shared result semantics are documented in [reference.md](./reference.md)
- Group discovery and image lookup are documented in [resources-and-images.md](./resources-and-images.md)
