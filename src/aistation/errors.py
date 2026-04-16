"""SDK exception hierarchy with human-friendly hints.

Every :class:`AiStationError` instance exposes a ``.hint()`` method that maps
the server-side error code to actionable guidance in Chinese. This lets a CLI
or Skill show a next-step to the user without hard-coding the mapping.
"""
from __future__ import annotations


# ---------- server errCode → (short description, suggested action) ----------
_ERROR_GUIDE: dict[str, tuple[str, str]] = {
    # Auth
    "IBASE_IAUTH_TOKEN_NOT_FOUND": (
        "Token 不存在或已过期",
        "调用 client.login() 重新登录",
    ),
    "IBASE_NO_PERMISSION": (
        "权限不足",
        "当前账号（role=2 普通用户）无法访问该接口，或该资源组对你不可见",
    ),
    # Task creation — validation
    "IRESOURCE_NOT_NULL_ILLEGAL": (
        "必填字段缺失",
        "服务器错误消息中会指明字段名，按名字补齐",
    ),
    "IRESOURCE_FORMAT_ILLEGAL": (
        "字段格式不合规",
        "错误消息里包含服务器正则（如 ^ib|ether|roce$），按正则选合法值",
    ),
    "IRESOURCE_FRAMEWORK_ILLEGAL": (
        "imageType/type 字段不合规",
        "只能是 pytorch/tensorflow/caffe/mxnet/paddlepaddle/mpi/other/serving",
    ),
    "IRESOURCE_VALID_JOB_NAME": (
        "任务名不合法",
        "name 只允许大小写字母和数字，禁连字符/下划线/中文",
    ),
    # Task creation — resource constraints
    "IRESOURCE_COMMON_RES_GROUP_NOT_FOUND": (
        "资源组不存在",
        "检查 resource_group 名称或 UUID，用 client.groups.list() 列出可见组",
    ),
    "IRESOURCE_COMMON_RES_GROUP_CAN_NOT_BE_USED": (
        "当前用户无权使用该资源组",
        "换一个你有权限的组（有现役任务的组通常可用）",
    ),
    "IRESOURCE_GPU_NUM_OUT_OF_RESOURCE_GROUP_LIMIT": (
        "GPU 卡数与组要求不符",
        "GPU 组 cards 必须 ≥ 1；CPU 组 cards 必须 = 0",
    ),
    "IRESOURCE_CPU_NUM_OUT_OF_RANGE": (
        "CPU 核数越界",
        "查一下目标节点的 cpu 上限（约 ≤ 128），减小 cpu 参数",
    ),
    "IRESOURCE_MEMORY_NUM_OUT_OF_RANGE": (
        "内存容量越界",
        "memory_gb 必须在 0-500 之间",
    ),
    "IRESOURCE_MEMORY_LT_SHM_SIZE_ERROR": (
        "内存不足以容纳共享内存",
        "memory_gb 必须 ≥ shm_size × 2",
    ),
    # Image
    "IRESOURCE_IMAGE_INFO_NOT_EXISTS": (
        "镜像在数据库中不存在",
        "确认 image 字段是完整 ref（registry/name:tag），或用 client.images.list() 查可用镜像",
    ),
    "IRESOURCE_TRAIN_IMAGE_NOT_IN_HARBOR": (
        "镜像不在 Harbor 仓库中",
        "镜像 tag 不存在，重新拉取或选其他 tag",
    ),
    # Mount / exec
    "IRESOURCE_DUPLICATED_ACCOUNT_MOUNT_PATH": (
        "挂载路径不能等于用户名",
        "mount_path 用子路径如 /{account}/workdir，或留空由 SDK 推断",
    ),
    "IRESOURCE_EXECUTION_DIRECTORY_ERROR": (
        "执行路径错误",
        "exec_dir 设为空串 \"\" 最稳，非空必须是真实存在的路径",
    ),
    # Generic / catch-all
    "IRESOURCE_CHECK_JOB_PARAM_FAILED": (
        "参数检查失败",
        "payload 里某必填字段缺失或非法；打开 verbose 查看详细原因",
    ),
    "IRESOURCE_CREATE_TRAIN_JOB_FAILED": (
        "创建任务失败",
        "可能组合了多个不兼容选项；对比一个已知可用任务的 raw 字段",
    ),
    "IRESOURCE_STOP_TRAIN_JOB_FAILED": (
        "停止任务失败",
        "任务可能已经结束；用 tasks.delete() 软删除历史记录",
    ),
    "IRESOURCE_QUERY_USER_QUOTA_FAILED": (
        "查询用户配额失败",
        "role=2 通常无权访问该接口，skill 层可忽略此错误",
    ),
    "SDK_SPEC_VALIDATION": (
        "客户端预校验未通过",
        "查看 .field_name 属性，按提示修正 TaskSpec",
    ),
    "SDK_CLI_NOT_LOGGED_IN": (
        "未登录，无 token 缓存",
        "先运行 `aistation login` 登录",
    ),
    "SDK_CLI_MISSING_ACCOUNT": (
        "缺少账号",
        "用 `-u ACCOUNT` 或设 AISTATION_ACCOUNT 环境变量",
    ),
    "SDK_CLI_MISSING_PASSWORD": (
        "缺少密码",
        "用 `-p PASSWORD` / 设 AISTATION_PASSWORD / 或 `-p -` 从 stdin 读",
    ),
    "IBASE_IAUTH_ACCOUNT_OR_PASSWORD_ERROR": (
        "账号或密码错误",
        "检查输入；多次失败后服务器会触发验证码（下条错误码）",
    ),
    "IBASE_IAUTH_CAPTCHA_EMPTY": (
        "需要验证码（多次密码错误触发）",
        "CLI 会自动拉取验证码图像并提示输入，按 'r' 可刷新",
    ),
    "IBASE_IAUTH_CAPTCHA_ERROR": (
        "验证码错误",
        "重新输入；CLI 的 login 会自动再次拉取新图",
    ),
    "IBASE_IAUTH_CAPTCHA_EXPIRED": (
        "验证码已过期",
        "按 'r' 刷新后重输",
    ),
    "SDK_CLI_CAPTCHA_ABANDONED": (
        "验证码多次刷新仍未输入",
        "确认网络通后重试，或去 UI 先成功登录一次重置计数",
    ),
    "SDK_REAUTH_DISABLED": (
        "当前调用不会自动重新登录",
        "显式调用 client.login()，或把 reauth_policy 改成 if_possible",
    ),
    "SDK_MAX_PAGES_EXCEEDED": (
        "分页超过调用方设置的最大页数限制",
        "增大 max_pages，或传 None 取消限制后重试",
    ),
    "SDK_RESULT_UNRESOLVED": (
        "操作已完成，但 SDK 没能解析出实体对象",
        "调用 result.raw / result.payload 检查返回值，或显式再 get()/resolve() 一次",
    ),
    "SDK_INVALID_REFERENCE": (
        "传入的资源引用为空",
        "传合法的 id / 名称，或传包含有效 id 的模型对象",
    ),
    "SDK_NOT_FOUND": (
        "未找到匹配资源",
        "检查传入的 id / 名称，或先调用 list()/resolve_many() 看候选项",
    ),
    "SDK_AMBIGUOUS_MATCH": (
        "匹配到多个候选资源",
        "传更精确的 id / 名称，或先调用 resolve_many() 查看候选项",
    ),
}


class AiStationError(RuntimeError):
    """Base class for all SDK-originated errors."""

    def __init__(
        self,
        message: str,
        *,
        err_code: str | None = None,
        err_message: str | None = None,
        path: str | None = None,
    ) -> None:
        self.err_code = err_code
        self.err_message = err_message
        self.path = path
        super().__init__(message)

    def hint(self) -> tuple[str, str] | None:
        """Return ``(short_description, suggested_action)`` or ``None`` if the
        error code is not in the known guide.
        """
        if self.err_code and self.err_code in _ERROR_GUIDE:
            return _ERROR_GUIDE[self.err_code]
        return None

    def describe(self) -> str:
        """Produce a multi-line explanation suitable for a CLI / user-facing log."""
        lines = [
            f"[{self.err_code or 'unknown'}] {self.err_message or str(self)}",
        ]
        if self.path:
            lines.append(f"  path: {self.path}")
        hint = self.hint()
        if hint:
            desc, action = hint
            lines.append(f"  → {desc}")
            lines.append(f"  → 建议：{action}")
        return "\n".join(lines)


class TransportError(AiStationError):
    """Network / TLS / timeout / DNS failure."""


class AuthError(AiStationError):
    """Login or token-related failures."""


class InvalidCredentials(AuthError):
    """Account or password is invalid."""


class TokenExpired(AuthError):
    """Token missing or expired."""


class NotFoundError(AiStationError):
    """Requested resource was not found."""

    def __init__(self, resource_type: str, query: str) -> None:
        self.resource_type = resource_type
        self.query = query
        super().__init__(
            f"{resource_type} not found: {query!r}",
            err_code="SDK_NOT_FOUND",
            err_message=f"{resource_type} not found: {query}",
            path=None,
        )


class AmbiguousMatchError(AiStationError):
    """Reference matched more than one resource."""

    def __init__(self, resource_type: str, query: str, *, matches: list[str]) -> None:
        self.resource_type = resource_type
        self.query = query
        self.matches = matches
        message = f"ambiguous {resource_type} reference: {query!r}"
        if matches:
            message = f"{message} -> {', '.join(matches)}"
        super().__init__(
            message,
            err_code="SDK_AMBIGUOUS_MATCH",
            err_message=message,
            path=None,
        )


class PermissionDenied(AiStationError):
    """Current role cannot access the endpoint."""


class ValidationError(AiStationError):
    """Server rejected input parameters."""

    def __init__(
        self,
        message: str,
        *,
        field_name: str | None = None,
        err_code: str | None = None,
        err_message: str | None = None,
        path: str | None = None,
    ) -> None:
        self.field_name = field_name
        super().__init__(message, err_code=err_code, err_message=err_message, path=path)


class ResourceError(AiStationError):
    """Quota / scheduling / resource business error."""


class SpecValidationError(ValidationError):
    """Client-side TaskSpec validation failed before any network call."""

    def __init__(self, message: str, *, field_name: str | None = None) -> None:
        super().__init__(
            message,
            field_name=field_name,
            err_code="SDK_SPEC_VALIDATION",
            err_message=message,
            path=None,
        )


def lookup_error_guide(err_code: str) -> tuple[str, str] | None:
    """Public lookup helper for arbitrary error codes."""
    return _ERROR_GUIDE.get(err_code)
