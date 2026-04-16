# SDK UX And Performance Optimization

## Background

`ai-station-sdk` 目前已经具备同步 / 异步两套 API，但在真实使用里仍有两类明显问题：

1. 性能问题
   - 创建资源后立刻读取详情，容易撞上服务端最终一致性窗口。
   - 高频 `list()` / `resolve()` 会重复打相同请求。
   - `workplatform.resolve()` 在“按名称查找”场景会先走一次详情接口，增加无效 RTT。
   - `workplatform` 历史数据查询路径存在重复请求。
   - 传输层只重试网络异常，不重试明显的瞬时 5xx / 网关错误。

2. 用户交互问题
   - `TaskSpec` / `WorkPlatformSpec` 过于贴近后端字段，缺少高层入口。
   - SDK 方法普遍只接收字符串 id，不能直接接收已拿到的模型对象。
   - `OperationResult` 只有布尔意义上的 `resolved`，缺少强约束提取方法。
   - 等待资源就绪的能力在 `watch` 模块里，但没有贴近 `tasks` / `workplatforms` 主 API。
   - 同步 / 异步风格虽然大体一致，但便捷入口和行为细节仍有一些割裂感。

## Optimization Goals

本轮优化目标：

1. 同步 / 异步接口能力对齐。
2. 降低创建后立即查询的失败概率。
3. 降低常见查询路径的重复请求数量。
4. 让 SDK 更偏“意图驱动”，而不是“字段拼装驱动”。
5. 保持 0.2.0 版本号不变，只做开发期重构，不维护旧参数兼容。

## Problem Analysis And Plan

### 1. Read-after-write eventual consistency

现状：

- `tasks.create()` / `aio.tasks.create()` 在 POST 成功后只做一次 `get(id)`。
- `workplatform.create()` / `create_raw()` 也是直接 `get(id)`。
- 如果服务端写入和检索索引不同步，就会抛 `NotFoundError` 或回落到低质量兜底逻辑。

优化：

- 增加内部只读重试逻辑，专门处理“刚创建完，详情暂时不可见”的短窗口。
- 先按服务端返回 id 读取，多次失败后再回退到按 name 查找。
- 同步 / 异步都使用相同的重试策略和返回语义。

验收：

- 创建后的前 1-2 次 `get()` 返回 `NotFoundError` 也能最终成功。

### 2. Task list hot-path caching

现状：

- `tasks.list(status_flag=0)` 和 `tasks.list(status_flag=3)` 是热点接口。
- `exists()` / `resolve()` / `resolve_many()` / 幂等创建都会重复扫描列表。

优化：

- 为 `status_flag=0` 和 `status_flag=3` 分别增加短 TTL 缓存。
- `create()` / `delete()` / `stop()` 后主动失效缓存。
- 提供 `refresh=True` 绕过缓存，提供 `invalidate_cache()` 主动清空。
- `client.invalidate_caches()` 与 async 对应实现纳入 task 缓存清理。

验收：

- 连续相同列表查询命中缓存。
- 修改型操作后自动失效。

### 3. WorkPlatform resolve request path

现状：

- `workplatform.resolve(query)` 会先无条件 `get(query)`。
- 当 `query` 实际上是名字时，这一步几乎必然无效。

优化：

- 先在本地候选集合里解析；仅当本地没有匹配且 `query` 看起来像 id 时，再回退详情接口。
- `search_history=True` 时复用 `list()` 已取回的 history，不再二次抓历史页。

验收：

- 名称解析不再多打一跳 detail。
- history 搜索路径不重复请求。

### 4. Transport transient failure handling

现状：

- 只有 `requests` / `httpx` 抛出的 request-level 异常会触发 retry。
- 如果服务端返回 HTML 版 502 / 503，或 JSON 版 500，当前会直接失败。

优化：

- 将常见瞬时 HTTP 状态码视为可重试传输错误：
  - `408`, `425`, `429`, `500`, `502`, `503`, `504`
- 对非 JSON 的瞬时错误页同样转成 `TransportError` 进入统一重试链路。
- 对非瞬时状态码仍保持快速失败。

验收：

- 瞬时 5xx 能重试。
- 非 JSON 502/503 不再直接报“invalid JSON response”。

### 5. Intent-first spec constructors

现状：

- 用户需要记住大量字段组合，才能写出合理的 `TaskSpec` / `WorkPlatformSpec`。

优化：

- 在 `TaskSpec` 上提供：
  - `gpu_hold()`
  - `cpu_debug()`
  - `pytorch_train()`
  - `from_existing()`
- 在 `WorkPlatformSpec` 上提供：
  - `notebook()`
  - `from_existing()`

验收：

- README / examples 可以直接展示 `TaskSpec.gpu_hold(...)` 这样的入口。

### 6. Object-friendly API inputs

现状：

- 很多接口只能接收纯字符串 id。
- 调用者明明已经拿到 `Task` / `WorkPlatform` / `ResourceGroup` / `Image` 模型，仍然要手动摘字段。

优化：

- `TaskSpec.resource_group` / `WorkPlatformSpec.resource_group` 接收 `str | ResourceGroup`
- `TaskSpec.image` / `WorkPlatformSpec.image` 接收 `str | Image`
- 任务接口支持直接传 `Task`：
  - `get`
  - `pods`
  - `read_log`
  - `stop`
  - `delete`
  - `wait_running`
  - `wait_pods`
- 开发环境接口支持直接传 `WorkPlatform`：
  - `get`
  - `delete`
  - `rebuild_template`
  - `jupyter_url`
  - `shell_url`
  - `commit_image`
  - `toggle_history_collect`
  - `wait_ready`

验收：

- 拿到实体对象后能直接继续调用后续 API，不需要手工取 id。

### 7. OperationResult ergonomics

现状：

- 调用者需要手写 `if result.entity is None: raise ...`

优化：

- 增加：
  - `require_entity()`
  - `unwrap()`
- 在实体缺失时抛出清晰的 SDK 异常。

验收：

- 创建 / 查询类结果可直接 `result.unwrap()`。

### 8. Resource-local wait helpers

现状：

- 等待能力在 `watch` 模块里，用户得自己切换命名空间。

优化：

- `tasks.wait_running()` / `tasks.wait_pods()`
- `workplatforms.wait_ready()`
- async 等价接口完全对应

验收：

- 同步 / 异步用户都可以沿着主资源 API 继续调用等待逻辑。

## Implementation Order

1. 文档定稿。
2. 增加内部引用归一化工具。
3. 扩展 `OperationResult` 与 specs 便捷构造器。
4. 改造 sync/async tasks API。
5. 改造 sync/async workplatform API。
6. 改造 transport retry。
7. 更新 README / examples。
8. 补齐测试并跑完整校验。

## Risk Control

- 不回滚工作树中的既有无关改动。
- 只在 SDK API 层做重构，不改 CLI 设计方向。
- 版本保持 `0.2.0`。
- 所有同步能力必须有对应异步实现。
