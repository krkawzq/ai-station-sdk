# AI Station SDK Tutorial and API Reference

This folder contains the full English documentation set for the Python SDK.

The goal of this documentation is not to be a short getting-started guide. It is an exhaustive reference for the supported SDK surface, written for users who need to understand the API in detail before building real automation or integrations.

## Scope

This reference covers:

- Everything exported from `aistation.__all__`
- Everything exported from `aistation.aio.__all__`
- The task/env operational CLI surface intended for shell and skill orchestration
- The complete method surface of the client-attached API objects:
  - `client.nodes`
  - `client.groups`
  - `client.images`
  - `client.tasks`
  - `client.workplatforms`
  - and their async equivalents
- Helper modules that are part of normal SDK use:
  - `aistation.presets`
  - `aistation.watch`
  - `aistation.recommend`
  - `aistation.validation`
  - `aistation.form_context.enumerate_form_context`
  - `aistation.discovery.discover_payload_requirements`
  - async mirrors under `aistation.aio`
- Public data models, enums, configuration objects, and error types

This reference does not document internal/private implementation modules such as:

- `aistation.cli._*`
- `aistation.transport.*`
- `aistation.builders.*`
- `aistation._*`

Those modules may be importable, but they are implementation details rather than the intended stable SDK contract.

## Reading Order

If you are new to the SDK, read the files in this order:

1. [clients.md](./clients.md)
2. [cli.md](./cli.md)
3. [resources-and-images.md](./resources-and-images.md)
4. [tasks.md](./tasks.md)
5. [workplatforms.md](./workplatforms.md)
6. [helpers.md](./helpers.md)
7. [reference.md](./reference.md)

If you already know the SDK and only need exact signatures or behavior, jump directly to the topic file you need.

## Coverage Matrix

### Package Entry Points

| Symbol | Where documented |
| --- | --- |
| `AiStationClient` | [clients.md](./clients.md) |
| `AsyncAiStationClient` | [clients.md](./clients.md) |
| `aio` | [clients.md](./clients.md), [helpers.md](./helpers.md) |
| `presets` | [tasks.md](./tasks.md) |
| `recommend` | [helpers.md](./helpers.md) |
| `specs` | [tasks.md](./tasks.md), [workplatforms.md](./workplatforms.md) |
| `validation` | [helpers.md](./helpers.md) |
| `watch` | [tasks.md](./tasks.md), [workplatforms.md](./workplatforms.md) |

### Operational CLI

| Surface | Where documented |
| --- | --- |
| `aistation task ...` | [cli.md](./cli.md) |
| `aistation env ...` | [cli.md](./cli.md) |
| task/env JSON output conventions | [cli.md](./cli.md) |
| task/env spec-file format | [cli.md](./cli.md) |

### Configuration and Auth

| Symbol | Where documented |
| --- | --- |
| `AuthData` | [reference.md](./reference.md) |
| `Config` | [reference.md](./reference.md) |
| `CONFIG_DIR` | [reference.md](./reference.md) |
| `AUTH_FILE` | [reference.md](./reference.md) |
| `CONFIG_FILE` | [reference.md](./reference.md) |
| `load_auth()` | [reference.md](./reference.md) |
| `save_auth()` | [reference.md](./reference.md) |
| `load_config()` | [reference.md](./reference.md) |
| `TTLCache` | [reference.md](./reference.md) |
| `AuthStatus` | [reference.md](./reference.md), [clients.md](./clients.md) |

### Core Client-Attached APIs

| API object | Where documented |
| --- | --- |
| `client.nodes` / `async_client.nodes` | [resources-and-images.md](./resources-and-images.md) |
| `client.groups` / `async_client.groups` | [resources-and-images.md](./resources-and-images.md) |
| `client.images` / `async_client.images` | [resources-and-images.md](./resources-and-images.md) |
| `client.tasks` / `async_client.tasks` | [tasks.md](./tasks.md) |
| `client.workplatforms` / `async_client.workplatforms` | [workplatforms.md](./workplatforms.md) |

### Specs and Presets

| Symbol | Where documented |
| --- | --- |
| `TaskSpec` | [tasks.md](./tasks.md) |
| `WorkPlatformSpec` | [workplatforms.md](./workplatforms.md) |
| `presets.gpu_hold()` | [tasks.md](./tasks.md) |
| `presets.cpu_debug()` | [tasks.md](./tasks.md) |
| `presets.pytorch_train()` | [tasks.md](./tasks.md) |
| `presets.from_existing()` | [tasks.md](./tasks.md) |

### Helper Functions

| Symbol | Where documented |
| --- | --- |
| `enumerate_form_context()` | [helpers.md](./helpers.md) |
| `discover_payload_requirements()` | [helpers.md](./helpers.md) |
| `aio.enumerate_form_context()` | [helpers.md](./helpers.md) |
| `aio.discover_payload_requirements()` | [helpers.md](./helpers.md) |
| `recommend.suggest_groups()` | [helpers.md](./helpers.md) |
| `recommend.suggest_images()` | [helpers.md](./helpers.md) |
| `aio.recommend.suggest_groups()` | [helpers.md](./helpers.md) |
| `aio.recommend.suggest_images()` | [helpers.md](./helpers.md) |
| `watch.watch_task()` | [tasks.md](./tasks.md) |
| `watch.wait_running()` | [tasks.md](./tasks.md) |
| `watch.wait_pods()` | [tasks.md](./tasks.md) |
| `aio.watch.watch_task()` | [tasks.md](./tasks.md) |
| `aio.watch.wait_running()` | [tasks.md](./tasks.md) |
| `aio.watch.wait_pods()` | [tasks.md](./tasks.md) |
| `watch.watch_workplatform()` | [workplatforms.md](./workplatforms.md) |
| `watch.wait_workplatform_ready()` | [workplatforms.md](./workplatforms.md) |
| `aio.watch.watch_workplatform()` | [workplatforms.md](./workplatforms.md) |
| `aio.watch.wait_workplatform_ready()` | [workplatforms.md](./workplatforms.md) |
| `validation.validate_spec()` | [helpers.md](./helpers.md) |
| `validation.validate_group_card_compatibility()` | [helpers.md](./helpers.md) |

### Models

| Symbol | Where documented |
| --- | --- |
| `User` | [reference.md](./reference.md) |
| `Port` | [reference.md](./reference.md) |
| `Node` | [reference.md](./reference.md) |
| `ResourceGroup` | [reference.md](./reference.md) |
| `Image` | [reference.md](./reference.md) |
| `ImageType_` | [reference.md](./reference.md) |
| `Task` | [reference.md](./reference.md) |
| `Pod` | [reference.md](./reference.md) |
| `JobVolume` | [reference.md](./reference.md) |
| `TaskType` | [reference.md](./reference.md) |
| `WorkPlatform` | [reference.md](./reference.md) |
| `FormContext` | [reference.md](./reference.md) |
| `OperationResult` | [reference.md](./reference.md) |
| `DiscoveryStep` | [reference.md](./reference.md) |
| `DiscoveryReport` | [reference.md](./reference.md) |

### Enums and Errors

| Symbol | Where documented |
| --- | --- |
| `AuthMode` | [reference.md](./reference.md) |
| `ReauthPolicy` | [reference.md](./reference.md) |
| `SwitchType` | [reference.md](./reference.md) |
| `CardKind` | [reference.md](./reference.md) |
| `PodStatus` | [reference.md](./reference.md) |
| `TaskStatus` | [reference.md](./reference.md) |
| `ImageType` | [reference.md](./reference.md) |
| `FunctionModel` | [reference.md](./reference.md) |
| `ShareType` | [reference.md](./reference.md) |
| `MakeType` | [reference.md](./reference.md) |
| `RoleType` | [reference.md](./reference.md) |
| `AiStationError` and all documented subclasses | [reference.md](./reference.md) |
| `lookup_error_guide()` | [reference.md](./reference.md) |

## Design Notes

The SDK intentionally exposes both:

- ergonomic, intent-first APIs such as `TaskSpec.gpu_hold()` or `WorkPlatformSpec.notebook()`
- lower-level raw request helpers such as `client.get()` or `client.list_all()`

You should prefer the high-level APIs whenever possible. The lower-level helpers exist for endpoints that are not yet wrapped or for debugging unusual server behavior.

## Version

This tutorial set is written for SDK version `0.3.0`.
