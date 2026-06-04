"""Editable QQ profile packs for role cards and sticker libraries."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .character_card import CharacterCard
from .stickers import StickerLibrary


ROLE_CARD_FILENAME = "role-card.json"
STICKER_LIBRARY_FILENAME = "sticker-library.json"
PROFILE_README_FILENAME = "README.md"
PROFILE_CONFIG_BACKUP_FILENAME = "config.before-profile.json"


@dataclass(frozen=True)
class QQProfilePackConfig:
    output_dir: Path
    group_id: str
    role_name: str
    force: bool = False

    def __post_init__(self) -> None:
        _required_text(str(self.output_dir), "output_dir")
        _required_text(self.group_id, "group")
        _required_text(self.role_name, "name")


@dataclass(frozen=True)
class QQProfilePackResult:
    output_dir: Path
    role_card_path: Path
    sticker_library_path: Path
    readme_path: Path

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "role_card_path": str(self.role_card_path),
            "sticker_library_path": str(self.sticker_library_path),
            "readme_path": str(self.readme_path),
        }


@dataclass(frozen=True)
class QQProfileApplyConfig:
    pack_dir: Path
    profile_dir: Path

    def __post_init__(self) -> None:
        _required_text(str(self.pack_dir), "pack_dir")
        _required_text(str(self.profile_dir), "profile_dir")


@dataclass(frozen=True)
class QQProfileApplyResult:
    config_path: Path
    backup_path: Path
    role_card_path: Path
    sticker_library_path: Path

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "config_path": str(self.config_path),
            "backup_path": str(self.backup_path),
            "role_card_path": str(self.role_card_path),
            "sticker_library_path": str(self.sticker_library_path),
        }


def create_qq_profile_pack(config: QQProfilePackConfig) -> QQProfilePackResult:
    output_dir = config.output_dir
    if output_dir.exists() and any(output_dir.iterdir()) and not config.force:
        raise ValueError(f"profile pack already exists: {output_dir}; pass --force to overwrite")
    output_dir.mkdir(parents=True, exist_ok=True)

    role_payload = _role_card_payload(config)
    sticker_payload = _sticker_library_payload(config)
    CharacterCard.from_dict(role_payload)
    StickerLibrary.from_dict(sticker_payload)

    role_card_path = output_dir / ROLE_CARD_FILENAME
    sticker_library_path = output_dir / STICKER_LIBRARY_FILENAME
    readme_path = output_dir / PROFILE_README_FILENAME
    _write_json(role_card_path, role_payload)
    _write_json(sticker_library_path, sticker_payload)
    readme_path.write_text(_readme(config), encoding="utf-8")
    return QQProfilePackResult(
        output_dir=output_dir,
        role_card_path=role_card_path,
        sticker_library_path=sticker_library_path,
        readme_path=readme_path,
    )


def apply_qq_profile_pack(config: QQProfileApplyConfig) -> QQProfileApplyResult:
    pack_dir = config.pack_dir
    profile_dir = config.profile_dir
    config_path = pack_dir / "config.json"
    role_card_path = profile_dir / ROLE_CARD_FILENAME
    sticker_library_path = profile_dir / STICKER_LIBRARY_FILENAME
    backup_path = pack_dir / PROFILE_CONFIG_BACKUP_FILENAME

    if not config_path.exists():
        raise ValueError(f"beta pack config does not exist: {config_path}")
    role_payload = _read_json(role_card_path)
    sticker_payload = _read_json(sticker_library_path)
    CharacterCard.from_dict(role_payload)
    StickerLibrary.from_dict(sticker_payload)

    beta_config = _read_json(config_path)
    if not backup_path.exists():
        _write_json(backup_path, beta_config)
    beta_config.pop("role_card", None)
    beta_config.pop("sticker_library", None)
    beta_config["role_card_path"] = _relative_path(role_card_path, start=pack_dir)
    beta_config["sticker_library_path"] = _relative_path(sticker_library_path, start=pack_dir)
    _write_json(config_path, beta_config)
    return QQProfileApplyResult(
        config_path=config_path,
        backup_path=backup_path,
        role_card_path=role_card_path,
        sticker_library_path=sticker_library_path,
    )


def _role_card_payload(config: QQProfilePackConfig) -> dict[str, Any]:
    return {
        "schema_version": "isotope.character_card_plus.v1",
        "identity": {
            "name": config.role_name,
            "aliases": ["bot", config.role_name],
            "description": "长期待在 QQ 群里的工程型群友，不抢话，先看上下文。",
            "creator_notes": "按酒馆角色卡思路维护身份、说话方式、行为边界和记忆规则。",
        },
        "voice": {
            "speaking_style": "像熟悉项目的群友，短句优先，先判断是否该插话。",
            "tone": "direct",
            "vocabulary": ["上下文", "复盘", "测试", "表情包", "先别急"],
            "example_messages": [
                "我先看下前面在聊什么，再决定要不要接话。",
                "这轮像是配置问题，先把日志和复现步骤对齐。",
                "收到，这个我记成群规，不当成一次性玩笑。",
            ],
            "forbidden_style": "不要像客服，不要刷屏，不要每句话都解释自己是 AI。",
        },
        "social_behavior": {
            "talkativeness": 0.4,
            "interruption_style": "only_when_useful",
            "mention_policy": "always_consider",
            "lurk_policy": "watch_and_wait",
            "disagreement_style": "explain_reason",
            "relationship_policy": "remember_stable_preferences",
        },
        "stickers": {
            "enabled": True,
            "favorite_packs": ["qq-default"],
            "style_tags": ["friendly", "helpful", "dry"],
            "emotion_map": {
                "ack": ["ok"],
                "positive": ["thumbs-up", "ship"],
                "confused": ["question"],
                "calm": ["calm"],
            },
            "use_frequency": 0.25,
            "allow_sticker_only_reply": True,
            "avoid_tags": ["spam", "刷屏"],
        },
        "tools": {
            "allowed_capabilities": [],
            "tool_use_style": "ask_operator_before_new_capability",
            "after_tool_result_behavior": "answer_briefly",
        },
        "memory": {
            "remember": ["群规", "稳定偏好", "长期项目背景"],
            "do_not_remember": ["一次性玩笑", "临时情绪"],
            "review_policy": "operator_review_before_memory_writes",
        },
        "groups": {
            "overrides": {
                config.group_id: {
                    "social_behavior": {"talkativeness": 0.4},
                    "stickers": {"enabled": True},
                }
            }
        },
    }


def _sticker_library_payload(config: QQProfilePackConfig) -> dict[str, Any]:
    entries = [
        ("ack-ok", "ok", "收到、确认、不需要展开时使用", ["ok", "ack", "friendly"]),
        ("ship-it", "ship", "结果不错、可以推进时使用", ["ship", "thumbs-up", "positive"]),
        ("need-context", "question", "信息不够、需要补上下文时使用", ["question", "confused", "helpful"]),
        ("calm-down", "calm", "争论升温、需要按步骤排查时使用", ["calm", "debug", "dry"]),
    ]
    return {
        "entries": [
            {
                "sticker_id": sticker_id,
                "pack_id": "qq-default",
                "media": {
                    "media_ref": f"qq-image://profile/{media_id}",
                    "kind": "sticker",
                    "source": "editable_profile",
                },
                "tags": tags,
                "meaning": meaning,
                "allowed_groups": [config.group_id],
                "source": "qq_profile_pack",
            }
            for sticker_id, media_id, meaning, tags in entries
        ]
    }


def _readme(config: QQProfilePackConfig) -> str:
    return f"""# QQ Profile Pack

Role: `{config.role_name}`
Group: `{config.group_id}`

Edit `role-card.json` for identity, voice, group behavior, memory policy, and
tool style. Edit `sticker-library.json` for sticker IDs, media refs, tags, and
meanings.

Apply this profile to a generated beta pack:

```bash
isotope-social qq apply-profile --pack-dir ../qq-beta --profile-dir . --json
isotope-social qq beta-check --pack-dir ../qq-beta --json
```

Replace `qq-image://profile/...` media refs with real sendable QQ image refs
before enabling sticker-heavy behavior in a real group.

The generated beta pack defaults to `runtime.reply_provider = "deterministic"`.
To use LLM-generated text replies, edit the beta pack `config.json` and set
`runtime.reply_provider = "llm"` after the shared Isotope LLM provider is
configured. Run `startup-check.sh` before live dry-run; it blocks missing LLM
configuration.
"""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _relative_path(path: Path, *, start: Path) -> str:
    return os.path.relpath(path, start=start)


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
