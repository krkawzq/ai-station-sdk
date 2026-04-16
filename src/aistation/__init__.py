"""aistation — Unofficial Python SDK for the Westlake University AI Station.

Public surface:

- :class:`AiStationClient` — the main entrypoint
- :mod:`aistation.aio` — async surface
- :class:`TaskSpec` — user-friendly input for creating tasks
- Model dataclasses: User, Node, ResourceGroup, Image, Task, Pod, Port, JobVolume
- Exception hierarchy: AiStationError + subtypes, each with ``.hint()``
- Config / auth: ``AuthData``, ``Config``, ``load_auth``, ``save_auth``
- Helpers: ``enumerate_form_context``, ``discover_payload_requirements``
- Subpackages: :mod:`aistation.presets`, :mod:`aistation.recommend`,
  :mod:`aistation.watch`, :mod:`aistation.validation`
"""
from . import aio, presets, recommend, specs, validation, watch
from .cache import TTLCache
from .client import AiStationClient
from .config import AuthData, Config, load_auth, load_config, save_auth
from .discovery import DiscoveryReport, DiscoveryStep, discover_payload_requirements
from .enums import (
    AuthMode,
    CardKind,
    FunctionModel,
    ImageType,
    MakeType,
    PodStatus,
    ReauthPolicy,
    RoleType,
    ShareType,
    SwitchType,
    TaskStatus,
)
from .errors import (
    AiStationError,
    AmbiguousMatchError,
    AuthError,
    InvalidCredentials,
    NotFoundError,
    PermissionDenied,
    ResourceError,
    SpecValidationError,
    TokenExpired,
    TransportError,
    ValidationError,
    lookup_error_guide,
)
from .form_context import enumerate_form_context
from .modeling import (
    AuthStatus,
    FormContext,
    Image,
    JobVolume,
    Node,
    OperationResult,
    Pod,
    Port,
    ResourceGroup,
    Task,
    User,
    WorkPlatform,
)
from .specs import TaskSpec, WorkPlatformSpec

AsyncAiStationClient = aio.AsyncAiStationClient

__version__ = "0.2.0"

__all__ = [
    # main client
    "AiStationClient",
    "AsyncAiStationClient",
    "aio",
    # config / auth
    "Config",
    "AuthData",
    "load_auth",
    "save_auth",
    "load_config",
    # helpers
    "enumerate_form_context",
    "discover_payload_requirements",
    "DiscoveryReport",
    "DiscoveryStep",
    "TTLCache",
    "lookup_error_guide",
    # errors
    "AiStationError",
    "AuthError",
    "InvalidCredentials",
    "TokenExpired",
    "NotFoundError",
    "AmbiguousMatchError",
    "PermissionDenied",
    "ValidationError",
    "SpecValidationError",
    "ResourceError",
    "TransportError",
    # enums
    "AuthMode",
    "ReauthPolicy",
    "SwitchType",
    "CardKind",
    "PodStatus",
    "TaskStatus",
    "ImageType",
    "FunctionModel",
    "ShareType",
    "MakeType",
    "RoleType",
    # models
    "User",
    "Node",
    "ResourceGroup",
    "Image",
    "Task",
    "Pod",
    "Port",
    "JobVolume",
    "TaskSpec",
    "WorkPlatform",
    "WorkPlatformSpec",
    "FormContext",
    "AuthStatus",
    "OperationResult",
    # submodules
    "presets",
    "recommend",
    "specs",
    "validation",
    "watch",
]
