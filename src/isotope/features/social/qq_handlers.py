"""QQ command handlers for the social CLI."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...integrations.qq import FakeOneBotClient, OneBotAdapter, OneBotWebSocketClient
from .audit_log import SocialAuditEntry, SocialAuditLog
from .beta_check import QQBetaCheckConfig, check_qq_beta_pack
from .beta_day_report import (
    QQBetaDayReportConfig,
    build_qq_beta_day_report,
    write_qq_beta_day_report,
)
from .beta_pack import QQBetaPackConfig, create_qq_beta_pack
from .character_card import CharacterCard
from .config import SocialGroupPolicy, SocialOperationsConfig
from .dry_run_review import (
    QQDryRunReviewConfig,
    build_qq_dry_run_review,
    write_qq_dry_run_review,
)
from .lorebook import Lorebook, LorebookEntry
from .operations import SocialOperationsController
from .profile_pack import (
    QQProfileApplyConfig,
    QQProfilePackConfig,
    apply_qq_profile_pack,
    create_qq_profile_pack,
)
from .replay import (
    QQReplayTemplateConfig,
    build_replay_report,
    create_qq_replay_template,
    load_qq_replay,
    runtime_overrides,
    write_replay_report,
)
from .regression_intake import (
    QQRegressionIntakeConfig,
    build_qq_regression_intake,
    write_qq_regression_intake,
)
from .runtime import SocialRuntime, SocialRuntimeConfig
from .stickers import StickerLibrary
from .startup_gate import QQStartupGateConfig, check_qq_startup_gate


STATE_FILENAME = "social-qq-state.json"


def qq_handlers() -> dict[str, Callable[[argparse.Namespace], dict[str, Any]]]:
    return {
        "run": _handle_run,
        "live_run": _handle_live_run,
        "init_beta": _handle_init_beta,
        "init_profile": _handle_init_profile,
        "apply_profile": _handle_apply_profile,
        "init_replay": _handle_init_replay,
        "replay": _handle_replay,
        "beta_check": _handle_beta_check,
        "startup_check": _handle_startup_check,
        "review_dry_run": _handle_review_dry_run,
        "beta_day_report": _handle_beta_day_report,
        "regression_intake": _handle_regression_intake,
        "pause_resume": _handle_pause_resume,
        "inspect": _handle_inspect,
        "health": _handle_health,
        "export_log": _handle_export_log,
    }


def _handle_run(args: argparse.Namespace) -> dict[str, Any]:
    config = _load_config(Path(args.config_json))
    state = _load_state(Path(args.state_root))
    operations = _operations_from_config(config, state=state)
    client = FakeOneBotClient()
    client.queue_event(_read_json_file(Path(args.event_json)))
    runtime = _runtime_from_adapter(
        config=config,
        operations=operations,
        adapter=OneBotAdapter(client=client),
    )
    dry_run = True if args.command == "dry-run" else not bool(args.send)
    turn = runtime.process_next(dry_run=dry_run)
    _save_state(Path(args.state_root), operations)
    return {
        "status": "ok",
        "command": args.command,
        "state_file": str(_state_path(Path(args.state_root))),
        "turn": turn.to_public_dict() if turn is not None else None,
        "sent_group_messages": list(client.sent_group_messages),
        "sent_private_messages": list(client.sent_private_messages),
    }


def _handle_live_run(args: argparse.Namespace) -> dict[str, Any]:
    if args.max_events < 0:
        raise ValueError("max-events must be 0 or greater")
    config = _load_config(Path(args.config_json))
    state_root = Path(args.state_root)
    operations = _operations_from_config(config, state=_load_state(state_root))
    client = OneBotWebSocketClient(
        args.websocket_url,
        access_token=args.access_token,
        request_timeout_seconds=args.request_timeout_seconds,
        receive_timeout_seconds=args.receive_timeout_seconds,
    )
    adapter = OneBotAdapter(client=client)
    runtime = _runtime_from_adapter(config=config, operations=operations, adapter=adapter)
    turns: list[dict[str, Any]] = []
    try:
        if args.max_events == 0:
            if hasattr(client, "connect"):
                client.connect()
        for _ in range(args.max_events):
            turn = runtime.process_next(dry_run=not bool(args.send))
            if turn is None:
                break
            turns.append(turn.to_public_dict())
            _save_state(state_root, operations)
        if not turns:
            _save_state(state_root, operations)
        health = runtime.health()
    finally:
        if hasattr(client, "close"):
            client.close()
    return {
        "status": "ok",
        "command": "live-run",
        "state_file": str(_state_path(state_root)),
        "websocket_url": args.websocket_url,
        "dry_run": not bool(args.send),
        "processed_events": len(turns),
        "turns": turns,
        "health": health,
    }


def _handle_init_beta(args: argparse.Namespace) -> dict[str, Any]:
    result = create_qq_beta_pack(
        QQBetaPackConfig(
            output_dir=Path(args.output_dir),
            group_id=args.group,
            operator_user_id=args.operator,
            bot_user_id=args.bot_user_id,
            websocket_url=args.websocket_url,
            max_events=args.max_events,
            force=bool(args.force),
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "init-beta"})
    return payload


def _handle_init_profile(args: argparse.Namespace) -> dict[str, Any]:
    result = create_qq_profile_pack(
        QQProfilePackConfig(
            output_dir=Path(args.output_dir),
            group_id=args.group,
            role_name=args.name,
            force=bool(args.force),
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "init-profile"})
    return payload


def _handle_apply_profile(args: argparse.Namespace) -> dict[str, Any]:
    result = apply_qq_profile_pack(
        QQProfileApplyConfig(
            pack_dir=Path(args.pack_dir),
            profile_dir=Path(args.profile_dir),
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "apply-profile"})
    return payload


def _handle_init_replay(args: argparse.Namespace) -> dict[str, Any]:
    result = create_qq_replay_template(
        QQReplayTemplateConfig(
            output=Path(args.output),
            group_id=args.group,
            bot_user_id=args.bot_user_id,
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "init-replay"})
    return payload


def _handle_replay(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config_json)
    state_root = Path(args.state_root)
    replay_path = Path(args.replay_json)
    output_path = Path(args.output)
    config = _load_config(config_path)
    state = _load_state(state_root)
    operations = _operations_from_config(config, state=state)
    replay_payload = load_qq_replay(replay_path)
    overrides = runtime_overrides(replay_payload)
    client = FakeOneBotClient()
    events = replay_payload["events"]
    for event in events:
        client.queue_event(event)
    runtime = _runtime_from_adapter(
        config=config,
        operations=operations,
        adapter=OneBotAdapter(client=client),
    )
    turns: list[dict[str, Any]] = []
    for _ in events:
        turn = runtime.process_next(dry_run=True, **overrides)
        if turn is None:
            break
        turns.append(turn.to_public_dict())
        _save_state(state_root, operations)
    if not turns:
        _save_state(state_root, operations)
    report = build_replay_report(
        replay_path=replay_path,
        config_path=config_path,
        state_file=_state_path(state_root),
        dry_run=True,
        event_count=len(events),
        turns=turns,
        sent_group_messages=list(client.sent_group_messages),
        sent_private_messages=list(client.sent_private_messages),
        expectations=dict(replay_payload.get("expectations", {})),
    )
    write_replay_report(output_path, report)
    return {
        "status": "ok",
        "command": "replay",
        "passed": bool(report["passed"]),
        "dry_run": True,
        "processed_events": len(turns),
        "event_count": len(events),
        "output": str(output_path),
        "state_file": str(_state_path(state_root)),
        "expectations": report["expectations"],
        "summary": report["summary"],
    }


def _handle_beta_check(args: argparse.Namespace) -> dict[str, Any]:
    result = check_qq_beta_pack(QQBetaCheckConfig(pack_dir=Path(args.pack_dir)))
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "beta-check"})
    return payload


def _handle_startup_check(args: argparse.Namespace) -> dict[str, Any]:
    result = check_qq_startup_gate(
        QQStartupGateConfig(
            pack_dir=Path(args.pack_dir),
            replay_report=Path(args.replay_report),
            min_sticker_candidates=args.min_sticker_candidates,
        )
    )
    payload = result.to_public_dict()
    payload.update(
        {
            "status": "ok" if result.ready else "blocked",
            "command": "startup-check",
        }
    )
    if not result.ready:
        payload["_exit_code"] = 2
    return payload


def _handle_review_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    state_file = _state_path(Path(args.state_root))
    output = Path(args.output)
    report = build_qq_dry_run_review(
        QQDryRunReviewConfig(
            state_file=state_file,
            group_id=str(args.group),
            output=output,
        )
    )
    write_qq_dry_run_review(output, report)
    return {
        "status": "ok",
        "command": "review-dry-run",
        "output": str(output),
        "ready_for_send": bool(report["ready_for_send"]),
        "summary": report["summary"],
        "warnings": report["warnings"],
    }


def _handle_beta_day_report(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output)
    report = build_qq_beta_day_report(
        QQBetaDayReportConfig(
            date=args.date,
            group_id=str(args.group),
            dry_run_review=Path(args.dry_run_review),
            export_log=Path(args.export_log),
            failures_json=Path(args.failures_json) if args.failures_json else None,
            output=output,
        )
    )
    write_qq_beta_day_report(output, report)
    return {
        "status": "ok",
        "command": "beta-day-report",
        "output": str(output),
        "ready_for_send": bool(report["ready_for_send"]),
        "open_failure_count": int(report["summary"]["open_failure_count"]),
        "summary": report["summary"],
        "next_actions": report["next_actions"],
    }


def _handle_regression_intake(args: argparse.Namespace) -> dict[str, Any]:
    index_output = Path(args.index_output)
    intake = build_qq_regression_intake(
        QQRegressionIntakeConfig(
            group_id=str(args.group),
            bot_user_id=str(args.bot_user_id),
            failures_json=Path(args.failures_json),
            output_dir=Path(args.output_dir),
            index_output=index_output,
        )
    )
    write_qq_regression_intake(index_output, intake)
    return {
        "status": "ok",
        "command": "regression-intake",
        "output_dir": str(args.output_dir),
        "index_output": str(index_output),
        "open_failure_count": int(intake["open_failure_count"]),
        "draft_count": int(intake["draft_count"]),
        "drafts": [
            str(draft["replay_json"])
            for draft in intake["drafts"]
            if isinstance(draft, dict)
        ],
    }


def _handle_pause_resume(args: argparse.Namespace) -> dict[str, Any]:
    config = _load_config(Path(args.config_json))
    state_root = Path(args.state_root)
    operations = _operations_from_config(config, state=_load_state(state_root))
    if args.command == "pause":
        result = operations.pause_group(args.group, operator_user_id=args.operator)
    else:
        result = operations.resume_group(args.group, operator_user_id=args.operator)
    _save_state(state_root, operations)
    return {
        "status": "ok" if result.get("ok") else "blocked",
        "command": args.command,
        "result": result,
        "state_file": str(_state_path(state_root)),
    }


def _handle_inspect(args: argparse.Namespace) -> dict[str, Any]:
    config = _load_config(Path(args.config_json))
    operations = SocialOperationsController()
    if args.target == "role":
        return {"status": "ok", "role": operations.inspect_role(_character_card_from_config(config))}
    if args.target == "lorebook":
        lorebook = _optional_lorebook_from_config(config) or Lorebook()
        return {"status": "ok", "lorebook": operations.inspect_lorebook(lorebook)}
    if args.target == "stickers":
        stickers = _optional_stickers_from_config(config) or StickerLibrary(entries=())
        return {"status": "ok", "stickers": operations.inspect_stickers(stickers)}
    raise ValueError(f"unknown inspect target: {args.target}")


def _handle_health(args: argparse.Namespace) -> dict[str, Any]:
    config = _load_config(Path(args.config_json))
    operations = _operations_from_config(config, state=_load_state(Path(args.state_root)))
    return {"status": "ok", "health": operations.health_check()}


def _handle_export_log(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(Path(args.state_root))
    output = Path(args.output)
    entries = [
        entry
        for entry in state.audit_entries
        if entry.get("group_id") == str(args.group)
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json_file(output, {"entries": entries})
    return {
        "status": "ok",
        "group_id": str(args.group),
        "output": str(output),
        "entry_count": len(entries),
    }


def _runtime_from_adapter(
    *,
    config: dict[str, Any],
    operations: SocialOperationsController,
    adapter: OneBotAdapter,
) -> SocialRuntime:
    return SocialRuntime(
        adapter=adapter,
        character_card=_character_card_from_config(config),
        operations=operations,
        config=_runtime_config_from_config(config),
        lorebook=_optional_lorebook_from_config(config),
        sticker_library=_optional_stickers_from_config(config),
    )


def _runtime_config_from_config(config: dict[str, Any]) -> SocialRuntimeConfig:
    runtime = _dict_field(config, "runtime", default={})
    return SocialRuntimeConfig(
        bot_user_id=_config_string(config, "bot_user_id"),
        dry_run=bool(config.get("dry_run", True)),
        wake_keywords=_string_tuple_from_list(runtime.get("wake_keywords", [])),
        autonomy_score=_ratio(runtime.get("autonomy_score", 1.0), "runtime.autonomy_score"),
        sticker_emotion=_string_value(
            runtime.get("sticker_emotion", "ack"),
            "runtime.sticker_emotion",
        ),
        sticker_scene_tags=_string_tuple_from_list(runtime.get("sticker_scene_tags", [])),
        allow_sticker_only=_bool_value(
            runtime.get("allow_sticker_only", False),
            "runtime.allow_sticker_only",
        ),
    )


class _StoredState:
    def __init__(self, *, paused_groups: tuple[str, ...], audit_entries: tuple[dict[str, Any], ...]):
        self.paused_groups = paused_groups
        self.audit_entries = audit_entries


def _load_state(state_root: Path) -> _StoredState:
    path = _state_path(state_root)
    if not path.exists():
        return _StoredState(paused_groups=(), audit_entries=())
    payload = _read_json_file(path)
    return _StoredState(
        paused_groups=tuple(str(item) for item in payload.get("paused_groups", [])),
        audit_entries=tuple(dict(item) for item in payload.get("audit_entries", [])),
    )


def _save_state(state_root: Path, operations: SocialOperationsController) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    health = operations.health_check()
    payload = {
        "paused_groups": list(health["paused_groups"]),
        "audit_entries": [
            entry.to_public_dict()
            for entry in operations.audit_log.entries
        ],
    }
    _write_json_file(_state_path(state_root), payload)


def _state_path(state_root: Path) -> Path:
    return state_root / STATE_FILENAME


def _operations_from_config(
    config: dict[str, Any],
    *,
    state: _StoredState,
) -> SocialOperationsController:
    group_policy = _dict_field(config, "group_policy", default={})
    paused = _string_tuple_from_list(group_policy.get("paused_groups", [])) + state.paused_groups
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
                allowed_groups=_string_tuple_from_list(group_policy.get("allowed_groups", [])),
                blocked_groups=_string_tuple_from_list(group_policy.get("blocked_groups", [])),
                operator_user_ids=_string_tuple_from_list(
                    group_policy.get("operator_user_ids", [])
                ),
                paused_groups=tuple(dict.fromkeys(paused)),
                default_dry_run=bool(group_policy.get("default_dry_run", True)),
            )
        ),
        audit_log=audit_log,
    )


def _load_config(path: Path) -> dict[str, Any]:
    payload = _read_json_file(path)
    payload["_config_base"] = str(path.parent)
    return payload


def _character_card_from_config(config: dict[str, Any]) -> CharacterCard:
    return CharacterCard.from_dict(_payload_from_config(config, "role_card", "role_card_path"))


def _optional_lorebook_from_config(config: dict[str, Any]) -> Lorebook | None:
    if "lorebook" not in config and "lorebook_path" not in config:
        return None
    payload = _payload_from_config(config, "lorebook", "lorebook_path")
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("lorebook.entries must be a list")
    return Lorebook(
        entries=tuple(
            LorebookEntry(
                entry_id=str(item["entry_id"]),
                title=str(item["title"]),
                content=str(item["content"]),
                keywords=_string_tuple_from_list(item.get("keywords", [])),
                regex=_string_tuple_from_list(item.get("regex", [])),
                users=_string_tuple_from_list(item.get("users", [])),
                message_part_kinds=_string_tuple_from_list(item.get("message_part_kinds", [])),
                priority=int(item.get("priority", 0)),
                position=str(item.get("position", "after_recent_context")),
                expires_at=item.get("expires_at"),
            )
            for item in entries
        )
    )


def _optional_stickers_from_config(config: dict[str, Any]) -> StickerLibrary | None:
    if "sticker_library" not in config and "sticker_library_path" not in config:
        return None
    return StickerLibrary.from_dict(
        _payload_from_config(config, "sticker_library", "sticker_library_path")
    )


def _payload_from_config(config: dict[str, Any], inline_key: str, path_key: str) -> dict[str, Any]:
    if inline_key in config:
        return _dict_field(config, inline_key)
    path_value = _config_string(config, path_key)
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(_config_string(config, "_config_base")) / path
    return _read_json_file(path)


def _read_json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _dict_field(config: dict[str, Any], key: str, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    value = config.get(key, default)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return value


def _config_string(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _string_value(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_tuple_from_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("expected a JSON array of strings")
    return tuple(str(item) for item in value)


def _ratio(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be between 0 and 1")
    result = float(value)
    if result < 0 or result > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return result


def _bool_value(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a bool")
    return value
