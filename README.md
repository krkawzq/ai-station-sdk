# aistation

AI Station 的非官方 Python SDK 和 CLI。

> 仍然需要vpn解决内网环境

## 安装

```bash
pip install ai-station-sdk
```

如果你需要 CLI：

```bash
pip install "ai-station-sdk[cli]"
```

## CLI

CLI 主要用来查询状态。

```bash
aistation login # 交互式登录

# or
# export AISTATION_ACCOUNT=your_account
# export AISTATION_PASSWORD='your_password'
# aistation login

aistation status
aistation gpus --free
aistation tasks
```

## Python

```python
import aistation as A

with A.AiStationClient() as client:
    spec = A.TaskSpec.gpu_hold(
        resource_group="8A100_80",
        image="pytorch/pytorch:21.10-py3",
        hours=2,
    )
    result = client.tasks.create_and_wait(spec)
    task = result.unwrap()
    pods = client.tasks.wait_pods(task)
    print(task.id, len(pods))
```

如果你只想恢复本地 token、不做自动登录：

```python
import aistation as A

client = A.AiStationClient(auth_mode=A.AuthMode.TOKEN_ONLY)
```

如果你想显式控制请求遇到过期 token 时是否自动重登：

```python
import aistation as A

client = A.AiStationClient(reauth_policy=A.ReauthPolicy.IF_POSSIBLE)
```

异步用法：

```python
import aistation as A

async with A.AsyncAiStationClient() as client:
    spec = A.WorkPlatformSpec.notebook(
        resource_group="DEV-POOL",
        image="registry.example.invalid/ml/dev:latest",
    )
    wp = (await client.workplatforms.create(spec)).unwrap()
    print((await client.workplatforms.jupyter_url(wp)).get("url"))
```

高层 async helper：

```python
import aistation as A
from aistation import aio

async with A.AsyncAiStationClient() as client:
    ctx = await aio.enumerate_form_context(client)
    groups = await aio.recommend.suggest_groups(client, card_type_contains="A100")
    print(len(ctx.images), len(groups))
```

创建类接口统一返回 `OperationResult`：

```python
import aistation as A

with A.AiStationClient() as client:
    result = client.tasks.create_and_wait(spec)
    task = result.unwrap()
    print(result.created, result.reused, result.waited, task.id)
    client.tasks.stop(task)  # 直接传 Task 对象
```

## 更多

- 示例见 [docs/examples.md](docs/examples.md)
- 性能/交互优化分析见 [docs/sdk-ux-performance-optimization.md](docs/sdk-ux-performance-optimization.md)
- 收尾记录见 [docs/cleanup-0.2.0.md](docs/cleanup-0.2.0.md)
- async 实施记录见 [docs/async-client-implementation.md](docs/async-client-implementation.md)
- License: MIT
