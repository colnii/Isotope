"""Operator-facing diagnostics for generated QQ beta packs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...llm.provider import resolve_llm_chat_provider
from .beta_check import QQBetaCheckConfig, check_qq_beta_pack
from .character_card import CharacterCard
from .qq_state_config import dict_field, load_config, optional_stickers_from_config
from .startup_gate import QQStartupGateConfig, check_qq_startup_gate


DEFAULT_PROFILE_DIR = "../qq-profile"
DEFAULT_PROFILE_NAME = "群聊工程猫"
DEFAULT_REPLAY_REPORT = "logs/replay-report.json"
DEFAULT_REPLAY_SCENARIOS_REPORT = "logs/replay-scenarios-report.json"


@dataclass(frozen=True)
class QQBetaDiagnosticsConfig:
    pack_dir: Path

    def __post_init__(self) -> None:
        if not str(self.pack_dir).strip():
            raise ValueError("pack-dir must be a non-empty path")


def build_qq_beta_diagnostics(config: QQBetaDiagnosticsConfig) -> dict[str, Any]:
    pack_dir = config.pack_dir
    if not pack_dir.exists() or not pack_dir.is_dir():
        raise ValueError(f"beta pack directory does not exist: {pack_dir}")
    config_path = pack_dir / "config.json"
    payload = load_config(config_path)
    replay_report = pack_dir / DEFAULT_REPLAY_REPORT
    replay_scenarios_report = pack_dir / DEFAULT_REPLAY_SCENARIOS_REPORT

    checks = _build_checks(
        pack_dir=pack_dir,
        replay_report=replay_report,
        replay_scenarios_report=replay_scenarios_report,
    )
    summary = _build_summary(
        payload,
        pack_dir=pack_dir,
        replay_report=replay_report,
        replay_scenarios_report=replay_scenarios_report,
    )
    ready = (
        bool(replay_report.exists())
        and bool(replay_scenarios_report.exists())
        and all(bool(check.get("ok")) for check in checks)
    )
    next_steps = _next_steps(summary=summary, checks=checks)
    return {
        "status": "ready" if ready else "needs_action",
        "pack_dir": str(pack_dir),
        "operator_cwd": str(pack_dir),
        "config_path": str(config_path),
        "summary": summary,
        "checks": checks,
        "next_steps": next_steps,
    }


def _build_checks(
    *,
    pack_dir: Path,
    replay_report: Path,
    replay_scenarios_report: Path,
) -> list[dict[str, Any]]:
    if replay_report.exists():
        result = check_qq_startup_gate(
            QQStartupGateConfig(
                pack_dir=pack_dir,
                replay_report=replay_report,
                replay_scenarios_report=replay_scenarios_report,
            )
        )
        return list(result.checks)
    checks: list[dict[str, Any]] = []
    try:
        beta_result = check_qq_beta_pack(QQBetaCheckConfig(pack_dir=pack_dir))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        checks.append({"name": "beta_pack", "ok": False, "error": str(exc)})
    else:
        checks.append(
            {
                "name": "beta_pack",
                "ok": beta_result.ok,
                "checks": list(beta_result.checks),
            }
        )
    checks.append(
        {
            "name": "replay_report",
            "ok": False,
            "errors": [f"replay report does not exist: {replay_report}"],
        }
    )
    checks.append(
        {
            "name": "replay_scenarios_report",
            "ok": False,
            "errors": [
                f"replay scenarios report does not exist: {replay_scenarios_report}"
            ],
        }
    )
    return checks


def _build_summary(
    payload: dict[str, Any],
    *,
    pack_dir: Path,
    replay_report: Path,
    replay_scenarios_report: Path,
) -> dict[str, Any]:
    group_policy = dict_field(payload, "group_policy", default={})
    allowed_groups = _string_list(group_policy.get("allowed_groups", []))
    operator_user_ids = _string_list(group_policy.get("operator_user_ids", []))
    runtime = dict_field(payload, "runtime", default={})
    reply_provider = str(runtime.get("reply_provider", "deterministic"))
    return {
        "platform": str(payload.get("platform", "qq")),
        "adapter": str(payload.get("adapter", "onebot")),
        "allowed_groups": allowed_groups,
        "operator_user_ids": operator_user_ids,
        "bot_user_id": str(payload.get("bot_user_id", "")),
        "websocket_url": str(payload.get("websocket_url", "")),
        "default_dry_run": bool(group_policy.get("default_dry_run", True)),
        "reply_provider": reply_provider,
        "llm": _llm_summary(reply_provider),
        "profile": _profile_summary(payload),
        "stickers": _sticker_summary(payload),
        "replay_report": _replay_report_summary(replay_report),
        "replay_scenarios_report": _replay_scenarios_report_summary(
            replay_scenarios_report
        ),
        "scripts": _script_summary(pack_dir),
    }


def _profile_summary(payload: dict[str, Any]) -> dict[str, Any]:
    role_card_path = payload.get("role_card_path")
    sticker_library_path = payload.get("sticker_library_path")
    applied = isinstance(role_card_path, str) and isinstance(sticker_library_path, str)
    role_name = None
    errors: list[str] = []
    if applied:
        try:
            role = CharacterCard.from_dict(
                _payload_from_config(payload, "role_card", "role_card_path")
            )
            role_name = role.identity.name
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
    return {
        "applied": applied,
        "role_card_path": role_card_path if isinstance(role_card_path, str) else None,
        "sticker_library_path": (
            sticker_library_path if isinstance(sticker_library_path, str) else None
        ),
        "role_name": role_name,
        "errors": errors,
    }


def _sticker_summary(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        library = optional_stickers_from_config(payload)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return {"entry_count": 0, "media_entry_count": 0, "errors": [str(exc)]}
    if library is None:
        return {"entry_count": 0, "media_entry_count": 0, "errors": []}
    media_entries = [
        entry
        for entry in library.entries
        if entry.media.kind == "sticker" and bool(entry.media.media_ref.strip())
    ]
    return {
        "entry_count": len(library.entries),
        "media_entry_count": len(media_entries),
        "errors": [],
    }


def _llm_summary(reply_provider: str) -> dict[str, Any]:
    if reply_provider == "deterministic":
        return {
            "required": False,
            "configured": None,
            "provider_name": None,
            "reason_code": "deterministic_reply_provider",
        }
    if reply_provider != "llm":
        return {
            "required": False,
            "configured": False,
            "provider_name": None,
            "reason_code": "invalid_reply_provider",
        }
    resolution = resolve_llm_chat_provider()
    return {
        "required": True,
        "configured": resolution.status == "configured" and resolution.provider is not None,
        "provider_name": resolution.provider_name,
        "reason_code": resolution.reason_code,
    }


def _replay_report_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "passed": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"exists": True, "path": str(path), "passed": None, "errors": [str(exc)]}
    if not isinstance(payload, dict):
        return {
            "exists": True,
            "path": str(path),
            "passed": None,
            "errors": ["replay report must contain a JSON object"],
        }
    return {
        "exists": True,
        "path": str(path),
        "passed": payload.get("passed"),
        "summary": payload.get("summary", {}),
    }


def _replay_scenarios_report_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "passed": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"exists": True, "path": str(path), "passed": None, "errors": [str(exc)]}
    if not isinstance(payload, dict):
        return {
            "exists": True,
            "path": str(path),
            "passed": None,
            "errors": ["replay scenarios report must contain a JSON object"],
        }
    return {
        "exists": True,
        "path": str(path),
        "passed": payload.get("passed"),
        "summary": payload.get("summary", {}),
    }


def _script_summary(pack_dir: Path) -> dict[str, bool]:
    return {
        name: (pack_dir / name).exists()
        for name in (
            "health.sh",
            "startup-check.sh",
            "dry-run.sh",
            "review-dry-run.sh",
            "send-run.sh",
        )
    }


def _next_steps(
    *,
    summary: dict[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    group = _first(summary.get("allowed_groups")) or "<group_id>"
    bot_user_id = str(summary.get("bot_user_id") or "<bot_qq>")
    profile = summary.get("profile", {})
    if isinstance(profile, dict) and not profile.get("applied"):
        return [
            {
                "name": "create_profile",
                "command": (
                    "isotope-social qq init-profile "
                    f"--output-dir {DEFAULT_PROFILE_DIR} --group {group} "
                    f"--name {DEFAULT_PROFILE_NAME} --json"
                ),
                "reason": "role-card and sticker-library files are not applied",
            },
            {
                "name": "apply_profile",
                "command": (
                    "isotope-social qq apply-profile "
                    f"--pack-dir . --profile-dir {DEFAULT_PROFILE_DIR} --json"
                ),
                "reason": "config.json must point to editable profile assets",
            },
            _rerun_step(),
        ]
    replay_report = summary.get("replay_report", {})
    if isinstance(replay_report, dict) and not replay_report.get("exists"):
        return [
            {
                "name": "create_replay",
                "command": (
                    "isotope-social qq init-replay --output replay.json "
                    f"--group {group} --bot-user-id {bot_user_id} --json"
                ),
                "reason": "startup readiness needs a replay report",
            },
            {
                "name": "run_replay",
                "command": (
                    "isotope-social qq replay --config-json config.json "
                    "--state-root state --replay-json replay.json "
                    f"--output {DEFAULT_REPLAY_REPORT} --json"
                ),
                "reason": "generate logs/replay-report.json before live dry-run",
            },
            _rerun_step(),
        ]
    failed_names = {str(check.get("name")) for check in checks if not check.get("ok")}
    if "llm_reply_provider" in failed_names:
        return [
            {
                "name": "fix_llm_reply_provider",
                "command": (
                    "configure the shared Isotope LLM provider or set "
                    'runtime.reply_provider = "deterministic" in config.json'
                ),
                "reason": "LLM reply mode is selected but provider config is not ready",
            },
            _rerun_step(),
        ]
    replay_scenarios_report = summary.get("replay_scenarios_report", {})
    if isinstance(replay_scenarios_report, dict) and not replay_scenarios_report.get(
        "exists"
    ):
        return [
            {
                "name": "create_replay_scenarios",
                "command": (
                    "isotope-social qq init-replay-scenarios "
                    f"--output-dir replay-scenarios --group {group} "
                    f"--bot-user-id {bot_user_id} --json"
                ),
                "reason": "startup readiness needs replay scenario files",
            },
            {
                "name": "run_replay_scenarios",
                "command": (
                    "isotope-social qq replay-scenarios --config-json config.json "
                    "--state-root state --scenario-dir replay-scenarios "
                    f"--output {DEFAULT_REPLAY_SCENARIOS_REPORT} "
                    "--reports-dir logs/replay-scenario-reports --json"
                ),
                "reason": (
                    "generate logs/replay-scenarios-report.json before live dry-run"
                ),
            },
            _rerun_step(),
        ]
    if failed_names:
        return [
            {
                "name": "fix_startup_check",
                "command": "isotope-social qq startup-check --pack-dir . "
                f"--replay-report {DEFAULT_REPLAY_REPORT} "
                f"--replay-scenarios-report {DEFAULT_REPLAY_SCENARIOS_REPORT} --json",
                "reason": "startup-check still has failed checks: "
                + ", ".join(sorted(failed_names)),
            },
            _rerun_step(),
        ]
    return [
        {
            "name": "health",
            "command": "./health.sh",
            "reason": "connect to OneBot without consuming group messages",
        },
        {
            "name": "dry_run",
            "command": "./dry-run.sh",
            "reason": "consume real events without sending messages",
        },
        {
            "name": "review_dry_run",
            "command": "./review-dry-run.sh",
            "reason": "write the operator review report before any send-enabled run",
        },
    ]


def _payload_from_config(config: dict[str, Any], inline_key: str, path_key: str) -> dict[str, Any]:
    if inline_key in config:
        value = config.get(inline_key)
        if not isinstance(value, dict):
            raise ValueError(f"{inline_key} must be a JSON object")
        return value
    path_value = config.get(path_key)
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError(f"{inline_key} or {path_key} is required")
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(str(config["_config_base"])) / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _first(value: object) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _rerun_step() -> dict[str, str]:
    return {
        "name": "rerun_diagnostics",
        "command": "isotope-social qq beta-diagnostics --pack-dir . --json",
        "reason": "confirm the beta pack checklist after the previous action",
    }
