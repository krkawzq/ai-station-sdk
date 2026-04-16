# aistation

AI Station 的非官方 Python SDK 和 CLI。

> 仍然需要vpn解决内网环境

## 安装

```bash
cd ai-station-sdk
uv sync --extra cli
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

client = A.AiStationClient.from_config()
client.ensure_auth()

for group in client.groups.list():
    print(group.group_name, group.free_cards)
```

## 更多

- 示例见 [docs/examples.md](docs/examples.md)
- License: MIT
