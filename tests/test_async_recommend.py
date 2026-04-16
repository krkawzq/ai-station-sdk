from __future__ import annotations

from types import SimpleNamespace

import pytest

from aistation.aio.recommend import suggest_groups, suggest_images

from .helpers import make_group, make_image


class _DummyClient:
    def __init__(self) -> None:
        async def list_groups():
            return [
                make_group(group_name="public-a100", card_type="Synthetic-A100-80GB", total_cards=8, used_cards=2),
                make_group(group_name="private-team", card_type="Synthetic-A100-40GB", total_cards=4, used_cards=0),
                make_group(group_name="4v100", card_type="Synthetic-V100-32GB", total_cards=8, used_cards=1),
            ]

        async def list_images():
            return [
                make_image(name="registry.example.invalid/ml/pytorch", tag="latest", pull_count=100, share=2),
                make_image(name="registry.example.invalid/ml/pytorch-nightly", tag="nightly", pull_count=150, share=1),
                make_image(name="registry.example.invalid/ml/tensorflow", tag="2.15", image_type="tensorflow", pull_count=80, share=2),
            ]

        self.groups = SimpleNamespace(list=list_groups)
        self.images = SimpleNamespace(list=list_images)


@pytest.mark.asyncio
async def test_async_suggest_groups_filters_and_ranks() -> None:
    client = _DummyClient()

    groups = await suggest_groups(client, card_type_contains="A100", min_free_cards=2, min_card_memory_gb=80)

    assert [group.group_name for group in groups] == ["public-a100"]


@pytest.mark.asyncio
async def test_async_suggest_images_prefers_public_and_filters() -> None:
    client = _DummyClient()

    images = await suggest_images(client, image_type="pytorch", name_contains="pytorch", prefer_public=True, limit=2)

    assert [image.full_ref for image in images] == [
        "registry.example.invalid/ml/pytorch:latest",
        "registry.example.invalid/ml/pytorch-nightly:nightly",
    ]
