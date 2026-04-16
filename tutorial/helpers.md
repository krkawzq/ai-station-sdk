# Helpers

This document covers the public helper surface around the core client APIs:

- `aistation.enumerate_form_context()`
- `aistation.discover_payload_requirements()`
- `aistation.recommend.*`
- `aistation.validation.*`
- async mirrors exposed through `aistation.aio`

These helpers are not thin aliases for a single endpoint. They are higher-level convenience utilities that combine multiple SDK behaviors into one call.

## Module Layout

Sync entry points:

- `aistation.enumerate_form_context`
- `aistation.discover_payload_requirements`
- `aistation.recommend.suggest_groups`
- `aistation.recommend.suggest_images`
- `aistation.validation.validate_spec`
- `aistation.validation.validate_group_card_compatibility`

Async entry points:

- `aistation.aio.enumerate_form_context`
- `aistation.aio.discover_payload_requirements`
- `aistation.aio.recommend.suggest_groups`
- `aistation.aio.recommend.suggest_images`

There is no separate async validation module because validation is pure client-side logic and does not perform I/O.

## Form Context Enumeration

`enumerate_form_context()` builds a single `FormContext` object containing the reference data typically needed before building a task-creation UI, an agent workflow, or a dynamic form.

### Sync API

```python
enumerate_form_context(
    client: AiStationClient,
    *,
    include_all_images: bool = True,
) -> FormContext
```

### Async API

```python
await aistation.aio.enumerate_form_context(
    client: AsyncAiStationClient,
    *,
    include_all_images: bool = True,
) -> FormContext
```

### What it collects

The helper gathers the following pieces of information:

- the current user via `client.require_user()`
- image-type metadata from `/api/iresource/v1/image-type`
- task-type metadata from `/api/iresource/v1/base/timeout-task-type`
- shared-memory editability from `/api/iresource/v1/config/shm`
- start-script choices from `/api/iresource/v1/train/start-file`
- images from `client.images.list(...)`
- resource groups from `client.groups.list()`

### Parameters

| Parameter | Meaning |
| --- | --- |
| `client` | A prepared sync or async client. The helper requires a usable auth state because it calls `require_user()`. |
| `include_all_images` | When `True`, calls `images.list()` with default behavior. When `False`, requests only public images by calling `images.list(share=2)`. |

### Error-tolerance model

This helper is intentionally tolerant.

- It does not fail immediately when one sub-request is denied or returns an SDK error.
- Instead it records the issue in `FormContext.missing`.
- The returned `FormContext` still includes every successfully collected section.

Examples of `missing` entries:

- `image-type: denied (IBASE_NO_PERMISSION)`
- `resource-groups: IBASE_NO_PERMISSION: no permission`
- `train/start-file: TransportError: ...`

This makes the helper suitable for agent workflows where partial context is still useful.

### Returned `FormContext`

The returned object contains:

- `user`
- `resource_groups`
- `images`
- `image_types`
- `task_types`
- `start_scripts`
- `shm_editable`
- `missing`

See [reference.md](./reference.md) for the exact `FormContext` field definitions.

### Example

Sync:

```python
import aistation as A

with A.AiStationClient() as client:
    ctx = A.enumerate_form_context(client, include_all_images=False)
    print(ctx.user.account)
    print(len(ctx.resource_groups), len(ctx.images))
    if ctx.missing:
        print("Partial context:", ctx.missing)
```

Async:

```python
import aistation as A

async with A.AsyncAiStationClient() as client:
    ctx = await A.aio.enumerate_form_context(client)
    print(ctx.shm_editable)
```

## Payload Requirement Discovery

`discover_payload_requirements()` is a live probing helper for task-submission payloads.

It takes a `TaskSpec`, builds the normal task payload, submits it to the server, reads validation failures, applies heuristics, and tries again until the payload is accepted or the helper gives up.

This is useful when:

- the backend contract is stricter than the exposed UI suggests
- the server returns field-level validation hints that you want to learn programmatically
- you are building an agent that needs to recover from task-submit validation errors automatically

### Sync API

```python
discover_payload_requirements(
    client: AiStationClient,
    spec: TaskSpec,
    *,
    max_iterations: int = 15,
    name_prefix: str = "sdkauto",
    auto_delete_created: bool = True,
    verbose: bool = False,
    dry_validate: bool = True,
    submit_timeout: float = 20.0,
) -> DiscoveryReport
```

### Async API

```python
await aistation.aio.discover_payload_requirements(
    client: AsyncAiStationClient,
    spec: TaskSpec,
    *,
    max_iterations: int = 15,
    name_prefix: str = "sdkauto",
    auto_delete_created: bool = True,
    verbose: bool = False,
    dry_validate: bool = True,
    submit_timeout: float = 20.0,
) -> DiscoveryReport
```

### Parameters

| Parameter | Meaning |
| --- | --- |
| `client` | A logged-in sync or async client. |
| `spec` | The starting `TaskSpec` to probe. The helper clones it before modifying the name. |
| `max_iterations` | Maximum number of probe/fix cycles before the helper stops. |
| `name_prefix` | Prefix used to generate a unique probe task name. The helper always replaces `spec.name` with a generated value. |
| `auto_delete_created` | If a real task is created successfully and the helper can resolve its ID, delete it automatically after discovery. |
| `verbose` | Print one short progress line per iteration. Useful for local debugging. |
| `dry_validate` | When `True`, submit against `/api/iresource/v1/train/check-resources`. When `False`, use the real `/api/iresource/v1/train` endpoint. |
| `submit_timeout` | Per-request timeout passed into the low-level request call. |

### Safety model

The helper performs real POST requests.

- With `dry_validate=True`, it uses the safer validation endpoint and should not create a task.
- With `dry_validate=False`, the final successful iteration can create a real task.
- `auto_delete_created=True` only performs cleanup after a successful creation and only if the helper can extract an ID from the response.

### Discovery workflow

On each iteration, the helper:

1. Builds the task payload using the normal SDK task builder.
2. Sends it to the validation or creation endpoint.
3. Parses the returned `errCode` and `errMessage`.
4. Tries to infer one corrective change.
5. Repeats until accepted or until no heuristic applies.

### Heuristics currently implemented

The helper can automatically react to these server-feedback patterns:

- missing required fields
- regex-based format constraints
- numeric range constraints
- `memory >= shm_size * 2` cross-field constraints
- duplicated mount path equal to the account name
- invalid execution directory
- GPU group card-count minimums
- CPU group card-count zero-only requirements

Each iteration is recorded as a `DiscoveryStep`.

### Result object

The return value is a `DiscoveryReport` containing:

- `success`
- `iterations`
- `steps`
- `final_payload`
- `final_response`
- `created_task_id`
- `constraints`
- `missing_fields`

See [reference.md](./reference.md) for the exact `DiscoveryStep` and `DiscoveryReport` field definitions.

### Typical usage

```python
import aistation as A

spec = A.TaskSpec.pytorch_train(
    resource_group="8A100_80",
    image="pytorch/pytorch:21.10-py3",
    command="python train.py",
)

with A.AiStationClient() as client:
    report = A.discover_payload_requirements(client, spec, verbose=True)
    print(report.success)
    print(report.constraints)
    print(report.missing_fields)
```

### Interpreting `DiscoveryStep.action`

Common action values include:

- `accepted`
- `fix_missing`
- `fix_regex`
- `fix_range`
- `fix_cross_mem_shm`
- `fix_mount_path`
- `fix_exec_dir`
- `fix_gpu_min_card`
- `fix_cpu_zero_card`
- `give_up`

Treat these as descriptive workflow markers, not as a stable enum type.

## Recommendation Helpers

The `recommend` module ranks likely-good groups and images using data already available through the SDK APIs.

### Important behavior

These helpers do not issue raw endpoint calls directly. They call:

- `client.groups.list()`
- `client.images.list()`

That means:

- if the relevant cache is already warm, the helper is effectively local
- if the cache is cold or `list()` decides to refresh, the usual SDK network calls still happen

## `recommend.suggest_groups(...)`

Sync:

```python
suggest_groups(
    client: AiStationClient,
    *,
    card_type_contains: str | None = None,
    min_free_cards: int = 1,
    min_card_memory_gb: int | None = None,
    card_kind: str = "GPU",
    include_private: bool = False,
) -> list[ResourceGroup]
```

Async:

```python
await aistation.aio.recommend.suggest_groups(
    client: AsyncAiStationClient,
    *,
    card_type_contains: str | None = None,
    min_free_cards: int = 1,
    min_card_memory_gb: int | None = None,
    card_kind: str = "GPU",
    include_private: bool = False,
) -> list[ResourceGroup]
```

### Parameters

| Parameter | Meaning |
| --- | --- |
| `client` | A sync or async client. |
| `card_type_contains` | Case-insensitive substring filter on `ResourceGroup.card_type`. Example: `"A100"`. |
| `min_free_cards` | Minimum `ResourceGroup.free_cards` required for a candidate to remain in the result. |
| `min_card_memory_gb` | Minimum per-card memory parsed from the card-type string when possible. |
| `card_kind` | Required group card kind. Usually `"GPU"` or `"CPU"`. Pass an empty string only if you intentionally want no kind filter. |
| `include_private` | When `False`, groups that look like private or ACL-restricted groups are filtered out heuristically. |

### Ranking behavior

Results are sorted descending by:

1. `free_cards`
2. `total_cards`

### Private-group heuristic

When `include_private=False`, the helper excludes groups that look private according to simple name heuristics.

This is intentionally conservative. It is only a recommendation layer, not a permission check. A returned group can still be unusable for the current account, and a filtered-out group may still be valid for a privileged user.

### Example

```python
import aistation as A
from aistation import recommend

with A.AiStationClient() as client:
    groups = recommend.suggest_groups(
        client,
        card_type_contains="A100",
        min_free_cards=2,
        min_card_memory_gb=40,
    )
```

## `recommend.suggest_images(...)`

Sync:

```python
suggest_images(
    client: AiStationClient,
    *,
    image_type: str | None = None,
    name_contains: str | None = None,
    min_pulls: int = 0,
    prefer_public: bool = True,
    limit: int = 10,
) -> list[Image]
```

Async:

```python
await aistation.aio.recommend.suggest_images(
    client: AsyncAiStationClient,
    *,
    image_type: str | None = None,
    name_contains: str | None = None,
    min_pulls: int = 0,
    prefer_public: bool = True,
    limit: int = 10,
) -> list[Image]
```

### Parameters

| Parameter | Meaning |
| --- | --- |
| `client` | A sync or async client. |
| `image_type` | Exact `Image.image_type` filter such as `pytorch` or `tensorflow`. |
| `name_contains` | Case-insensitive substring filter applied to `Image.full_ref`. |
| `min_pulls` | Minimum image popularity threshold based on `Image.pull_count`. |
| `prefer_public` | When `True`, public images rank ahead of private images. |
| `limit` | Maximum number of returned images. If `0`, the helper returns all ranked matches. |

### Ranking behavior

Results are ranked descending by:

1. public-image preference when `prefer_public=True`
2. `pull_count`

### Example

```python
import aistation as A
from aistation import recommend

with A.AiStationClient() as client:
    images = recommend.suggest_images(
        client,
        image_type="pytorch",
        name_contains="21.10",
        min_pulls=10,
        limit=5,
    )
```

## Validation Helpers

The `validation` module performs local preflight checks before you contact the server.

This is especially valuable for:

- agent-generated `TaskSpec` objects
- batch submission pipelines
- interactive tools that want immediate, field-specific feedback

## `validation.validate_spec(spec, user=None)`

```python
validate_spec(spec: TaskSpec, user: User | None = None) -> None
```

This function validates a `TaskSpec` against known backend rules and raises `SpecValidationError` on the first failure.

### Rules enforced

The current validation layer checks:

- `name` must be non-empty and strictly alphanumeric
- `image` must resolve to a non-empty reference and must include a tag
- `switch_type` must match the known server regex
- `card_kind` must be one of the supported values
- `image_type` must be one of the supported framework values
- `distributed` must be one of the supported distributed-mode strings
- `memory_gb` must be within the known server range
- `memory_gb` must be at least `shm_size * 2` when both are positive
- `cpu` must be non-negative and below the SDK's conservative upper bound
- `cards` must be non-negative
- `mount_path` cannot be exactly `/{user.account}` when `user` is provided

### Failure model

On failure, the function raises `SpecValidationError` with:

- `err_code="SDK_SPEC_VALIDATION"`
- `field_name` set when the failing field is known

### Example

```python
from aistation import validation
from aistation.errors import SpecValidationError

try:
    validation.validate_spec(spec, user=client.require_user())
except SpecValidationError as exc:
    print(exc.field_name, exc)
```

## `validation.validate_group_card_compatibility(...)`

```python
validate_group_card_compatibility(
    group_card_kind: str,
    spec_card_kind: str,
    spec_cards: int,
) -> None
```

This helper validates the relationship between a resolved resource group and the task card request.

### Rules enforced

- GPU groups require `spec_cards >= 1`
- CPU groups require `spec_cards == 0`
- GPU groups are inconsistent with `spec_card_kind == "CPU"`

This check is separate from `validate_spec()` because it requires resolved resource-group information rather than only the standalone spec.

### Example

```python
from aistation import validation

group = client.groups.resolve(spec.resource_group)
validation.validate_group_card_compatibility(
    group.card_kind,
    spec.card_kind,
    spec.cards,
)
```

## Choosing the Right Helper

Use:

- `enumerate_form_context()` when you need a UI or agent-facing catalog snapshot
- `discover_payload_requirements()` when you need to learn backend validation rules by probing
- `recommend.*` when you want ranked suggestions rather than exhaustive lists
- `validation.*` when you want cheap local checks before making any request
