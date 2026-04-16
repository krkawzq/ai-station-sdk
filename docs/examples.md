# `aistation` 使用示例

端到端的实战示例：从登录到"占卡成功，拿到 SSH 入口"。

目录：
- [0. 安装与初始化](#0-安装与初始化)
- [1. 登录（首次 / 有缓存 / 验证码）](#1-登录首次--有缓存--验证码)
- [2. 资源查询](#2-资源查询)
- [3. 提交训练任务](#3-提交训练任务)
- [4. 等任务 Running + 拿 SSH / Jupyter 入口](#4-等任务-running--拿-ssh--jupyter-入口)
- [5. 开发环境（Jupyter 类）](#5-开发环境jupyter-类)
- [6. 克隆已有任务 / 开发环境](#6-克隆已有任务--开发环境)
- [7. Discovery：让服务器告诉你缺什么字段](#7-discovery让服务器告诉你缺什么字段)
- [8. 自动抢卡脚本](#8-自动抢卡脚本)
- [9. CLI 速查](#9-cli-速查)
- [10. 错误处理](#10-错误处理)

---

## 0. 安装与初始化

```bash
cd ai-station-sdk
uv sync --all-extras          # 含可选 Pillow 验证码渲染
```

验证：
```bash
python -c "import aistation; print(aistation.__version__)"
aistation --help
```

SDK 和 CLI 共用 `~/.config/aistation/auth.json` 和 `~/.config/aistation/config.json`（首次登录自动创建，0600 权限）。

---

## 1. 登录（首次 / 有缓存 / 验证码）

### 方式 A：Python 显式登录

```python
import aistation as A

client = A.AiStationClient()
user = client.login(account="{USER}", password="XXX")
print(f"{user.account} role={user.role_type} group={user.group_id[:8]}")
# → {USER} role=2 group=087e233e
# token 已自动缓存到 auth.json，后续进程直接 AiStationClient() 即可复用
```

### 方式 B：从缓存恢复（最常见）

```python
import aistation as A

client = A.AiStationClient()  # 自动加载本地 auth/config；有 token 就复用，stale token 会按配置自动刷新
```

### 方式 C：控制自动认证策略

```python
import aistation as A

client = A.AiStationClient(auth_mode=A.AuthMode.TOKEN_ONLY)        # 只恢复本地 token
manual = A.AiStationClient(auth_mode=A.AuthMode.MANUAL)            # 完全手动
eager = A.AiStationClient(auth_mode=A.AuthMode.LOGIN_IF_POSSIBLE)  # 只要能登就提前刷新
strict = A.AiStationClient(reauth_policy=A.ReauthPolicy.NEVER)     # 请求遇到过期 token 时不自动重登

print(client.auth_status())
```

### 方式 D：配合上下文管理

```python
import aistation as A

with A.AiStationClient() as client:
    print(client.groups.list())
```

### 方式 F：Async client

```python
import aistation as A

async with A.AsyncAiStationClient() as client:
    print(client.auth_status())
    groups = await client.groups.list()
    print(groups[0].group_name if groups else "no-groups")
```

### 方式 E：CLI（更友好，含交互式验证码）

```bash
export AISTATION_ACCOUNT={USER}
export AISTATION_PASSWORD='XXX'
aistation login
# ✓ Logged in as {USER} (role=2)

# 若服务器触发验证码：
# ▸ Captcha required (saved: /tmp/aistation-captcha.png)
# [彩色 unicode 半块字符画，肉眼可辨识]
# Enter captcha (or 'r' to refresh): 9B2
```

### 验证码处理（Python 手动）

```python
from aistation.errors import AiStationError
import aistation as A

client = A.AiStationClient()
try:
    client.login("{USER}", "XXX")
except AiStationError as e:
    if e.err_code == "IBASE_IAUTH_CAPTCHA_EMPTY":
        b64_png = client.fetch_captcha()        # 拉新验证码 (base64 PNG)
        code = input("captcha: ")
        client.login("{USER}", "XXX", captcha=code)
```

---

## 2. 资源查询

### 看空闲资源组

```python
import aistation as A
c = A.AiStationClient()

for g in c.groups.list():
    if g.free_cards > 0:
        print(f"{g.group_name:<22} {g.card_type:<28} free={g.free_cards}/{g.total_cards}")
# 8A100_80_dev           NVIDIA-A800-SXM4-80GB         free=2/16
# 4V100_towmode          Tesla-V100-SXM2-32GB          free=2/20
```

> ⚠️ 看到 `free>0` **不代表你能提交** 
> 用过一次成功的组，或从 `tasks.list()` 里看到自己有任务的组，通常就能用。

### 按资源组看节点明细

```python
nodes = c.nodes.list(group_id=c.groups.resolve_id("8A100_80"))
for n in nodes:
    print(f"{n.node_name}  {n.cards_used}/{n.cards_total}  cpu={n.cpu_used}/{n.cpu}  status={n.status}")
```

### 查镜像

```python
popular = A.recommend.suggest_images(c, image_type="pytorch", limit=5)
for im in popular:
    print(f"{im.full_ref:<70} pulls={im.pull_count}")
```

### 一次性拉全量表单数据（适合 Skill 初始化）

```python
ctx = A.enumerate_form_context(c)
print(f"{len(ctx.resource_groups)} groups, {len(ctx.images)} images, {len(ctx.task_types)} task types")
print(f"missing: {ctx.missing}")   # role=2 无权限的 endpoint 会记录在这里
```

---

## 3. 提交训练任务

### 3a. 用 preset（推荐）

```python
import aistation as A
c = A.AiStationClient()

spec = A.TaskSpec.gpu_hold(
    resource_group="8A100_80",
    cards=1, cpu=8, memory_gb=16,
    image="pytorch/pytorch:21.10-py3",
    hours=2,                      # 2 小时后自动结束；None = sleep infinity
)
result = c.tasks.create(spec)
task = result.unwrap()
# create() 默认开启 validate + precheck + idempotent：
#   - 客户端预校验（name 正则 / memory / mount 等）
#   - 服务器 dry-run（/train/check-resources）
#   - 幂等：同名已存在直接返回已有任务
print(f"✓ created={result.created} reused={result.reused} id={task.id}")
```

### 3b. 手写完整 spec

```python
spec = A.TaskSpec(
    name="mytrain",                 # 只允许字母数字！
    resource_group="8A100_80",
    image="pytorch/pytorch:21.10-py3",
    command="bash /{USER}/run.sh",
    cards=2, cpu=16, memory_gb=32,
    shm_size=4,
    ports=[19810, 22],
    env={"CUDA_VISIBLE_DEVICES": "0,1"},
    switch_type="ib",
    card_kind="GPU",
)
task = c.tasks.create(spec).entity
```

### 3c. 只看 payload 不提交（调试）

```python
payload = c.tasks.create(spec, dry_run=True).payload
import json
print(json.dumps(payload, indent=2, ensure_ascii=False))
```

### 3d. 只校验不提交（服务器端 dry-run）

```python
result = c.tasks.check_resources(spec)   # POST /train/check-resources
print(result.action, result.raw)         # result.raw 为服务端返回的校验结果
```

---

## 4. 等任务 Running + 拿 SSH / Jupyter 入口

### 流式监听状态变化

```python
from aistation.watch import watch_task

for state in watch_task(c, task.id, until={"Running", "Succeeded", "Failed"}):
    print(f"[{state.status:<10}] node={state.node_name or '-'}")
```

### 一步到位：等到 Running 并拿端口映射

```python
from aistation.watch import wait_running, wait_pods

task = wait_running(c, task.id, timeout=300)
pods = wait_pods(c, task.id)

for p in pods:
    print(f"pod {p.pod_name_changed} on {p.node_ip}")
    for url in p.external_urls:
        print(f"  → {url}")           # e.g. 192.168.105.24:31063
```

### 4b. 直接把 Task 对象继续传给 API

```python
task = c.tasks.create_and_wait(spec).unwrap()
pods = c.tasks.wait_pods(task)      # 不需要再手动 task.id
log = c.tasks.read_log(task)
stopped = c.tasks.stop(task)
print(len(pods), len(log), stopped.target_id)
```

### async 版等待任务 Running

```python
import aistation as A
from aistation import aio

async with A.AsyncAiStationClient() as c:
    result = await c.tasks.create(spec)
    task = result.entity
    if task is not None:
        running = await aio.watch.wait_running(c, task.id, timeout=300)
        pods = await aio.watch.wait_pods(c, task.id)
        print(running.status, pods[0].external_urls if pods else [])
```

### 读日志

```python
log = c.tasks.read_log(task.id)
print(log[-2000:])                    # 末尾 2KB
```

### 停止 / 删除

```python
stopped = c.tasks.stop(task.id)
deleted = c.tasks.delete(task.id)
batch = c.tasks.delete(["id1", "id2", "id3"])

print(stopped.action, stopped.target_id)
print(deleted.action, deleted.target_ids)
print(batch.raw)
```

---

## 5. 开发环境（Jupyter 类）

### 列可用组（必须 `groupLabel=develop` 标签）

```python
for g in c.workplatforms.list_groups():
    print(f"{g.group_name}  free={g.total_cards - g.used_cards}/{g.total_cards}")
```

### 创建 CPU-only dev env

```python
spec = A.WorkPlatformSpec.notebook(
    name="mynotebook",
    resource_group="4V100",
    image="192.168.108.1:5000/pytorch/pytorch:21.10-py3",
    cpu=2,
    memory_gb=4,
)
result = c.workplatforms.create(spec, idempotent=True)
wp = result.unwrap()
print(f"created={result.created} reused={result.reused} wpId={wp.wp_id}")
```

### 创建带 GPU 的

```python
spec = A.WorkPlatformSpec(
    name="mygpunb",
    resource_group="4V100",
    image="192.168.108.1:5000/pytorch/pytorch:21.10-py3",
    cards=1, card_kind="GPU",
    cpu=4, memory_gb=16,
    command="sleep infinity",
)
wp = c.workplatforms.create(spec).entity
```

### 查 / 删 / 拿 Jupyter URL

```python
wp = c.workplatforms.get(wp)
print(wp.wp_status, wp.group_name, wp.cpu, wp.cards)

info = c.workplatforms.jupyter_url(wp)
print(info)      # 含 URL + token

# dev env 删除同样返回 OperationResult
deleted = c.workplatforms.delete(wp)
print(deleted.action, deleted.target_id)
```

### Commit 运行中环境为镜像

```python
result = c.workplatforms.commit_image(
    wp.wp_id,
    image_name="my/myapp",
    image_tag="v1",
    pod_id=wp.raw["podId"],
    comment="调好 deepspeed",
)
print(result.action, result.raw)
```

---

## 6. 克隆已有任务 / 开发环境

### 克隆训练任务

```python
from aistation import presets

existing = c.tasks.get("GFM")                # 已知能跑的任务
spec = presets.from_existing(existing)        # 反推 TaskSpec
spec.command = "bash /{USER}/new_script.sh"
spec.name = "GFMv2"
new_task = c.tasks.create(spec).entity
```

### 克隆历史 dev env（最稳的创建方式）

```python
# rebuild_template 是服务器官方的"重建"接口 — 拿到一模一样的有效 payload
template = c.workplatforms.rebuild_template(old_wp_id)
template["wpName"] = "cloneX"
template["command"] = "sleep 7200"
template["wpType"] = "COMMON_WP"     # 模板里没这个字段，补上

wp = c.workplatforms.create_raw(template).entity
```

---

## 7. Discovery：让服务器告诉你缺什么字段

```python
from aistation import discover_payload_requirements

report = discover_payload_requirements(
    client=c,
    spec=spec,
    dry_validate=True,          # 用 check-resources，不创建真实任务
    max_iterations=10,
    verbose=True,
)

print(f"success: {report.success}")
print(f"missing fields the SDK added: {report.missing_fields}")
print(f"server-revealed constraints: {report.constraints}")
# 例：{'type': '^tensorflow|caffe|mxnet|pytorch|...|serving$'}
```

---

## 8. 自动抢卡脚本

cron 每分钟跑一次，只在命中空闲时提交：

```python
# /usr/local/bin/grab_a100.py
#!/usr/bin/env python3
import sys
import aistation as A

PREFERRED = ["8A100_80", "8A100_80_normal", "8A100_80_large"]

def main() -> int:
    c = A.AiStationClient()

    # 已经有占卡任务就跳过
    running = [t for t in c.tasks.list(status_flag=0) if t.name.startswith("autograb")]
    if running:
        print(f"already holding {len(running)} tasks, skip")
        return 0

    # 找一个有空闲 A100 的组
    groups = {g.group_name: g for g in c.groups.list()}
    target = next(
        (groups[n] for n in PREFERRED if n in groups and groups[n].free_cards > 0),
        None,
    )
    if target is None:
        print("no free A100 right now")
        return 0

    spec = A.presets.gpu_hold(
        resource_group=target.group_name,
        cards=1, cpu=8, memory_gb=16,
        image="pytorch/pytorch:21.10-py3",
        hours=4,
        name_prefix="autograb",
    )
    try:
        task = c.tasks.create(spec).entity
    except A.AiStationError as e:
        print(f"submit failed: {e.describe()}")
        return 0

    print(f"✓ grabbed {task.id if task else '-'} on {target.group_name}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

crontab：
```
* * * * * /usr/local/bin/grab_a100.py >> /var/log/grab.log 2>&1
```

---

## 9. CLI 速查

CLI 现在覆盖查询，以及 task/env 的创建、等待、停止/删除等常用操作。

```bash
# 登录
aistation login                           # 交互式（TTY 下提示账号密码）
aistation login -u {USER} -p -        # 密码从 stdin
echo $PASS | aistation login -u X -p -

# 看状态
aistation status                           # 一屏 dashboard
aistation gpus --free                      # 只有空闲的组
aistation tasks                            # 我的运行中任务
aistation task <task_id>                   # 任务详情 + pod + 端口
aistation envs                             # dev env 列表
aistation env <wp_id>

# 脚本集成（管道自动切 JSON）
aistation gpus | jq '.[] | select(.free_cards>0).group_name'
aistation -q gpus --free                   # 只打名字

# 健康检查
aistation ping
aistation whoami                           # 读本地缓存，不走网络
```

全局选项（**必须**放命令之前）：`--json` / `-q` / `-v` / `-o {table,json}` / `--timeout N`。

---

## 10. 错误处理

### 全局异常层级

```python
import aistation as A

try:
    result = c.tasks.create(spec)
except A.SpecValidationError as e:
    print(f"参数有误: {e.field_name}  {e}")
except A.PermissionDenied:
    print("role 权限不足")
except A.TokenExpired:
    c.login()
    result = c.tasks.create(spec)
except A.AiStationError as e:
    print(e.describe())
    # [IRESOURCE_GPU_NUM_OUT_OF_RESOURCE_GROUP_LIMIT] 资源组 8A100_80 只能提交加速卡个数大于等于1的任务
    #   path: /api/iresource/v1/train
    #   → GPU 卡数与组要求不符
    #   → 建议：GPU 组 cards 必须 ≥ 1；CPU 组 cards 必须 = 0
except A.TransportError:
    pass  # 网络 / 超时 — 可重试
```

### CLI 退出码

| code | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 通用错误 |
| 2 | Spec 校验失败 |
| 3 | 认证失败（需重登 / 凭据缺失） |
| 4 | 资源不存在 |
| 5 | 权限不足 |
| 6 | 网络 / 超时 |
| 7 | 服务器业务拒绝 |

### 常见错误 + 解法

| 错误码 | 原因 | 解法 |
|---|---|---|
| `SDK_CLI_NOT_LOGGED_IN` | token 缓存丢失 | `aistation login` |
| `IBASE_IAUTH_CAPTCHA_EMPTY` | 密码错多次，触发验证码 | CLI 自动处理；Python 用 `client.fetch_captcha()` |
| `IRESOURCE_VALID_JOB_NAME` | 任务名含非法字符 | 用字母数字，别用 `-` / `_` / 中文 |
| `IRESOURCE_GPU_NUM_OUT_OF_RESOURCE_GROUP_LIMIT` | GPU 组 cards=0 / CPU 组 cards>0 | 匹配组类型 |
| `IRESOURCE_MEMORY_LT_SHM_SIZE_ERROR` | memory < shm_size*2 | `memory_gb >= 2 * shm_size` |
| `IRESOURCE_DUPLICATED_ACCOUNT_MOUNT_PATH` | mount = 用户名 | 用子路径 `/{account}/work` |
| `IRESOURCE_COMMON_RES_GROUP_CAN_NOT_BE_USED` | 组你无权限用 | 换组 |

---

## 附录：完整端到端脚本

```python
#!/usr/bin/env python3
"""full_cycle.py — 占一张 A100 → 等 Running → 打印 SSH 入口。"""
import sys
import aistation as A
from aistation.watch import wait_running, wait_pods

def main() -> int:
    c = A.AiStationClient()

    spec = A.presets.gpu_hold(
        resource_group="8A100_80",
        cards=1, cpu=8, memory_gb=16,
        image="pytorch/pytorch:21.10-py3",
        hours=2,
    )
    try:
        task = c.tasks.create(spec).entity
    except A.AiStationError as e:
        print(e.describe()); return 1

    print(f"submitted id={task.id if task else '-'}; waiting for Running...")
    try:
        task = wait_running(c, task.id, timeout=600)  # type: ignore[union-attr]
    except TimeoutError:
        print("not running after 10 min (still Pending on server)")
        return 2
    if task.status != "Running":
        print(f"task ended in status {task.status}")
        print(c.tasks.read_log(task.id)[-2000:])
        return 3

    pods = wait_pods(c, task.id, timeout=60)
    print(f"✓ running on {pods[0].node_name} ({pods[0].node_ip})")
    for u in pods[0].external_urls:
        print(f"  ssh/jupyter → {u}")
    print(f"\nto stop: c.tasks.delete('{task.id}')")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

```bash
$ python full_cycle.py
submitted id=abcd...; waiting for Running...
✓ running on ai-a100v2-02 (192.168.105.12)
  ssh/jupyter → 192.168.105.12:31045
```
