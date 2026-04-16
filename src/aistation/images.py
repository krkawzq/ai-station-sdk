from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from .cache import TTLCache
from .modeling.images import Image, ImageType_

if TYPE_CHECKING:
    from .client import AiStationClient


class ImagesAPI:
    """Image catalog with 5-minute TTL (images change rarely)."""

    def __init__(self, client: AiStationClient) -> None:
        self._c = client
        self._cache: TTLCache[list[Image]] = TTLCache(ttl=300.0)
        self._types_cache: TTLCache[list[ImageType_]] = TTLCache(ttl=300.0)

    def list(
        self,
        *,
        share: int | None = None,
        image_type: str | None = None,
        refresh: bool = False,
    ) -> list[Image]:
        """List images. Cached 5 min; pass ``refresh=True`` to bypass."""
        images = self._cache.get() if not refresh else None
        if images is None:
            images = [
                Image.from_api(item)
                for item in self._c.list_all("/api/iresource/v1/images/all")
            ]
            self._cache.set(images)
        if share is not None:
            images = [image for image in images if image.share == share]
        if image_type:
            images = [image for image in images if image.image_type == image_type]
        return images

    def invalidate_cache(self) -> None:
        self._cache.invalidate()
        self._types_cache.invalidate()

    def types(self) -> builtins.list[ImageType_]:
        cached = self._types_cache.get()
        if cached is not None:
            return cached
        data = self._c.get("/api/iresource/v1/image-type")
        if not isinstance(data, list):
            return []
        types = [ImageType_.from_api(item) for item in data if isinstance(item, dict)]
        self._types_cache.set(types)
        return types

    def resolve(self, image_ref: str) -> Image:
        query = image_ref.strip()
        images = self.list()

        exact = [image for image in images if image.full_ref == query]
        if len(exact) == 1:
            return exact[0]

        short_exact = [image for image in images if self._short_ref(image) == query]
        if len(short_exact) == 1:
            return short_exact[0]

        suffix = [image for image in images if image.full_ref.endswith(query) or self._short_ref(image).endswith(query)]
        if len(suffix) == 1:
            return suffix[0]

        contains = [image for image in images if query in image.full_ref or query in self._short_ref(image)]
        if len(contains) == 1:
            return contains[0]

        if not exact and not short_exact and not suffix and not contains:
            raise ValueError(f"image not found: {image_ref!r}")
        raise ValueError(f"ambiguous image reference: {image_ref!r}")

    def check(self, image_name: str, image_tag: str) -> dict[str, Any]:
        data = self._c.post(
            "/api/iresource/v1/images/check",
            json={"imageName": image_name, "imageTag": image_tag},
        )
        if not isinstance(data, dict):
            raise ValueError("unexpected image check payload")
        return data

    def import_external(
        self,
        *,
        image_name: str,
        image_tag: str,
        image_type: str,
        share: int = 1,
        comment: str = "",
        alias_name: str = "",
        username: str = "",
        password: str = "",
    ) -> dict[str, Any]:
        body = {
            "imageName": image_name,
            "imageTag": image_tag,
            "imageType": image_type,
            "share": share,
            "imageComment": comment,
            "aliasName": alias_name,
            "username": username,
            "password": password,
        }
        data = self._c.post("/api/iresource/v1/images/outside-import", json=body)
        if not isinstance(data, dict):
            raise ValueError("unexpected image import payload")
        self.invalidate_cache()
        return data

    def progress(self, task_id: str) -> dict[str, Any]:
        data = self._c.get("/api/iresource/v1/images/progress", params={"id": task_id})
        if not isinstance(data, dict):
            raise ValueError("unexpected image progress payload")
        return data

    @staticmethod
    def _short_ref(image: Image) -> str:
        ref = image.full_ref
        parts = ref.split("/", 1)
        return parts[1] if len(parts) == 2 else ref
