from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._coerce import as_int


@dataclass
class Image:
    id: str
    name: str
    tag: str
    image_type: str
    share: int
    size_bytes: int
    pull_count: int
    owner: str
    make_type: int
    logo_id: str | None
    create_time: str
    update_time: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def full_ref(self) -> str:
        return f"{self.name}:{self.tag}" if self.tag else self.name

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        logo_id = d.get("logoId")
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("imageName", "")),
            tag=str(d.get("imageTag", "")),
            image_type=str(d.get("imageType", "")),
            share=as_int(d.get("share"), 1),
            size_bytes=as_int(d.get("size")),
            pull_count=as_int(d.get("pullCount")),
            owner=str(d.get("userName", "")),
            make_type=as_int(d.get("makeType")),
            logo_id=str(logo_id) if logo_id else None,
            create_time=str(d.get("createTime", "")),
            update_time=str(d.get("updateTime", "")),
            raw=d,
        )


@dataclass
class ImageType_:
    id: str
    name: str
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Self:
        return cls(id=str(d.get("id", "")), name=str(d.get("name", "")), raw=d)
