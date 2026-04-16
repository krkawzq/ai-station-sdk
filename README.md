# aistation

Unofficial Python SDK + CLI for [Westlake University AI Station](https://172.16.78.10:32206).

> ⚠️ Hack, not official. Reverse-engineered from the front-end. Use responsibly.

## 能做什么

- **查资源**：节点 / 资源组 / 镜像 / 我的任务 / dev env，带真实占用（`getUsage=1`）
- **提交任务**：TaskSpec / WorkPlatformSpec → 客户端预校验 → 服务端 dry-run → 幂等提交
- **管理生命周期**：watch 状态 / 拉日志 / 停止 / 删除
- **预设**：`gpu_hold`（占卡）/ `cpu_debug` / `pytorch_train` / `from_existing`（克隆）
- **CLI**：只读命令 + 交互式登录（含 SM2 + 验证码字符画渲染）

## 快速开始

```bash
cd ai-station-sdk
uv sync --all-extras                # 含 CLI (typer / rich / pillow)
```

### CLI 查状态

```bash
export AISTATION_ACCOUNT=zhoujingbo
export AISTATION_PASSWORD='...'

aistation login         # 交互式；触发验证码时终端直接渲染字符画
aistation status        # 一屏 dashboard
aistation gpus --free   # 有空闲卡的资源组
aistation tasks         # 我的运行中任务
```

### Python SDK 占卡

```python
import aistation as A
from aistation.watch import wait_running, wait_pods

c = A.AiStationClient.from_config()
c.ensure_auth()

spec = A.presets.gpu_hold(
    resource_group="8A100_80", cards=1, cpu=8, memory_gb=16,
    image="pytorch/pytorch:21.10-py3", hours=2,
)
task = c.tasks.create(spec)          # 自动预校验 + 服务端 dry-run + 幂等
task = wait_running(c, task.id)
pods = wait_pods(c, task.id)
print("SSH:", pods[0].external_urls[0])
# → 192.168.105.24:31063
```

详细用法见 [`docs/examples.md`](docs/examples.md)。

## 架构

```
aistation/
├── client.py              AiStationClient 主入口
├── transport/             HTTP + 认证（SM2 登录、token 缓存）
├── pagination.py          page=-1 fast path + 兼容分页
├── modeling/              dataclass 数据模型（User / Task / Pod / ...）
├── specs.py               TaskSpec / WorkPlatformSpec（用户输入契约）
├── builders/              spec → API payload 转换
├── resources.py           节点 / 资源组 API
├── images.py              镜像 API
├── tasks.py               训练任务 API
├── workplatform.py        开发环境 API（Jupyter 类）
├── presets.py             常用 TaskSpec 工厂
├── recommend.py           按条件排序的组 / 镜像推荐
├── watch.py               状态轮询助手
├── validation.py          客户端预校验
├── discovery.py           迭代式字段缺失自动补齐
├── cache.py               TTL 缓存层
├── errors.py              异常层级 + 中文 hint 字典
└── cli/                   只读 CLI（typer + rich）
```

## 文档

- [`docs/examples.md`](docs/examples.md) — **使用示例（推荐先读这个）**
- [`docs/CLI_USAGE.md`](docs/CLI_USAGE.md) — CLI 命令速查
- [`docs/CLI_DESIGN.md`](docs/CLI_DESIGN.md) — CLI 设计理念
- [`docs/CHANGES.md`](docs/CHANGES.md) — SDK 演进记录
- [`docs/SPEC.md`](docs/SPEC.md) — 实现规格（给 agent 的交付文档）

## 核心设计

- **只读 CLI + 写操作 SDK**：命令行查状态；写操作（创建 / 删除）在 Python 里做，避免命令行字段写不下
- **Skill 友好**：所有命令支持 `--json`（稳定 schema）；非 TTY 自动切 JSON；exit code 按错误类型分档
- **防呆默认开启**：`tasks.create()` 默认做客户端预校验 + 服务端预检 + 幂等检查，失败尽早暴露
- **中文错误 hint**：每个已知 errCode 配有"问题描述 + 建议动作"，`.describe()` 方法一键打印
- **官方 fast path**：分页走 `page=-1, pageSize=-1`（官方前端用的魔法值），单次请求拉全，避 `pageNum` 被服务端忽略的 bug
- **`getUsage=1`**：默认加到 `/node` 请求，才能看到真实 `acceleratorCardUsage`（不加全是 0）

## 已知限制

- role=2（普通用户）看不到别人任务；集群聚合监控接口无权限（用节点聚合替代）
- `zangzelin` / `liziqing_*` 等私有组虽能查询到空闲，但提交会被拒
- VPN 抖动时部分接口（如全量 finished task 列表）可能需 30-60s

## 对应的文档仓库

项目完整探索记录、API 逆向笔记在上层 `ai-station-helper/docs/`：
- `01-overview.md` — 架构总览
- `02-auth.md` — SM2 登录细节
- `05-task-create.md` — 任务创建 payload 规则
- `08-api-reference.md` — 全 API 清单

## License

MIT
