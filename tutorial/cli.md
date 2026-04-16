# CLI

This document covers the operational CLI surface for task and development-environment workflows.

The Python SDK remains the primary programmable interface. The CLI exists for:

- shell usage
- skill orchestration
- stable JSON output in automation
- quick inspection and lifecycle operations without writing Python code

## Design Goals

The CLI is designed around a few rules:

- Every task and env command supports `--json`.
- `--short` keeps JSON payloads focused on the fields a skill usually needs next.
- Create commands support both:
  - flag-driven construction
  - JSON/YAML spec files
- Destructive operations are explicit commands:
  - `task delete`
  - `task stop`
  - `env delete`
- Read and write commands share one naming model:
  - `task list/get/resolve/create/delete/...`
  - `env list/get/resolve/create/delete/...`

## Global CLI Behavior

All examples below inherit the root CLI options:

```bash
aistation --json --short ...
```

### Output modes

| Option | Meaning |
| --- | --- |
| `--json` | Emit JSON instead of tables |
| `--short` | When combined with JSON, keep only key fields |
| `--quiet` | Print only core identifiers or values |
| `--timeout` | Override the configured default timeout |
| `--auth` | Override the auth file path |
| `--config` | Override the config file path |

### Auth behavior

Read commands prefer cached-token usage.

Write commands such as `task create`, `task delete`, `task stop`, `env create`, and `env delete` use a client configuration that can refresh auth automatically when login credentials are available in the saved config/auth state.

## Common Validation Rules

The CLI validates a number of inputs before it calls the SDK or the server.

Examples:

- `task list --status` must be one of the documented status values
- wait timeouts and polling intervals must be greater than `0`
- `--page` and `--size` for history commands must be at least `1`
- repeated `--port` values must be within `1..65535`
- non-negative numeric fields such as `--cards`, `--cpu`, and `--memory-gb` are checked before create

When `--json` is enabled, these validation errors are returned in the normal structured error envelope with:

- `error.code`
- `error.message`
- `error.field`
- `error.exit_code`

## Command Tree

The task and env command groups are:

```text
aistation task list
aistation task get
aistation task resolve
aistation task pods
aistation task logs
aistation task wait
aistation task create
aistation task delete
aistation task stop

aistation env list
aistation env get
aistation env history
aistation env resolve
aistation env urls
aistation env wait
aistation env create
aistation env delete
```

## Task Commands

## `task list`

```bash
aistation task list --status running --json --short
```

### Status filter

Supported `--status` values:

- `running`
- `unfinished`
- `pending`
- `finished`
- `done`
- `all`

### JSON shape

```json
{
  "items": [
    {
      "id": "task-1",
      "name": "TaskOne",
      "status": "Running",
      "resource_group_name": "GPU-POOL-A",
      "image": "registry.example.invalid/ml/pytorch:latest",
      "cards": 1
    }
  ],
  "count": 1,
  "status": "running"
}
```

## `task get`

```bash
aistation task get task-1 --json --short
```

This command resolves the reference, returns the task, and also fetches pods.

### JSON shape

```json
{
  "item": {
    "id": "task-1",
    "name": "TaskOne",
    "status": "Running"
  },
  "pods": [
    {
      "pod_id": "pod-1",
      "pod_status": "Running",
      "node_ip": "198.51.100.10",
      "external_urls": [
        "198.51.100.10:30080"
      ]
    }
  ],
  "pod_count": 1
}
```

## `task resolve`

```bash
aistation task resolve my-training-name --json --short
```

Use this when a skill has a fuzzy or human-entered identifier and needs one canonical task object before the next step.

### JSON shape

```json
{
  "query": "my-training-name",
  "item": {
    "id": "task-1",
    "name": "my-training-name",
    "status": "Running"
  }
}
```

## `task pods`

```bash
aistation task pods task-1 --json --short
```

This is the focused pod-inspection command. It is useful when the task object is already known and the skill only needs network endpoints or node placement.

### JSON shape

```json
{
  "task_id": "task-1",
  "items": [
    {
      "pod_id": "pod-1",
      "pod_name": "pod-one",
      "pod_status": "Running",
      "node_name": "gpu-node-1",
      "node_ip": "198.51.100.10",
      "external_urls": [
        "198.51.100.10:30080"
      ]
    }
  ],
  "count": 1
}
```

## `task logs`

```bash
aistation task logs task-1 --pod pod-name --json
```

### JSON shape

```json
{
  "task_id": "task-1",
  "pod": "pod-name",
  "log": "..."
}
```

## `task wait`

```bash
aistation task wait task-1 --for running --json --short
```

Supported conditions:

- `running`
- `pods`

### Wait for running

```bash
aistation task wait task-1 --for running --timeout 600 --interval 5 --json --short
```

JSON shape:

```json
{
  "target": "task-1",
  "condition": "running",
  "item": {
    "id": "task-1",
    "name": "TaskOne",
    "status": "Running"
  }
}
```

### Wait for pods

```bash
aistation task wait task-1 --for pods --pod-timeout 120 --pod-interval 3 --json --short
```

JSON shape:

```json
{
  "target": "task-1",
  "condition": "pods",
  "item": {
    "id": "task-1",
    "name": "TaskOne",
    "status": "Running"
  },
  "pods": [
    {
      "pod_id": "pod-1",
      "pod_status": "Running"
    }
  ],
  "pod_count": 1
}
```

## `task create`

`task create` supports two input modes:

1. all-important fields from flags
2. a JSON/YAML spec file via `--file`

You can combine them. When both are present:

- scalar CLI options override file values
- `env` and `raw_overrides` are merged
- list-style CLI inputs replace file lists

### Flag-driven creation

```bash
aistation task create \
  --name MyTrainJob \
  --group 8A100_80 \
  --image pytorch/pytorch:21.10-py3 \
  --command "python train.py --epochs 10" \
  --cards 1 \
  --cpu 16 \
  --memory-gb 32 \
  --port 6006 \
  --env WANDB_MODE=offline \
  --json --short
```

### Spec-file creation

```bash
aistation task create --file task.yaml --json --short
```

Example `task.yaml`:

```yaml
task:
  name: MyTrainJob
  resource_group: 8A100_80
  image: pytorch/pytorch:21.10-py3
  command: python train.py --epochs 10
  cards: 1
  cpu: 16
  memory_gb: 32
  distributed: node
  env:
    WANDB_MODE: offline
```

### File plus CLI overrides

```bash
aistation task create \
  --file task.yaml \
  --cpu 24 \
  --env EXTRA_FLAG=1 \
  --json --short
```

### Advanced repeated options

These options accept JSON/YAML object literals and may be repeated:

- `--dataset-json`
- `--model-json`
- `--raw-override-json`

Example:

```bash
aistation task create \
  --name DataTrain \
  --group 8A100_80 \
  --image pytorch/pytorch:21.10-py3 \
  --command "python train.py" \
  --dataset-json '{"file_model": 2, "function_model": 1, "volume_mount": "/data", "storage_name": "master"}' \
  --raw-override-json '{"timeoutFlag": 0}' \
  --json
```

### Lifecycle flags

| Option | Meaning |
| --- | --- |
| `--dry-run` | Build the payload only |
| `--validate / --no-validate` | Enable or skip client-side validation |
| `--precheck / --no-precheck` | Enable or skip the server-side task precheck |
| `--idempotent / --no-idempotent` | Reuse an active same-name task when possible |
| `--wait` | Wait until the created task becomes running |
| `--wait-pods` | Wait until pods are available after create |

### Dry-run JSON shape

```json
{
  "action": "create",
  "resource_type": "task",
  "created": false,
  "reused": false,
  "waited": false,
  "payload": {
    "name": "MyTrainJob"
  }
}
```

### Normal create JSON shape

```json
{
  "action": "create",
  "resource_type": "task",
  "target_id": "task-created-1",
  "target_ids": [
    "task-created-1"
  ],
  "created": true,
  "reused": false,
  "waited": false,
  "item": {
    "id": "task-created-1",
    "name": "MyTrainJob",
    "status": "Running"
  }
}
```

### Create-and-wait JSON shape

If `--wait-pods` is used, the result also contains:

- `pods`
- `pod_count`

## `task delete`

```bash
aistation task delete task-1 old-task-name --json
```

This command accepts one or more task references. Each reference is resolved before deletion.

JSON shape:

```json
{
  "action": "delete",
  "resource_type": "task",
  "target_id": "task-1",
  "target_ids": [
    "task-1",
    "task-2"
  ],
  "created": false,
  "reused": false,
  "waited": false,
  "count": 2
}
```

## `task stop`

```bash
aistation task stop task-1 --json --short
```

Use this when you need to terminate execution without deleting the historical record immediately.

## Env Commands

## `env list`

```bash
aistation env list --json --short
```

JSON shape:

```json
{
  "items": [
    {
      "wp_id": "wp-1",
      "wp_name": "DevBoxOne",
      "wp_status": "Running",
      "group_name": "DEV-POOL",
      "cpu": 4,
      "memory_gb": 16,
      "cards": 0
    }
  ],
  "count": 1,
  "include_halted": false
}
```

## `env get`

```bash
aistation env get wp-1 --json --short
```

JSON shape:

```json
{
  "item": {
    "wp_id": "wp-1",
    "wp_name": "DevBoxOne",
    "wp_status": "Running"
  }
}
```

## `env history`

```bash
aistation env history --page 1 --size 20 --json --short
```

JSON shape:

```json
{
  "items": [
    {
      "wp_id": "wp-history-1",
      "wp_name": "OldEnv",
      "wp_status": "Stopped"
    }
  ],
  "count": 1,
  "page": 1,
  "page_size": 20
}
```

## `env resolve`

```bash
aistation env resolve notebook-name --json --short
```

JSON shape:

```json
{
  "query": "notebook-name",
  "item": {
    "wp_id": "wp-1",
    "wp_name": "notebook-name",
    "wp_status": "Running"
  }
}
```

## `env urls`

```bash
aistation env urls wp-1 --json
```

This command returns access information from both:

- `workplatforms.jupyter_url()`
- `workplatforms.shell_url()`

JSON shape:

```json
{
  "wp_id": "wp-1",
  "jupyter": {
    "url": "https://example.test/jupyter/wp-1"
  },
  "shell": {
    "url": "https://example.test/shell/wp-1"
  }
}
```

## `env wait`

```bash
aistation env wait wp-1 --timeout 600 --interval 5 --json --short
```

JSON shape:

```json
{
  "target": "wp-1",
  "condition": "ready",
  "item": {
    "wp_id": "wp-1",
    "wp_name": "DevBoxOne",
    "wp_status": "Running"
  }
}
```

## `env create`

Like `task create`, `env create` supports both flags and `--file`.

### Flag-driven creation

```bash
aistation env create \
  --name NotebookOne \
  --group DEV-POOL \
  --image registry.example.invalid/ml/dev:latest \
  --command "sleep infinity" \
  --cpu 4 \
  --memory-gb 16 \
  --port 8888 \
  --env MODE=lab \
  --json --short
```

### Spec-file creation

```bash
aistation env create --file env.yaml --json --short
```

Example `env.yaml`:

```yaml
env:
  name: NotebookOne
  resource_group: DEV-POOL
  image: registry.example.invalid/ml/dev:latest
  command: sleep infinity
  cpu: 4
  memory_gb: 16
  env:
    MODE: lab
```

### Advanced repeated options

These options accept JSON/YAML object literals and may be repeated:

- `--volume-json`
- `--model-json`
- `--raw-override-json`

### Lifecycle flags

| Option | Meaning |
| --- | --- |
| `--dry-run` | Build the payload only |
| `--idempotent / --no-idempotent` | Reuse an active same-name env when possible |
| `--wait` | Wait until the env is ready |

### Create JSON shape

```json
{
  "action": "create",
  "resource_type": "workplatform",
  "target_id": "wp-created-1",
  "target_ids": [
    "wp-created-1"
  ],
  "created": true,
  "reused": false,
  "waited": false,
  "item": {
    "wp_id": "wp-created-1",
    "wp_name": "NotebookOne",
    "wp_status": "Running"
  }
}
```

## `env delete`

```bash
aistation env delete wp-1 --json --short
```

JSON shape:

```json
{
  "action": "delete",
  "resource_type": "workplatform",
  "target_id": "wp-1",
  "target_ids": [
    "wp-1"
  ],
  "created": false,
  "reused": false,
  "waited": false,
  "item": {
    "wp_id": "wp-1",
    "wp_name": "DevBoxOne",
    "wp_status": "Running"
  }
}
```

## Recommended Skill Patterns

For skills or automation, these are the recommended flows.

### Create task from a generated file

1. Generate `task.yaml`
2. Run `aistation task create --file task.yaml --json --short`
3. Read `target_id` and `item.id`
4. If needed, run `aistation task wait <id> --for pods --json --short`

### Resolve then inspect

1. Run `aistation task resolve <query> --json --short`
2. Extract `item.id`
3. Run `aistation task pods <id> --json --short` or `aistation task logs <id> --json`

### Create env and fetch entry URLs

1. Run `aistation env create --file env.yaml --wait --json --short`
2. Extract `item.wp_id`
3. Run `aistation env urls <wp_id> --json`

## Choosing CLI vs SDK

Prefer the CLI when:

- you are inside a shell workflow
- your skill is already shell-oriented
- you want stable JSON without writing Python glue

Prefer the SDK when:

- you need richer programmatic branching
- you are constructing complex specs directly in Python
- you need direct access to returned dataclasses and lower-level API methods
