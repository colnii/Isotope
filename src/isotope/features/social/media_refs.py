"""Stable media references for social messages and replies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .messages import (
    _omit_empty,
    _optional_nullable_string,
    _required_string_value,
)


SUPPORTED_MEDIA_REF_KINDS = {"sticker", "image", "qq_face", "file", "voice", "video"}


@dataclass(frozen=True)
class MediaRef:
    media_ref: str
    kind: str
    source: str
    checksum: str | None = None
    local_path: str | None = None
    platform_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required_string_value(self.media_ref, "media_ref")
        if self.kind not in SUPPORTED_MEDIA_REF_KINDS:
            raise ValueError("media ref kind is not supported")
        _required_string_value(self.source, "media source")
        _optional_nullable_string(self.checksum, "media checksum")
        _optional_nullable_string(self.local_path, "media local_path")
        if not isinstance(self.platform_data, dict):
            raise ValueError("media platform_data must be a dict")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaRef":
        if not isinstance(data, dict):
            raise ValueError("media must be a dict")
        return cls(
            media_ref=_required_string_value(data.get("media_ref"), "media_ref"),
            kind=_required_string_value(data.get("kind"), "media kind"),
            source=_required_string_value(data.get("source"), "media source"),
            checksum=_optional_nullable_string(data.get("checksum"), "media checksum")
            if "checksum" in data
            else None,
            local_path=_optional_nullable_string(data.get("local_path"), "media local_path")
            if "local_path" in data
            else None,
            platform_data=_dict_from_mapping(data, "platform_data", "media platform_data"),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "media_ref": self.media_ref,
                "kind": self.kind,
                "source": self.source,
                "checksum": self.checksum,
                "local_path": self.local_path,
                "platform_data": dict(self.platform_data),
            }
        )


def _dict_from_mapping(
    data: dict[str, Any],
    key: str,
    field_name: str,
) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return dict(value)
