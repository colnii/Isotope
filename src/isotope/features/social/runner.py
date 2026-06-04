"""CLI runner for social bot operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ...integrations.qq import FakeOneBotClient, OneBotAdapter, OneBotWebSocketClient
from .audit_log import SocialAuditEntry, SocialAuditLog
from .beta_pack import QQBetaPackConfig, create_qq_beta_pack
from .character_card import CharacterCard
from .config import SocialGroupPolicy, SocialOperationsConfig
from .lorebook import Lorebook, LorebookEntry
from .operations import SocialOperationsController
from .runtime import SocialRuntime, SocialRuntimeConfig
from .stickers import StickerLibrary


STATE_FILENAME = "social-qq-state.json"


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Isotope social bot operations.")
    subparsers = parser.add_subparsers(dest="surface", required=True)
    qq_parser = subparsers.add_parser("qq", help="QQ group bot operations.")
    qq_subparsers = qq_parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("dry-run", "Process one QQ event without sending."),
        ("run", "Process one QQ event; sends only with --send."),
    ):
        command = qq_subparsers.add_parser(name, help=help_text)
        _add_config_state_args(command)
        command.add_argument("--event-json", required=True, help="OneBot event JSON file.")
        command.add_argument("--send", action="store_true", help="Allow sending for qq run.")
        command.add_argument("--json", action="store_true", help="Print JSON output.")

    live_run = qq_subparsers.add_parser(
        "live-run",
        help="Connect to a OneBot WebSocket endpoint and process QQ events.",
    )
    _add_config_state_args(live_run)
    live_run.add_argument("--websocket-url", required=True, help="NapCat OneBot WebSocket URL.")
    live_run.add_argument("--access-token", help="Optional OneBot access token.")
    live_run.add_argument(
        "--max-events",
        type=int,
        default=1,
        help="Stop after this many received events; 0 means health-only.",
    )
    live_run.add_argument(
        "--receive-timeout-seconds",
        type=float,
        default=30.0,
        help="Stop cleanly when no event arrives within this many seconds.",
    )
    live_run.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=5.0,
        help="Timeout for OneBot API responses.",
    )
    live_run.add_argument("--send", action="store_true", help="Allow real sends.")
    live_run.add_argument("--json", action="store_true", help="Print JSON output.")

    init_beta = qq_subparsers.add_parser(
        "init-beta",
        help="Create a controlled QQ beta config and script pack.",
    )
    init_beta.add_argument("--output-dir", required=True, help="Directory to create.")
    init_beta.add_argument("--group", required=True, help="Controlled QQ group id.")
    init_beta.add_argument("--operator", required=True, help="Operator QQ user id.")
    init_beta.add_argument("--bot-user-id", required=True, help="Bot QQ user id.")
    init_beta.add_argument("--websocket-url", required=True, help="NapCat OneBot WebSocket URL.")
    init_beta.add_argument(
        "--max-events",
        type=int,
        default=10,
        help="Default event count for dry-run and send scripts.",
    )
    init_beta.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files in an existing beta pack directory.",
    )
    init_beta.add_argument("--json", action="store_true", help="Print JSON output.")

    for name, help_text in (
        ("pause", "Pause one QQ group."),
        ("resume", "Resume one QQ group."),
    ):
        command = qq_subparsers.add_parser(name, help=help_text)
        _add_config_state_args(command)
        command.add_argument("--group", required=True, help="QQ group id.")
        command.add_argument("--operator", required=True, help="Operator QQ user id.")
        command.add_argument("--json", action="store_true", help="Print JSON output.")

    inspect = qq_subparsers.add_parser("inspect", help="Inspect configured bot assets.")
    inspect.add_argument(
        "target",
        choices=("role", "lorebook", "stickers"),
        help="Asset to inspect.",
    )
    inspect.add_argument("--config-json", required=True, help="QQ runtime config JSON.")
    inspect.add_argument("--json", action="store_true", help="Print JSON output.")

    health = qq_subparsers.add_parser("health", help="Show QQ operations health.")
    _add_config_state_args(health)
    health.add_argument("--json", action="store_true", help="Print JSON output.")

    export = qq_subparsers.add_parser("export-log", help="Export group audit log.")
    export.add_argument("--state-root", required=True, help="State root directory.")
    export.add_argument("--group", required=True, help="QQ group id.")
    export.add_argument("--output", required=True, help="Output JSON file.")
    export.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def _add_config_state_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config-json", required=True, help="QQ runtime config JSON.")
    parser.add_argument("--state-root", required=True, help="State root directory.")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.surface != "qq":
            raise ValueError(f"unknown social surface: {args.surface}")
        payload = _handle_qq(args)
        if getattr(args, "json", False):
            _print_json(payload)
        else:
            _print_plain(payload)
        return 0
    except (FileNotFoundError, RuntimeError, TimeoutError, ValueError) as exc:
        payload = {
            "status": "error",
            "error": {"code": "social_runner_error", "message": str(exc)},
        }
        if getattr(args, "json", False):
            _print_json(payload)
        else:
            print(f"error: {exc}")
        return 2


def _handle_qq(args: argparse.Namespace) -> dict[str, Any]:
    if args.command in {"dry-run", "run"}:
        return _handle_run(args)
    if args.command == "live-run":
        return _handle_live_run(args)
    if args.command == "init-beta":
        return _handle_init_beta(args)
    if args.command in {"pause", "resume"}:
        return _handle_pause_resume(args)
    if args.command == "inspect":
        return _handle_inspect(args)
    if args.command == "health":
        return _handle_health(args)
    if args.command == "export-log":
        return _handle_export_log(args)
    raise ValueError(f"unknown qq command: {args.command}")


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
        config=SocialRuntimeConfig(
            bot_user_id=_config_string(config, "bot_user_id"),
            dry_run=bool(config.get("dry_run", True)),
        ),
        lorebook=_optional_lorebook_from_config(config),
        sticker_library=_optional_stickers_from_config(config),
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


def _string_tuple_from_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("expected a JSON array of strings")
    return tuple(str(item) for item in value)


def _print_plain(payload: dict[str, Any]) -> None:
    print(f"status: {payload['status']}")


if __name__ == "__main__":
    raise SystemExit(main())
