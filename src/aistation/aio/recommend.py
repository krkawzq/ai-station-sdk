"""Async recommendation helpers over groups and images."""
from __future__ import annotations

from ..modeling.images import Image
from ..modeling.resources import ResourceGroup
from ..recommend import _looks_private, _parse_card_memory
from .client import AsyncAiStationClient


async def suggest_groups(
    client: AsyncAiStationClient,
    *,
    card_type_contains: str | None = None,
    min_free_cards: int = 1,
    min_card_memory_gb: int | None = None,
    card_kind: str = "GPU",
    include_private: bool = False,
) -> list[ResourceGroup]:
    groups = await client.groups.list()
    needle = card_type_contains.lower() if card_type_contains else None

    def _ok(group: ResourceGroup) -> bool:
        if card_kind and group.card_kind != card_kind:
            return False
        if group.free_cards < min_free_cards:
            return False
        if needle and needle not in group.card_type.lower():
            return False
        if min_card_memory_gb is not None:
            mem = _parse_card_memory(group.card_type)
            if mem is None or mem < min_card_memory_gb:
                return False
        if not include_private and _looks_private(group.group_name):
            return False
        return True

    return sorted(
        [group for group in groups if _ok(group)],
        key=lambda group: (group.free_cards, group.total_cards),
        reverse=True,
    )


async def suggest_images(
    client: AsyncAiStationClient,
    *,
    image_type: str | None = None,
    name_contains: str | None = None,
    min_pulls: int = 0,
    prefer_public: bool = True,
    limit: int = 10,
) -> list[Image]:
    images = await client.images.list()
    needle = name_contains.lower() if name_contains else None

    def _ok(image: Image) -> bool:
        if image_type and image.image_type != image_type:
            return False
        if image.pull_count < min_pulls:
            return False
        if needle and needle not in image.full_ref.lower():
            return False
        return True

    def _score(image: Image) -> tuple[int, int]:
        public_boost = 1 if (prefer_public and image.share == 2) else 0
        return (public_boost, image.pull_count)

    ranked = sorted([image for image in images if _ok(image)], key=_score, reverse=True)
    return ranked[:limit] if limit else ranked
