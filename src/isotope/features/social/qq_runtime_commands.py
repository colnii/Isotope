"""Runtime command handlers for QQ social commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...integrations.qq import FakeOneBotClient, OneBotAdapter, OneBotWebSocketClient
from .operations import SocialOperationsController
from .qq_state_config import (
    bool_value,
    character_card_from_config,
    config_string,
    dict_field,
    load_config,
    load_state,
    optional_lorebook_from_config,
    optional_stickers_from_config,
    operations_from_config,
    ratio,
    read_json_file,
    save_state,
    state_path,
    string_tuple_from_list,
    string_value,
)
from .replay import (
    build_replay_report,
    load_qq_replay,
    runtime_overrides,
    write_replay_report,
)
from .runtime import SocialRuntime, SocialRuntimeConfig


def handle_run(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(Path(args.config_json))
    state = load_state(Path(args.state_root))
    operations = operations_from_config(config, state=state)
    client = FakeOneBotClient()
    client.queue_event(read_json_file(Path(args.event_json)))
    runtime = runtime_from_adapter(
        config=config,
        operations=operations,
        adapter=OneBotAdapter(client=client),
    )
    dry_run = True if args.command == "dry-run" else not bool(args.send)
    turn = runtime.process_next(dry_run=dry_run)
    save_state(Path(args.state_root), operations)
    return {
        "status": "ok",
        "command": args.command,
        "state_file": str(state_path(Path(args.state_root))),
        "turn": turn.to_public_dict() if turn is not None else None,
        "sent_group_messages": list(client.sent_group_messages),
        "sent_private_messages": list(client.sent_private_messages),
    }


def handle_live_run(args: argparse.Namespace) -> dict[str, Any]:
    if args.max_events < 0:
        raise ValueError("max-events must be 0 or greater")
    config = load_config(Path(args.config_json))
    state_root = Path(args.state_root)
    operations = operations_from_config(config, state=load_state(state_root))
    client = OneBotWebSocketClient(
        args.websocket_url,
        access_token=args.access_token,
        request_timeout_seconds=args.request_timeout_seconds,
        receive_timeout_seconds=args.receive_timeout_seconds,
    )
    adapter = OneBotAdapter(client=client)
    runtime = runtime_from_adapter(config=config, operations=operations, adapter=adapter)
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
            save_state(state_root, operations)
        if not turns:
            save_state(state_root, operations)
        health = runtime.health()
    finally:
        if hasattr(client, "close"):
            client.close()
    return {
        "status": "ok",
        "command": "live-run",
        "state_file": str(state_path(state_root)),
        "websocket_url": args.websocket_url,
        "dry_run": not bool(args.send),
        "processed_events": len(turns),
        "turns": turns,
        "health": health,
    }


def handle_replay(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config_json)
    state_root = Path(args.state_root)
    replay_path = Path(args.replay_json)
    output_path = Path(args.output)
    config = load_config(config_path)
    state = load_state(state_root)
    operations = operations_from_config(config, state=state)
    replay_payload = load_qq_replay(replay_path)
    overrides = runtime_overrides(replay_payload)
    client = FakeOneBotClient()
    events = replay_payload["events"]
    for event in events:
        client.queue_event(event)
    runtime = runtime_from_adapter(
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
        save_state(state_root, operations)
    if not turns:
        save_state(state_root, operations)
    report = build_replay_report(
        replay_path=replay_path,
        config_path=config_path,
        state_file=state_path(state_root),
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
        "state_file": str(state_path(state_root)),
        "expectations": report["expectations"],
        "summary": report["summary"],
    }


def runtime_from_adapter(
    *,
    config: dict[str, Any],
    operations: SocialOperationsController,
    adapter: OneBotAdapter,
) -> SocialRuntime:
    return SocialRuntime(
        adapter=adapter,
        character_card=character_card_from_config(config),
        operations=operations,
        config=runtime_config_from_config(config),
        lorebook=optional_lorebook_from_config(config),
        sticker_library=optional_stickers_from_config(config),
    )


def runtime_config_from_config(config: dict[str, Any]) -> SocialRuntimeConfig:
    runtime = dict_field(config, "runtime", default={})
    return SocialRuntimeConfig(
        bot_user_id=config_string(config, "bot_user_id"),
        dry_run=bool(config.get("dry_run", True)),
        wake_keywords=string_tuple_from_list(runtime.get("wake_keywords", [])),
        autonomy_score=ratio(runtime.get("autonomy_score", 1.0), "runtime.autonomy_score"),
        sticker_emotion=string_value(
            runtime.get("sticker_emotion", "ack"),
            "runtime.sticker_emotion",
        ),
        sticker_scene_tags=string_tuple_from_list(runtime.get("sticker_scene_tags", [])),
        allow_sticker_only=bool_value(
            runtime.get("allow_sticker_only", False),
            "runtime.allow_sticker_only",
        ),
    )
