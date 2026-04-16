"""Recommendation helpers over groups and images.

Given a loose intent like "I need 2 A100 cards", return ranked candidates.
Uses only data already fetched via the client's cached APIs — no extra
network calls are issued by these functions directly.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .modeling.images import Image
from .modeling.resources import ResourceGroup

if TYPE_CHECKING:
    from .client import AiStationClient


def suggest_groups(
    client: "AiStationClient",
    *,
    card_type_contains: str | None = None,
    min_free_cards: int = 1,
    min_card_memory_gb: int | None = None,
    card_kind: str = "GPU",
    include_private: bool = False,
) -> list[ResourceGroup]:
    """Return groups matching the criteria, sorted by free capacity (desc).

    ``card_type_contains`` is a case-insensitive substring match (e.g. "A100"
    matches "NVIDIA-A100-SXM4-80GB"). ``min_card_memory_gb`` filters on per-card
    memory parsed out of the card_type string when possible.

    Private groups (name contains "private" / "VC" / matches usernames) are
    excluded by default because submissions to them usually fail with
    ``GROUP_CAN_NOT_BE_USED``.
    """
    groups = client.groups.list()
    needle = card_type_contains.lower() if card_type_contains else None

    def _ok(g: ResourceGroup) -> bool:
        if card_kind and g.card_kind != card_kind:
            return False
        if g.free_cards < min_free_cards:
            return False
        if needle and needle not in g.card_type.lower():
            return False
        if min_card_memory_gb is not None:
            mem = _parse_card_memory(g.card_type)
            if mem is None or mem < min_card_memory_gb:
                return False
        if not include_private and _looks_private(g.group_name):
            return False
        return True

    return sorted(
        [g for g in groups if _ok(g)],
        key=lambda g: (g.free_cards, g.total_cards),
        reverse=True,
    )


def suggest_images(
    client: "AiStationClient",
    *,
    image_type: str | None = None,
    name_contains: str | None = None,
    min_pulls: int = 0,
    prefer_public: bool = True,
    limit: int = 10,
) -> list[Image]:
    """Return images sorted by popularity (pull_count desc).

    - ``image_type``: filter by pytorch / tensorflow / ...
    - ``name_contains``: substring (case-insensitive) on image name+tag
    - ``prefer_public``: when True, public images (share=2) rank ahead of private
    """
    images = client.images.list()
    needle = name_contains.lower() if name_contains else None

    def _ok(im: Image) -> bool:
        if image_type and im.image_type != image_type:
            return False
        if im.pull_count < min_pulls:
            return False
        if needle:
            ref = im.full_ref.lower()
            if needle not in ref:
                return False
        return True

    def _score(im: Image) -> tuple[int, int]:
        public_boost = 1 if (prefer_public and im.share == 2) else 0
        return (public_boost, im.pull_count)

    ranked = sorted([i for i in images if _ok(i)], key=_score, reverse=True)
    return ranked[:limit] if limit else ranked


# ---------- helpers ----------

def _parse_card_memory(card_type: str) -> int | None:
    """Extract per-card memory in GB from strings like 'NVIDIA-A100-SXM4-80GB'."""
    import re
    m = re.search(r"(\d+)\s*GB", card_type, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _looks_private(name: str) -> bool:
    """Heuristic: group names like 'liziqing_private', 'zangzelin', '4V100'
    are often ACL-restricted. Use with care; prefer explicit allow-list."""
    lowered = name.lower()
    if "private" in lowered:
        return True
    # Groups known to be ACL-restricted from empirical testing
    # (we can't verify without attempting a submission; this is conservative)
    restricted = {"4v100"}
    return lowered in restricted
