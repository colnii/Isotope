"""Startup readiness checks for generated QQ beta packs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...llm.provider import resolve_llm_chat_provider
from .beta_check import QQBetaCheckConfig, check_qq_beta_pack
from .character_card import CharacterCard
from .stickers import StickerLibrary


@dataclass(frozen=True)
class QQStartupGateConfig:
    pack_dir: Path
    replay_report: Path
    min_sticker_candidates: int = 1

    def __post_init__(self) -> None:
        if not str(self.pack_dir).strip():
            raise ValueError("pack-dir must be a non-empty path")
        if not str(self.replay_report).strip():
            raise ValueError("replay-report must be a non-empty path")
        if (
            isinstance(self.min_sticker_candidates, bool)
            or not isinstance(self.min_sticker_candidates, int)
        ):
            raise ValueError("min-sticker-candidates must be an integer")
        if self.min_sticker_candidates < 0:
            raise ValueError("min-sticker-candidates must be 0 or greater")


@dataclass(frozen=True)
class QQStartupGateResult:
    pack_dir: Path
    replay_report: Path
    checks: tuple[dict[str, Any], ...]

    @property
    def ready(self) -> bool:
        return all(bool(check.get("ok")) for check in self.checks)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "pack_dir": str(self.pack_dir),
            "replay_report": str(self.replay_report),
            "ready": self.ready,
            "checks": list(self.checks),
        }


def check_qq_startup_gate(config: QQStartupGateConfig) -> QQStartupGateResult:
    pack_dir = config.pack_dir
    config_path = pack_dir / "config.json"
    config_payload = _load_json_object(config_path) if config_path.exists() else {}
    checks = (
        _check_beta_pack(pack_dir),
        _check_profile_assets(config_payload, base_dir=pack_dir),
        _check_sticker_assets(config_payload, base_dir=pack_dir),
        _check_llm_reply_provider(config_payload),
        _check_replay_report(
            config.replay_report,
            min_sticker_candidates=config.min_sticker_candidates,
        ),
    )
    return QQStartupGateResult(
        pack_dir=pack_dir,
        replay_report=config.replay_report,
        checks=checks,
    )


def _check_beta_pack(pack_dir: Path) -> dict[str, Any]:
    try:
        result = check_qq_beta_pack(QQBetaCheckConfig(pack_dir=pack_dir))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return {"name": "beta_pack", "ok": False, "error": str(exc)}
    return {
        "name": "beta_pack",
        "ok": result.ok,
        "checks": list(result.checks),
    }


def _check_profile_assets(payload: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    role_card_path = _asset_path(payload, "role_card_path", base_dir=base_dir)
    sticker_library_path = _asset_path(payload, "sticker_library_path", base_dir=base_dir)
    if role_card_path is None:
        errors.append("role_card_path is required; run qq apply-profile first")
    else:
        try:
            CharacterCard.from_dict(_load_json_object(role_card_path))
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"role_card_path:{exc}")
    if sticker_library_path is None:
        errors.append("sticker_library_path is required; run qq apply-profile first")
    else:
        try:
            StickerLibrary.from_dict(_load_json_object(sticker_library_path))
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"sticker_library_path:{exc}")
    return {
        "name": "profile_assets",
        "ok": not errors,
        "role_card_path": str(role_card_path) if role_card_path is not None else None,
        "sticker_library_path": (
            str(sticker_library_path) if sticker_library_path is not None else None
        ),
        "errors": errors,
    }


def _check_sticker_assets(payload: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    sticker_library_path = _asset_path(payload, "sticker_library_path", base_dir=base_dir)
    if sticker_library_path is None:
        return {
            "name": "sticker_assets",
            "ok": False,
            "entry_count": 0,
            "media_entry_count": 0,
            "errors": ["sticker_library_path is required; run qq apply-profile first"],
        }
    try:
        library = StickerLibrary.from_dict(_load_json_object(sticker_library_path))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return {
            "name": "sticker_assets",
            "ok": False,
            "entry_count": 0,
            "media_entry_count": 0,
            "errors": [str(exc)],
        }
    media_entries = [
        entry
        for entry in library.entries
        if entry.media.kind == "sticker" and bool(entry.media.media_ref.strip())
    ]
    errors = []
    if not media_entries:
        errors.append("sticker-library must contain at least one sticker media entry")
    return {
        "name": "sticker_assets",
        "ok": not errors,
        "entry_count": len(library.entries),
        "media_entry_count": len(media_entries),
        "errors": errors,
    }


def _check_llm_reply_provider(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = payload.get("runtime", {})
    if not isinstance(runtime, dict):
        return {
            "name": "llm_reply_provider",
            "ok": False,
            "reply_provider": None,
            "errors": ["runtime must be a JSON object"],
        }
    reply_provider = runtime.get("reply_provider", "deterministic")
    if reply_provider == "deterministic":
        return {
            "name": "llm_reply_provider",
            "ok": True,
            "reply_provider": "deterministic",
            "reason_code": "deterministic_reply_provider",
            "errors": [],
        }
    if reply_provider != "llm":
        return {
            "name": "llm_reply_provider",
            "ok": False,
            "reply_provider": reply_provider,
            "errors": ["runtime.reply_provider must be deterministic or llm"],
        }
    resolution = resolve_llm_chat_provider()
    return {
        "name": "llm_reply_provider",
        "ok": resolution.status == "configured" and resolution.provider is not None,
        "reply_provider": "llm",
        "provider_name": resolution.provider_name,
        "reason_code": resolution.reason_code,
        "errors": [] if resolution.status == "configured" else [resolution.reason_code],
    }


def _check_replay_report(path: Path, *, min_sticker_candidates: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "name": "replay_report",
            "ok": False,
            "errors": [f"replay report does not exist: {path}"],
        }
    try:
        payload = _load_json_object(path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return {"name": "replay_report", "ok": False, "errors": [str(exc)]}
    summary = payload.get("summary", {})
    errors: list[str] = []
    if payload.get("kind") != "qq_replay_report":
        errors.append("kind must be qq_replay_report")
    if payload.get("passed") is not True:
        errors.append("replay report passed must be true")
    if payload.get("dry_run") is not True:
        errors.append("replay report dry_run must be true")
    sticker_candidates = _int_field(summary, "sticker_candidate_count")
    sent_group_messages = _int_field(summary, "sent_group_message_count")
    if sticker_candidates < min_sticker_candidates:
        errors.append(
            "summary.sticker_candidate_count must be at least "
            f"{min_sticker_candidates}"
        )
    if sent_group_messages != 0:
        errors.append("summary.sent_group_message_count must be 0")
    return {
        "name": "replay_report",
        "ok": not errors,
        "passed": payload.get("passed"),
        "dry_run": payload.get("dry_run"),
        "sticker_candidate_count": sticker_candidates,
        "sent_group_message_count": sent_group_messages,
        "errors": errors,
    }


def _asset_path(payload: dict[str, Any], key: str, *, base_dir: Path) -> Path | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _int_field(payload: object, key: str) -> int:
    if not isinstance(payload, dict):
        return 0
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value
