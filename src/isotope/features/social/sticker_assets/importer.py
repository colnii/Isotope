"""Import local QQ sticker assets into a StickerLibrary JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..stickers import StickerLibrary


MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class QQStickerImportConfig:
    source_dir: Path
    output: Path
    group_id: str
    pack_id: str

    def __post_init__(self) -> None:
        _required_text(str(self.source_dir), "source_dir")
        _required_text(str(self.output), "output")
        _required_text(self.group_id, "group")
        _required_text(self.pack_id, "pack_id")


@dataclass(frozen=True)
class QQStickerImportResult:
    output: Path
    source_dir: Path
    entry_count: int
    sticker_ids: tuple[str, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "output": str(self.output),
            "source_dir": str(self.source_dir),
            "entry_count": self.entry_count,
            "sticker_ids": list(self.sticker_ids),
        }


def import_qq_sticker_assets(config: QQStickerImportConfig) -> QQStickerImportResult:
    source_dir = config.source_dir
    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError(f"sticker source directory does not exist: {source_dir}")
    manifest = _read_json(source_dir / MANIFEST_FILENAME)
    payload = _sticker_library_payload(config=config, manifest=manifest)
    StickerLibrary.from_dict(payload)
    config.output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(config.output, payload)
    sticker_ids = tuple(entry["sticker_id"] for entry in payload["entries"])
    return QQStickerImportResult(
        output=config.output,
        source_dir=source_dir,
        entry_count=len(sticker_ids),
        sticker_ids=sticker_ids,
    )


def _sticker_library_payload(
    *,
    config: QQStickerImportConfig,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    stickers = manifest.get("stickers")
    if not isinstance(stickers, list) or not stickers:
        raise ValueError("manifest.json stickers must be a non-empty list")
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(stickers, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"manifest sticker #{index} must be a JSON object")
        sticker_id = _required_manifest_text(item.get("sticker_id"), "sticker_id")
        if sticker_id in seen:
            raise ValueError(f"duplicate sticker_id in manifest: {sticker_id}")
        seen.add(sticker_id)
        relative_file = _relative_manifest_file(item.get("file"), field_name="file")
        file_path = config.source_dir / relative_file
        if not file_path.exists() or not file_path.is_file():
            raise ValueError(f"sticker file does not exist: {file_path}")
        media_ref = _optional_text(item.get("media_ref"), "media_ref") or (
            f"file://{relative_file}"
        )
        entries.append(
            {
                "sticker_id": sticker_id,
                "pack_id": _optional_text(item.get("pack_id"), "pack_id")
                or config.pack_id,
                "media": {
                    "media_ref": media_ref,
                    "kind": "sticker",
                    "source": "local_sticker_import",
                    "local_path": str(relative_file),
                },
                "tags": _string_list(item.get("tags"), "tags"),
                "meaning": _required_manifest_text(item.get("meaning"), "meaning"),
                "allowed_groups": [config.group_id],
                "source": _optional_text(item.get("source"), "source")
                or "qq_sticker_import",
            }
        )
    return {"entries": entries}


def _relative_manifest_file(value: object, *, field_name: str) -> str:
    text = _required_manifest_text(value, field_name)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must be a relative path inside source-dir")
    return path.as_posix()


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result: list[str] = []
    for item in value:
        result.append(_required_manifest_text(item, f"{field_name} item"))
    return result


def _optional_text(value: object, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _required_manifest_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
