# Resources and Images

This document covers the inventory-style APIs attached to the client:

- `client.nodes` / `async_client.nodes`
- `client.groups` / `async_client.groups`
- `client.images` / `async_client.images`

These APIs are read-heavy and cache-aware. They are designed to make repeated polling practical for automation.

## Nodes API

### Access

Sync:

```python
nodes_api = client.nodes
```

Async:

```python
nodes_api = client.nodes
```

The attribute name is the same. Only the method calls differ.

## `NodesAPI.list(...)`

Sync:

```python
list(
    *,
    group_id: str | None = None,
    with_usage: bool = True,
    refresh: bool = False,
) -> list[Node]
```

Async:

```python
await list(
    *,
    group_id: str | None = None,
    with_usage: bool = True,
    refresh: bool = False,
) -> list[Node]
```

Returns a list of `Node` objects.

### Parameters

| Parameter | Meaning |
| --- | --- |
| `group_id` | Restrict results to a single resource group ID. |
| `with_usage` | When `True`, sends `getUsage=1`. This is important because AI Station may otherwise return stale or incomplete occupancy information. |
| `refresh` | When `True`, bypasses the 30-second TTL cache. |

### Caching behavior

- Cache TTL is 30 seconds.
- Cache key is `(group_id, with_usage)`.
- Changing either value produces a different cache entry.

### Recommended usage

Use `with_usage=True` unless you have a very specific reason not to. The server is known to return less useful occupancy data without it.

## `NodesAPI.invalidate_cache()`

Sync and async:

```python
invalidate_cache() -> None
```

Clears the node cache.

## `NodesAPI.get(node_id)`

Sync:

```python
get(node_id: str) -> Node
```

Async:

```python
await get(node_id: str) -> Node
```

Fetches a single node detail record.

### Failure mode

Raises `ValueError` if the endpoint does not return the expected dictionary payload.

## Groups API

`GroupsAPI` and `AsyncGroupsAPI` are aggregation layers built on top of node data.

They do not hit a separate “groups list” endpoint for the standard training resource view. Instead they aggregate from `nodes.list()`.

## `GroupsAPI.list(...)`

Sync:

```python
list(*, refresh: bool = False) -> list[ResourceGroup]
```

Async:

```python
await list(*, refresh: bool = False) -> list[ResourceGroup]
```

Returns `ResourceGroup` objects synthesized from the current node list.

### Derived values

Each group aggregates:

- node count
- total cards
- used cards
- total CPU
- total memory
- node names

### Important note

This is a training-resource-group view. Development-environment groups are handled separately by `client.workplatforms.list_groups()` because that API needs `groupLabel=develop`.

## `GroupsAPI.by_name(name)`

Sync:

```python
by_name(name: str) -> ResourceGroup | None
```

Async:

```python
await by_name(name: str) -> ResourceGroup | None
```

Returns the matching group by exact group name, or `None` if not found.

## `GroupsAPI.resolve_many(query)`

Sync:

```python
resolve_many(query: str) -> list[ResourceGroup]
```

Async:

```python
await resolve_many(query: str) -> list[ResourceGroup]
```

Performs fuzzy resolution against:

- `group_id`
- `group_name`

Matching strategy is exact, then suffix, then contains.

## `GroupsAPI.resolve(name_or_id)`

Sync:

```python
resolve(name_or_id: str) -> ResourceGroup
```

Async:

```python
await resolve(name_or_id: str) -> ResourceGroup
```

Returns a single group or raises:

- `NotFoundError`
- `AmbiguousMatchError`

## `GroupsAPI.resolve_id(name_or_id)`

Sync:

```python
resolve_id(name_or_id: str) -> str
```

Async:

```python
await resolve_id(name_or_id: str) -> str
```

Convenience wrapper that returns only the `group_id`.

## Images API

The images API wraps the image catalog plus a few image-related operations.

### Cache model

Images change infrequently, so the SDK uses a 5-minute cache for:

- image list
- image type list

## `ImagesAPI.list(...)`

Sync:

```python
list(
    *,
    share: int | None = None,
    image_type: str | None = None,
    refresh: bool = False,
) -> list[Image]
```

Async:

```python
await list(
    *,
    share: int | None = None,
    image_type: str | None = None,
    refresh: bool = False,
) -> list[Image]
```

Returns a list of `Image` models.

### Parameters

| Parameter | Meaning |
| --- | --- |
| `share` | Filter by share mode. In practice, `1` is private and `2` is public. See `ShareType` in [reference.md](./reference.md). |
| `image_type` | Filter by image framework type such as `pytorch`, `tensorflow`, or `other`. |
| `refresh` | Bypass the cached full image list. |

### Notes

- Filtering happens after the cached full image list is loaded.
- `refresh=True` refreshes the full catalog before filtering.

## `ImagesAPI.invalidate_cache()`

Sync and async:

```python
invalidate_cache() -> None
```

Clears both:

- image list cache
- image-type list cache

## `ImagesAPI.types()`

Sync:

```python
types() -> list[ImageType_]
```

Async:

```python
await types() -> list[ImageType_]
```

Fetches image type metadata from `/api/iresource/v1/image-type`.

Return type is `ImageType_` because the backend response is a lightweight type table rather than a full image object.

## `ImagesAPI.resolve_many(image_ref)`

Sync:

```python
resolve_many(image_ref: str) -> list[Image]
```

Async:

```python
await resolve_many(image_ref: str) -> list[Image]
```

Matches against:

- `id`
- `full_ref`
- “short ref” with registry prefix removed
- raw `name`

This makes the resolver flexible. For example, both of these often work:

- `192.168.108.1:5000/pytorch/pytorch:21.10-py3`
- `pytorch/pytorch:21.10-py3`

## `ImagesAPI.resolve(image_ref)`

Sync:

```python
resolve(image_ref: str) -> Image
```

Async:

```python
await resolve(image_ref: str) -> Image
```

Returns a single image or raises `NotFoundError` / `AmbiguousMatchError`.

## `ImagesAPI.check(image_name, image_tag)`

Sync:

```python
check(image_name: str, image_tag: str) -> OperationResult[Image]
```

Async:

```python
await check(image_name: str, image_tag: str) -> OperationResult[Image]
```

Validates whether the specified image reference is acceptable to the backend.

This is a low-side-effect check call. It returns an `OperationResult` containing:

- `action="check"`
- `resource_type="image"`
- `payload`
- `raw`

It usually does not resolve an `Image` entity.

## `ImagesAPI.import_external(...)`

Sync:

```python
import_external(
    *,
    image_name: str,
    image_tag: str,
    image_type: str,
    share: int = 1,
    comment: str = "",
    alias_name: str = "",
    username: str = "",
    password: str = "",
) -> OperationResult[Image]
```

Async:

```python
await import_external(
    *,
    image_name: str,
    image_tag: str,
    image_type: str,
    share: int = 1,
    comment: str = "",
    alias_name: str = "",
    username: str = "",
    password: str = "",
) -> OperationResult[Image]
```

Imports an external image into AI Station.

### Parameters

| Parameter | Meaning |
| --- | --- |
| `image_name` | Repository name without the tag |
| `image_tag` | Image tag |
| `image_type` | Backend image type string |
| `share` | Visibility flag |
| `comment` | Optional image comment |
| `alias_name` | Optional alias name |
| `username` | Registry username if needed |
| `password` | Registry password if needed |

### Return value

Returns an `OperationResult` containing raw server data and, when available, a backend task or image identifier in `target_id`.

The SDK invalidates the image caches after this call.

## `ImagesAPI.progress(task_id)`

Sync:

```python
progress(task_id: str) -> dict[str, Any]
```

Async:

```python
await progress(task_id: str) -> dict[str, Any]
```

Queries progress for an image import task.

This method returns the raw progress dictionary rather than an `OperationResult`.

## Recommended Patterns

### Get a usable training group

```python
group = client.groups.resolve("8A100_80")
nodes = client.nodes.list(group_id=group.group_id, refresh=True)
```

### Find a public PyTorch image

```python
images = client.images.list(share=2, image_type="pytorch")
image = client.images.resolve("pytorch/pytorch:21.10-py3")
```

### Refresh caches explicitly

```python
client.nodes.invalidate_cache()
client.images.invalidate_cache()
```

Use explicit invalidation when another tool or user may have changed server state outside your current process.
