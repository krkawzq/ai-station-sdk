"""Client-side TaskSpec validation.

Checks that a :class:`TaskSpec` satisfies the server's known rules BEFORE
any network call. Catches common mistakes (bad name regex, memory < shm*2,
mount path == account name, etc.) without hitting the server.

Never raises for cases that are merely suboptimal — only for cases where the
server would certainly reject the submission.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ._refs import coerce_image_ref
from .errors import SpecValidationError

if TYPE_CHECKING:
    from .modeling.common import User
    from .modeling.images import Image
    from .specs import TaskSpec


# ---------- server-imposed patterns (reverse-engineered) ----------
NAME_RE = re.compile(r"^[A-Za-z0-9]+$")
SWITCH_TYPE_RE = re.compile(r"^(ether|ib|roce|ETHER|IB|ROCE)$")
IMAGE_TYPES = frozenset(
    {"pytorch", "tensorflow", "caffe", "mxnet", "paddlepaddle", "mpi", "other", "serving"}
)
DISTRIBUTED_MODES = frozenset({"node", "mpi", "ps_worker", "master_worker", "server_worker"})
CARD_KINDS = frozenset({"GPU", "CPU"})

MEMORY_MIN_GB = 0
MEMORY_MAX_GB = 500
CPU_MAX_CORES = 128  # empirical upper bound; actual max depends on node


def validate_spec(spec: "TaskSpec", user: "User | None" = None) -> None:
    """Validate a TaskSpec against known server rules.

    Raises :class:`SpecValidationError` on the first rule violation. Safe to
    call repeatedly; pure (no side effects).
    """
    _check_name(spec.name)
    _check_image(spec.image)
    _check_switch_type(spec.switch_type)
    _check_card_kind(spec.card_kind)
    _check_image_type(spec.image_type)
    _check_distributed(spec.distributed)
    _check_memory(spec.memory_gb, spec.shm_size)
    _check_cpu(spec.cpu)
    _check_cards(spec.cards)
    _check_mount_path(spec.mount_path, user)


def _check_name(name: str) -> None:
    if not name:
        raise SpecValidationError("name is required", field_name="name")
    if not NAME_RE.fullmatch(name):
        raise SpecValidationError(
            f"name={name!r} must be alphanumeric only (no -, _, spaces, or non-ASCII)",
            field_name="name",
        )


def _check_image(image: str | Image) -> None:
    resolved_image = coerce_image_ref(image)
    if not resolved_image:
        raise SpecValidationError("image is required", field_name="image")
    if ":" not in resolved_image.rsplit("/", 1)[-1]:
        raise SpecValidationError(
            f"image={resolved_image!r} must include a tag (e.g. 'pytorch/pytorch:21.10-py3')",
            field_name="image",
        )


def _check_switch_type(switch_type: str) -> None:
    if switch_type and not SWITCH_TYPE_RE.fullmatch(switch_type):
        raise SpecValidationError(
            f"switch_type={switch_type!r} must match server regex ^(ether|ib|roce|...)$ "
            "— note: use 'ether' not 'eth'",
            field_name="switch_type",
        )


def _check_card_kind(card_kind: str) -> None:
    if card_kind and card_kind not in CARD_KINDS:
        raise SpecValidationError(
            f"card_kind={card_kind!r} must be one of {sorted(CARD_KINDS)}",
            field_name="card_kind",
        )


def _check_image_type(image_type: str) -> None:
    if image_type and image_type not in IMAGE_TYPES:
        raise SpecValidationError(
            f"image_type={image_type!r} must be one of {sorted(IMAGE_TYPES)}",
            field_name="image_type",
        )


def _check_distributed(distributed: str) -> None:
    if distributed not in DISTRIBUTED_MODES:
        raise SpecValidationError(
            f"distributed={distributed!r} must be one of {sorted(DISTRIBUTED_MODES)}",
            field_name="distributed",
        )


def _check_memory(memory_gb: int, shm_size: int) -> None:
    if memory_gb < MEMORY_MIN_GB or memory_gb > MEMORY_MAX_GB:
        raise SpecValidationError(
            f"memory_gb={memory_gb} must be in [{MEMORY_MIN_GB}, {MEMORY_MAX_GB}]",
            field_name="memory_gb",
        )
    # Server rule: memory >= shm_size * 2  (only applies when shm_size > 0)
    if memory_gb > 0 and shm_size > 0 and memory_gb < shm_size * 2:
        raise SpecValidationError(
            f"memory_gb={memory_gb} must be >= shm_size * 2 ({shm_size * 2})",
            field_name="memory_gb",
        )


def _check_cpu(cpu: int) -> None:
    if cpu < 0:
        raise SpecValidationError(f"cpu={cpu} must be >= 0", field_name="cpu")
    if cpu > CPU_MAX_CORES:
        raise SpecValidationError(
            f"cpu={cpu} exceeds conservative upper bound {CPU_MAX_CORES} (node-dependent)",
            field_name="cpu",
        )


def _check_cards(cards: int) -> None:
    if cards < 0:
        raise SpecValidationError(f"cards={cards} must be >= 0", field_name="cards")


def _check_mount_path(mount_path: str, user: "User | None") -> None:
    if not mount_path or user is None:
        return
    if mount_path.rstrip("/") == f"/{user.account}":
        raise SpecValidationError(
            f"mount_path={mount_path!r} cannot equal /{user.account} (account name). "
            f"Use a subpath like /{user.account}/work",
            field_name="mount_path",
        )


def validate_group_card_compatibility(
    group_card_kind: str,
    spec_card_kind: str,
    spec_cards: int,
) -> None:
    """Check that spec's card count matches the resource group's type.

    Separate from :func:`validate_spec` because it needs a resolved
    :class:`ResourceGroup` object (client network call).
    """
    if group_card_kind == "GPU" and spec_cards < 1:
        raise SpecValidationError(
            "GPU resource group requires cards >= 1",
            field_name="cards",
        )
    if group_card_kind == "CPU" and spec_cards != 0:
        raise SpecValidationError(
            "CPU resource group requires cards == 0",
            field_name="cards",
        )
    if group_card_kind == "GPU" and spec_card_kind == "CPU":
        raise SpecValidationError(
            "GPU resource group with card_kind=CPU is inconsistent — use card_kind='GPU'",
            field_name="card_kind",
        )
