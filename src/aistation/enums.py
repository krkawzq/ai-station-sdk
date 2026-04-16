from __future__ import annotations

from enum import IntEnum, StrEnum


class SwitchType(StrEnum):
    IB = "ib"
    ETH = "eth"


class CardKind(StrEnum):
    GPU = "GPU"
    CPU = "CPU"
    NONE = "-"


class PodStatus(StrEnum):
    RUNNING = "Running"
    PENDING = "Pending"
    QUEUING = "Queuing"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    OOM_KILLED = "OOMKilled"
    STOPPED = "Stopped"


class TaskStatus(StrEnum):
    RUNNING = "Running"
    PENDING = "Pending"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    TERMINATING = "Terminating"


class ImageType(StrEnum):
    PYTORCH = "pytorch"
    TENSORFLOW = "tensorflow"
    CAFFE = "caffe"
    MXNET = "mxnet"
    PADDLEPADDLE = "paddlepaddle"
    OTHER = "other"


class ShareType(IntEnum):
    PRIVATE = 1
    PUBLIC = 2


class FunctionModel(IntEnum):
    DATASET = 1
    MOUNT_DIR = 2
    LOG_DIR = 3


class MakeType(IntEnum):
    NATIVE = 0
    DOCKERFILE = 1
    COMMIT = 4


class RoleType(IntEnum):
    ADMIN = 0
    USER = 2
