# Tasks

This document covers:

- `TaskSpec`
- `aistation.presets`
- `client.tasks` / `async_client.tasks`
- task wait and watch helpers in `aistation.watch` and `aistation.aio.watch`

In AI Station terminology, a “task” is a training or batch workload submitted to the `/train` backend.

## `TaskSpec`

`TaskSpec` is the user-facing input object used to create tasks.

### Constructor

```python
TaskSpec(
    name: str,
    resource_group: str | ResourceGroup,
    image: str | Image,
    command: str,
    cards: int = 1,
    cpu: int = 4,
    memory_gb: int = 0,
    nodes: int = 1,
    card_kind: str = "GPU",
    mount_path: str = "",
    script_dir: str = "",
    log_path: str = "",
    datasets: list[dict[str, Any]] = [],
    models: list[dict[str, Any]] = [],
    ports: list[int] = [],
    env: dict[str, str] = {},
    shm_size: int = 4,
    switch_type: str = "ib",
    image_type: str = "",
    image_flag: int = 0,
    is_elastic: bool = False,
    distributed: str = "node",
    emergency: bool = False,
    description: str = "",
    start_script: str = "",
    exec_dir: str = "",
    parameters: str = "",
    node_names: list[str] = [],
    mount_path_model: int = 2,
    log_storage_name: str = "master",
    task_type: int = 1,
    min_nodes: int = -1,
    raw_overrides: dict[str, Any] = {},
)
```

### Required fields

| Field | Meaning |
| --- | --- |
| `name` | Task name. The backend expects an alphanumeric-only string. |
| `resource_group` | Group name, group ID, or a `ResourceGroup` object. |
| `image` | Full image reference, short image reference, or an `Image` object. |
| `command` | Command string executed inside the task container. |

### Core scheduling fields

| Field | Meaning |
| --- | --- |
| `cards` | Number of accelerator cards requested per worker. |
| `cpu` | CPU cores requested per worker. |
| `memory_gb` | Memory in GB requested per worker. |
| `nodes` | Number of worker nodes. |
| `card_kind` | Usually `"GPU"` or `"CPU"`. |
| `switch_type` | Interconnect preference such as `"ib"` or `"roce"` depending on backend support. |

### Filesystem and execution fields

| Field | Meaning |
| --- | --- |
| `mount_path` | Working mount path. If empty, the SDK typically falls back to `/{account}`. |
| `script_dir` | Optional script directory metadata. |
| `log_path` | Optional persistent log directory. |
| `start_script` | Optional start script hint for the backend. |
| `exec_dir` | Optional execution directory. Empty string is often the safest value. |

### Networking and environment fields

| Field | Meaning |
| --- | --- |
| `ports` | List of container ports to expose. |
| `env` | Environment variables as a mapping. |
| `shm_size` | Shared memory size in GB-equivalent backend units. The server expects memory to be large enough relative to this value. |

### Data and model attachment fields

| Field | Meaning |
| --- | --- |
| `datasets` | Dataset mount declarations. These are translated into `jobVolume` entries. |
| `models` | Model mount metadata. |
| `mount_path_model` | Backend volume mode for the default working mount. |
| `log_storage_name` | Storage name used when `log_path` is set. |

### Distributed and advanced fields

| Field | Meaning |
| --- | --- |
| `distributed` | Distribution mode. Common values are `node`, `mpi`, `ps_worker`, `master_worker`, `server_worker`. |
| `is_elastic` | Enables elastic training metadata. |
| `min_nodes` | Minimum nodes for elastic execution. |
| `image_type` | Explicit image framework type. If empty, the SDK infers it from the image reference. |
| `image_flag` | Backend image flag. |
| `emergency` | Emergency scheduling flag. |
| `description` | Optional description. |
| `parameters` | Additional parameter string mapped to backend `param`. |
| `node_names` | Explicit node placement hints. |
| `task_type` | Backend task type integer. |
| `raw_overrides` | Raw backend payload overrides. Use only when you know the server contract exactly. |

## `TaskSpec` convenience constructors

### `TaskSpec.gpu_hold(...)`

```python
TaskSpec.gpu_hold(...)
```

Delegates to `aistation.presets.gpu_hold()` and returns a ready-to-submit single-node hold task.

Typical use:

```python
spec = A.TaskSpec.gpu_hold(
    resource_group="8A100_80",
    image="pytorch/pytorch:21.10-py3",
    cards=1,
    hours=2,
)
```

### `TaskSpec.cpu_debug(...)`

Delegates to `aistation.presets.cpu_debug()`.

Use this for small CPU-only smoke tests.

### `TaskSpec.pytorch_train(...)`

Delegates to `aistation.presets.pytorch_train()`.

Use this when you want a normal training task shape with sensible defaults.

### `TaskSpec.from_existing(task, **kwargs)`

Creates a new `TaskSpec` by reverse-engineering an existing `Task`.

This is useful for cloning a known-good task and modifying only a few fields.

## `aistation.presets`

The `presets` module provides the same factory functions directly:

- `presets.gpu_hold(...)`
- `presets.cpu_debug(...)`
- `presets.pytorch_train(...)`
- `presets.from_existing(task, *, name_prefix="clone")`

Use either style:

- `TaskSpec.gpu_hold(...)`
- `presets.gpu_hold(...)`

The returned object is always a plain mutable `TaskSpec`.

## Tasks API

Access the tasks API from the client:

```python
tasks_api = client.tasks
```

or:

```python
tasks_api = async_client.tasks
```

## `tasks.list(...)`

Sync:

```python
list(*, status_flag: int = 0, refresh: bool = False) -> list[Task]
```

Async:

```python
await list(*, status_flag: int = 0, refresh: bool = False) -> list[Task]
```

### Parameters

| Parameter | Meaning |
| --- | --- |
| `status_flag` | Backend status bucket. `0` means unfinished tasks. `3` means finished tasks. |
| `refresh` | Bypass the SDK task-list cache. |

### Cache behavior

- The SDK caches task lists for a short period.
- The cache is keyed by `status_flag`.
- `create()`, `delete()`, and `stop()` invalidate the task-list cache.

### Recommendation

Use `status_flag=0` for active workloads and `status_flag=3` only when you explicitly need history.

## `tasks.get(task_id, *, status_flag=0)`

Sync:

```python
get(task_id: str | Task, *, status_flag: int = 0) -> Task
```

Async:

```python
await get(task_id: str | Task, *, status_flag: int = 0) -> Task
```

Accepts either:

- a task ID string
- a `Task` object

Behavior:

- tries the requested `status_flag`
- then falls back across finished and unfinished buckets

Raises `NotFoundError` if the task cannot be found.

## `tasks.resolve_many(query, *, include_finished=True, refresh=False)`

Returns all task matches by:

- `id`
- `name`

If `include_finished=True`, both active and finished buckets are searched.

## `tasks.resolve(query, *, include_finished=True, refresh=False)`

Returns a single resolved `Task` or raises:

- `NotFoundError`
- `AmbiguousMatchError`

Use this when a task name is expected to be unique enough for automation.

## `tasks.pods(task_id)`

Sync:

```python
pods(task_id: str | Task) -> list[Pod]
```

Async:

```python
await pods(task_id: str | Task) -> list[Pod]
```

Returns the pod instances for a task.

This is the main way to discover:

- node placement
- node IPs
- exposed node ports

## `tasks.read_log(task_id, *, pod_name=None)`

Sync:

```python
read_log(task_id: str | Task, *, pod_name: str | None = None) -> str
```

Async:

```python
await read_log(task_id: str | Task, *, pod_name: str | None = None) -> str
```

Behavior:

- If the server returns a string, the SDK returns it directly.
- If the server returns a dictionary with `content`, `log`, or `data`, that string is returned.
- Otherwise the SDK JSON-serializes the dictionary to a string.

## `tasks.check_resources(spec, *, validate=True)`

Sync:

```python
check_resources(spec: TaskSpec, *, validate: bool = True) -> OperationResult[Task]
```

Async:

```python
await check_resources(spec: TaskSpec, *, validate: bool = True) -> OperationResult[Task]
```

Performs a server-side dry-run against `/train/check-resources`.

Use this when you want:

- full server validation
- no real task creation

If `validate=True`, the SDK runs client-side validation first.

## `tasks.exists(name, *, status_flag=0, refresh=False)`

Sync:

```python
exists(name: str, *, status_flag: int = 0, refresh: bool = False) -> Task | None
```

Async:

```python
await exists(name: str, *, status_flag: int = 0, refresh: bool = False) -> Task | None
```

Looks for an existing task with the exact name.

This is mainly used internally by idempotent create flows, but it can also be useful when you want a quick existence check without exception handling.

## `tasks.create(...)`

Sync:

```python
create(
    spec: TaskSpec,
    *,
    dry_run: bool = False,
    validate: bool = True,
    precheck: bool = True,
    idempotent: bool = True,
) -> OperationResult[Task]
```

Async:

```python
await create(
    spec: TaskSpec,
    *,
    dry_run: bool = False,
    validate: bool = True,
    precheck: bool = True,
    idempotent: bool = True,
) -> OperationResult[Task]
```

This is the main task submission entry point.

### Parameters

| Parameter | Meaning |
| --- | --- |
| `dry_run` | Return the final payload without performing any server call. |
| `validate` | Run client-side `TaskSpec` validation first. |
| `precheck` | Call `/train/check-resources` before the real create call. |
| `idempotent` | If an unfinished task with the same name already exists, return that task instead of creating a duplicate. |

### Create flow

When `dry_run=False`, the create flow is:

1. Optionally validate the spec locally.
2. Build the backend payload.
3. Optionally check for an existing task by name.
4. Optionally run the server precheck endpoint.
5. Submit the real create request.
6. Invalidate caches.
7. Try to resolve the newly created task.

### Eventual consistency handling

The SDK includes a short read-after-write retry path because the created task may not be visible immediately.

That means `create()` is more reliable than simply doing:

```python
client.post("/api/iresource/v1/train", json=payload)
client.tasks.get(task_id)
```

### Return value

`create()` always returns `OperationResult[Task]`.

Common states:

| State | Meaning |
| --- | --- |
| `created=True` | The SDK submitted a create request. |
| `reused=True` | The SDK found an existing task and returned it instead of creating a new one. |
| `entity is not None` | The SDK successfully resolved the created or reused task. |
| `payload is not None` | The request payload is available for inspection. |
| `raw is not None` | Raw server result is available. |

## `tasks.create_and_wait(...)`

Sync:

```python
create_and_wait(
    spec: TaskSpec,
    *,
    validate: bool = True,
    precheck: bool = True,
    idempotent: bool = True,
    timeout: float = 600.0,
    interval: float = 5.0,
    wait_for_pods: bool = False,
    pod_timeout: float = 120.0,
    pod_interval: float = 3.0,
) -> OperationResult[Task]
```

Async:

```python
await create_and_wait(
    spec: TaskSpec,
    *,
    validate: bool = True,
    precheck: bool = True,
    idempotent: bool = True,
    timeout: float = 600.0,
    interval: float = 5.0,
    wait_for_pods: bool = False,
    pod_timeout: float = 120.0,
    pod_interval: float = 3.0,
) -> OperationResult[Task]
```

This is the highest-level task submission helper.

Behavior:

- creates the task
- requires that the task can be resolved
- waits until the task reaches a ready/terminal state
- optionally waits for pods with exposed ports

The returned `OperationResult` has:

- `waited=True`
- `entity` replaced with the final waited task state
- optional `extras["pods"]`

## `tasks.delete(task_id)`

Sync:

```python
delete(task_id: str | Task | list[str | Task]) -> OperationResult[Task]
```

Async:

```python
await delete(task_id: str | Task | list[str | Task]) -> OperationResult[Task]
```

Deletes one or more tasks via the backend soft-delete API.

### Accepted inputs

- single task ID
- single `Task` object
- list of IDs
- list of `Task` objects

### Result

The returned `OperationResult` includes:

- `action="delete"`
- `target_id` when exactly one task was provided
- `target_ids` for all deleted tasks

## `tasks.stop(task_id)`

Sync:

```python
stop(task_id: str | Task) -> OperationResult[Task]
```

Async:

```python
await stop(task_id: str | Task) -> OperationResult[Task]
```

Stops a running task.

This is different from delete:

- `stop()` requests workload termination
- `delete()` removes the task entry from normal listings

## `tasks.wait_running(task_id, *, timeout=600.0, interval=5.0)`

Sync:

```python
wait_running(task_id: str | Task, *, timeout: float = 600.0, interval: float = 5.0) -> Task
```

Async:

```python
await wait_running(task_id: str | Task, *, timeout: float = 600.0, interval: float = 5.0) -> Task
```

Waits until the task reaches:

- `Running`
- or a failure/terminal state that ends the watch path

This is a convenience wrapper around the watch helpers.

## `tasks.wait_pods(task_id, *, timeout=120.0, interval=3.0)`

Sync:

```python
wait_pods(task_id: str | Task, *, timeout: float = 120.0, interval: float = 3.0) -> list[Pod]
```

Async:

```python
await wait_pods(task_id: str | Task, *, timeout: float = 120.0, interval: float = 3.0) -> list[Pod]
```

Waits until pods with usable port mappings appear.

This is useful when your automation needs SSH, Jupyter, tensorboard, or another exposed endpoint.

## `tasks.invalidate_cache()`

Sync and async:

```python
invalidate_cache() -> None
```

Clears the short task-list cache maintained by the SDK.

## Watch helpers

These helpers live in `aistation.watch` and `aistation.aio.watch`.

### `watch.watch_task(...)`

Sync:

```python
watch_task(
    client: AiStationClient,
    task_id: str,
    *,
    interval: float = 5.0,
    timeout: float = 600.0,
    until: set[str] | None = None,
) -> Iterator[Task]
```

Async:

```python
watch_task(
    client: AsyncAiStationClient,
    task_id: str,
    *,
    interval: float = 5.0,
    timeout: float = 600.0,
    until: set[str] | None = None,
) -> AsyncIterator[Task]
```

Yields a new `Task` state each time the status changes.

Default stop set includes:

- `Running`
- `Succeeded`
- `Failed`
- `Terminating`

Network transport errors are retried by sleeping and polling again.

### `watch.wait_running(...)`

Returns the final `Task` once the watch reaches a running or terminal outcome.

### `watch.wait_pods(...)`

Returns the first pod list that contains usable node IP plus port mappings.

## Typical patterns

### Create a hold task and wait for exposed pods

```python
spec = A.TaskSpec.gpu_hold(
    resource_group="8A100_80",
    image="pytorch/pytorch:21.10-py3",
    cards=1,
    hours=4,
)
result = client.tasks.create_and_wait(spec, wait_for_pods=True)
task = result.unwrap()
pods = result.extras.get("pods", [])
```

### Clone an existing task

```python
existing = client.tasks.get("task-id")
spec = A.TaskSpec.from_existing(existing)
spec.command = "bash /workspace/new_train.sh"
cloned = client.tasks.create(spec)
```

### Resolve by name and stop

```python
task = client.tasks.resolve("mytask")
client.tasks.stop(task)
```

## Related modules

- Validation helpers are documented in [helpers.md](./helpers.md)
- Discovery helpers for automatic payload correction are documented in [helpers.md](./helpers.md)
- The `Task` model and `OperationResult` are documented in [reference.md](./reference.md)
