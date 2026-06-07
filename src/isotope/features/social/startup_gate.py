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
    replay_scenarios_report: Path | None = None
    min_sticker_candidates: int = 1

    def __post_init__(self) -> None:
        if not str(self.pack_dir).strip():
            raise ValueError("pack-dir must be a non-empty path")
        if not str(self.replay_report).strip():
            raise ValueError("replay-report must be a non-empty path")
        if self.replay_scenarios_report is not None and not str(
            self.replay_scenarios_report
        ).strip():
            raise ValueError("replay-scenarios-report must be a non-empty path")
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
    replay_scenarios_report: Path | None
    checks: tuple[dict[str, Any], ...]

    @property
    def ready(self) -> bool:
        return all(bool(check.get("ok")) for check in self.checks)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "pack_dir": str(self.pack_dir),
            "replay_report": str(self.replay_report),
            "replay_scenarios_report": (
                str(self.replay_scenarios_report)
                if self.replay_scenarios_report is not None
                else None
            ),
            "ready": self.ready,
            "checks": list(self.checks),
        }


def check_qq_startup_gate(config: QQStartupGateConfig) -> QQStartupGateResult:
    pack_dir = config.pack_dir
    config_path = pack_dir / "config.json"
    config_payload = _load_json_object(config_path) if config_path.exists() else {}
    replay_report_payload = _optional_replay_report_payload(config.replay_report)
    checks: tuple[dict[str, Any], ...] = (
        _check_beta_pack(pack_dir),
        _check_profile_assets(config_payload, base_dir=pack_dir),
        _check_sticker_assets(
            config_payload,
            base_dir=pack_dir,
            replay_report_payload=replay_report_payload,
        ),
        _check_llm_reply_provider(config_payload),
        _check_replay_report(
            config.replay_report,
            min_sticker_candidates=config.min_sticker_candidates,
        ),
    )
    if config.replay_scenarios_report is not None:
        checks += (_check_replay_scenarios_report(config.replay_scenarios_report),)
    return QQStartupGateResult(
        pack_dir=pack_dir,
        replay_report=config.replay_report,
        replay_scenarios_report=config.replay_scenarios_report,
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


def _check_sticker_assets(
    payload: dict[str, Any],
    *,
    base_dir: Path,
    replay_report_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    sticker_library_path = _asset_path(payload, "sticker_library_path", base_dir=base_dir)
    if sticker_library_path is None:
        return {
            "name": "sticker_assets",
            "ok": False,
            "entry_count": 0,
            "media_entry_count": 0,
            "sticker_ids": [],
            "required_sticker_ids": [],
            "missing_required_sticker_ids": [],
            "missing_local_paths": [],
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
            "sticker_ids": [],
            "required_sticker_ids": [],
            "missing_required_sticker_ids": [],
            "missing_local_paths": [],
            "errors": [str(exc)],
        }
    sticker_ids = [entry.sticker_id for entry in library.entries]
    media_entries = [
        entry
        for entry in library.entries
        if entry.media.kind == "sticker" and bool(entry.media.media_ref.strip())
    ]
    errors = []
    missing_local_paths = _missing_local_paths(
        library=library,
        sticker_library_path=sticker_library_path,
    )
    required_sticker_ids = _required_sticker_ids(replay_report_payload)
    missing_required_sticker_ids = [
        sticker_id for sticker_id in required_sticker_ids if sticker_id not in sticker_ids
    ]
    if not media_entries:
        errors.append("sticker-library must contain at least one sticker media entry")
    for local_path in missing_local_paths:
        errors.append(f"sticker local_path does not exist: {local_path}")
    if missing_required_sticker_ids:
        errors.append(
            "replay required sticker ids missing from sticker-library: "
            + ", ".join(missing_required_sticker_ids)
        )
    return {
        "name": "sticker_assets",
        "ok": not errors,
        "entry_count": len(library.entries),
        "media_entry_count": len(media_entries),
        "sticker_ids": sticker_ids,
        "required_sticker_ids": required_sticker_ids,
        "missing_required_sticker_ids": missing_required_sticker_ids,
        "missing_local_paths": missing_local_paths,
        "errors": errors,
    }


def _check_llm_reply_provider(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = payload.get("runtime", {})
    if not isinstance(runtime, dict):
        return {
            "name": "llm_reply_provider",
            "ok": False,
            "reply_provider": None,
            "participation_provider": None,
            "errors": ["runtime must be a JSON object"],
        }
    reply_provider = runtime.get("reply_provider", "deterministic")
    participation_provider = runtime.get("participation_provider", "rules")
    if reply_provider not in {"deterministic", "llm"}:
        return {
            "name": "llm_reply_provider",
            "ok": False,
            "reply_provider": reply_provider,
            "participation_provider": participation_provider,
            "errors": ["runtime.reply_provider must be deterministic or llm"],
        }
    if participation_provider not in {"rules", "llm"}:
        return {
            "name": "llm_reply_provider",
            "ok": False,
            "reply_provider": reply_provider,
            "participation_provider": participation_provider,
            "errors": ["runtime.participation_provider must be rules or llm"],
        }
    if reply_provider == "deterministic" and participation_provider == "rules":
        return {
            "name": "llm_reply_provider",
            "ok": True,
            "reply_provider": "deterministic",
            "participation_provider": "rules",
            "reason_code": "deterministic_reply_provider",
            "errors": [],
        }
    resolution = resolve_llm_chat_provider()
    return {
        "name": "llm_reply_provider",
        "ok": resolution.status == "configured" and resolution.provider is not None,
        "reply_provider": reply_provider,
        "participation_provider": participation_provider,
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


def _check_replay_scenarios_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "name": "replay_scenarios_report",
            "ok": False,
            "errors": [f"replay scenarios report does not exist: {path}"],
        }
    try:
        payload = _load_json_object(path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return {"name": "replay_scenarios_report", "ok": False, "errors": [str(exc)]}
    summary = payload.get("summary", {})
    scenarios = payload.get("scenarios", [])
    errors: list[str] = []
    if payload.get("kind") != "qq_replay_scenarios_report":
        errors.append("kind must be qq_replay_scenarios_report")
    if payload.get("passed") is not True:
        errors.append("replay scenarios report passed must be true")
    scenario_count = _int_field(summary, "scenario_count")
    passed_count = _int_field(summary, "passed_count")
    failed_count = _int_field(summary, "failed_count")
    if scenario_count <= 0:
        errors.append("summary.scenario_count must be greater than 0")
    if failed_count != 0:
        errors.append("summary.failed_count must be 0")
    if passed_count != scenario_count:
        errors.append("summary.passed_count must equal summary.scenario_count")
    failed_scenarios = _failed_replay_scenarios(scenarios)
    if failed_scenarios:
        errors.append("all replay scenarios must pass")
    return {
        "name": "replay_scenarios_report",
        "ok": not errors,
        "passed": payload.get("passed"),
        "scenario_count": scenario_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "failed_scenarios": failed_scenarios,
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


def _optional_replay_report_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return _load_json_object(path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None


def _missing_local_paths(
    *,
    library: StickerLibrary,
    sticker_library_path: Path,
) -> list[str]:
    missing: list[str] = []
    for entry in library.entries:
        local_path = entry.media.local_path
        if not local_path:
            continue
        path = Path(local_path)
        if not path.is_absolute():
            path = sticker_library_path.parent / path
        if not path.exists() or not path.is_file():
            missing.append(local_path)
    return missing


def _required_sticker_ids(replay_report_payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(replay_report_payload, dict):
        return []
    expectations = replay_report_payload.get("expectations", [])
    if not isinstance(expectations, list):
        return []
    result: list[str] = []
    for item in expectations:
        if not isinstance(item, dict) or item.get("name") != "require_sticker_candidate_ids":
            continue
        expected = item.get("expected", [])
        if not isinstance(expected, list):
            continue
        for sticker_id in expected:
            if isinstance(sticker_id, str) and sticker_id.strip():
                normalized = sticker_id.strip()
                if normalized not in result:
                    result.append(normalized)
    return result


def _failed_replay_scenarios(scenarios: object) -> list[str]:
    if not isinstance(scenarios, list):
        return []
    result: list[str] = []
    for item in scenarios:
        if not isinstance(item, dict) or item.get("passed") is True:
            continue
        scenario_id = item.get("scenario_id")
        if isinstance(scenario_id, str) and scenario_id.strip():
            result.append(scenario_id.strip())
    return result


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
