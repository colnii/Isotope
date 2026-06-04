"""State and config helpers for QQ social commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .audit_log import SocialAuditEntry, SocialAuditLog
from .character_card import CharacterCard
from .config import SocialGroupPolicy, SocialOperationsConfig
from .lorebook import Lorebook, LorebookEntry
from .operations import SocialOperationsController
from .stickers import StickerLibrary


STATE_FILENAME = "social-qq-state.json"


class StoredQQState:
    def __init__(
        self,
        *,
        paused_groups: tuple[str, ...],
        audit_entries: tuple[dict[str, Any], ...],
    ):
        self.paused_groups = paused_groups
        self.audit_entries = audit_entries


def load_state(state_root: Path) -> StoredQQState:
    path = state_path(state_root)
    if not path.exists():
        return StoredQQState(paused_groups=(), audit_entries=())
    payload = read_json_file(path)
    return StoredQQState(
        paused_groups=tuple(str(item) for item in payload.get("paused_groups", [])),
        audit_entries=tuple(dict(item) for item in payload.get("audit_entries", [])),
    )


def save_state(state_root: Path, operations: SocialOperationsController) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    health = operations.health_check()
    payload = {
        "paused_groups": list(health["paused_groups"]),
        "audit_entries": [
            entry.to_public_dict()
            for entry in operations.audit_log.entries
        ],
    }
    write_json_file(state_path(state_root), payload)


def state_path(state_root: Path) -> Path:
    return state_root / STATE_FILENAME


def operations_from_config(
    config: dict[str, Any],
    *,
    state: StoredQQState,
) -> SocialOperationsController:
    group_policy = dict_field(config, "group_policy", default={})
    paused = string_tuple_from_list(group_policy.get("paused_groups", [])) + state.paused_groups
    audit_log = SocialAuditLog(
        _entries=[
            SocialAuditEntry(
                kind=str(entry["kind"]),
                group_id=str(entry["group_id"]),
                payload=dict(entry["payload"]),
                timestamp=str(entry["timestamp"]),
            )
            for entry in state.audit_entries
        ]
    )
    return SocialOperationsController(
        config=SocialOperationsConfig(
            group_policy=SocialGroupPolicy(
                allowed_groups=string_tuple_from_list(group_policy.get("allowed_groups", [])),
                blocked_groups=string_tuple_from_list(group_policy.get("blocked_groups", [])),
                operator_user_ids=string_tuple_from_list(
                    group_policy.get("operator_user_ids", [])
                ),
                paused_groups=tuple(dict.fromkeys(paused)),
                default_dry_run=bool(group_policy.get("default_dry_run", True)),
            )
        ),
        audit_log=audit_log,
    )


def load_config(path: Path) -> dict[str, Any]:
    payload = read_json_file(path)
    payload["_config_base"] = str(path.parent)
    return payload


def character_card_from_config(config: dict[str, Any]) -> CharacterCard:
    return CharacterCard.from_dict(payload_from_config(config, "role_card", "role_card_path"))


def optional_lorebook_from_config(config: dict[str, Any]) -> Lorebook | None:
    if "lorebook" not in config and "lorebook_path" not in config:
        return None
    payload = payload_from_config(config, "lorebook", "lorebook_path")
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("lorebook.entries must be a list")
    return Lorebook(
        entries=tuple(
            LorebookEntry(
                entry_id=str(item["entry_id"]),
                title=str(item["title"]),
                content=str(item["content"]),
                keywords=string_tuple_from_list(item.get("keywords", [])),
                regex=string_tuple_from_list(item.get("regex", [])),
                users=string_tuple_from_list(item.get("users", [])),
                message_part_kinds=string_tuple_from_list(item.get("message_part_kinds", [])),
                priority=int(item.get("priority", 0)),
                position=str(item.get("position", "after_recent_context")),
                expires_at=item.get("expires_at"),
            )
            for item in entries
        )
    )


def optional_stickers_from_config(config: dict[str, Any]) -> StickerLibrary | None:
    if "sticker_library" not in config and "sticker_library_path" not in config:
        return None
    return StickerLibrary.from_dict(
        payload_from_config(config, "sticker_library", "sticker_library_path")
    )


def payload_from_config(config: dict[str, Any], inline_key: str, path_key: str) -> dict[str, Any]:
    if inline_key in config:
        return dict_field(config, inline_key)
    path_value = config_string(config, path_key)
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(config_string(config, "_config_base")) / path
    return read_json_file(path)


def read_json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def dict_field(
    config: dict[str, Any],
    key: str,
    *,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = config.get(key, default)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return value


def config_string(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def string_value(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def string_tuple_from_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("expected a JSON array of strings")
    return tuple(str(item) for item in value)


def ratio(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be between 0 and 1")
    result = float(value)
    if result < 0 or result > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return result


def bool_value(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a bool")
    return value
