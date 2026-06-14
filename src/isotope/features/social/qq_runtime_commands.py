"""Runtime command handlers for QQ social commands."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ...integrations.qq import FakeOneBotClient, OneBotAdapter, OneBotWebSocketClient
from ...llm.provider import resolve_llm_chat_provider
from .capability_bridge import SocialCapabilityBridge, SocialCapabilityPolicy
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
from .runtime import SocialCapabilityRuntimeConfig, SocialRuntime, SocialRuntimeConfig
from .loop import SocialDecisionLoop
from .participation_provider import (
    LLMParticipationDecision,
    LLMSocialParticipationProvider,
)
from .reply_provider import LLMSocialReplyProvider


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
    return run_qq_replay(
        config_path=Path(args.config_json),
        state_root=Path(args.state_root),
        replay_path=Path(args.replay_json),
        output_path=Path(args.output),
    )


def run_qq_replay(
    *,
    config_path: Path,
    state_root: Path,
    replay_path: Path,
    output_path: Path,
) -> dict[str, Any]:
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
    replay_provider = _replay_participation_provider(replay_payload)
    if replay_provider is not None:
        runtime = replace(
            runtime,
            decision_loop=replace(
                runtime.decision_loop,
                participation_provider=replay_provider,
            ),
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


@dataclass(frozen=True)
class _ReplayParticipationProvider:
    decision: LLMParticipationDecision | None = None
    provider_error: str | None = None

    def decide(
        self,
        request: Any,
        *,
        wake_signals: tuple[str, ...],
    ) -> LLMParticipationDecision:
        if self.provider_error is not None:
            raise ValueError(self.provider_error)
        if self.decision is None:
            raise ValueError("replay participation decision is not configured")
        return self.decision


def _replay_participation_provider(
    replay_payload: dict[str, Any],
) -> _ReplayParticipationProvider | None:
    runtime = dict_field(replay_payload, "runtime", default={})
    decision_payload = runtime.get("replay_participation_decision")
    provider_error = runtime.get("replay_participation_error")
    if decision_payload is not None and provider_error is not None:
        raise ValueError(
            "replay runtime must not set both replay_participation_decision "
            "and replay_participation_error"
        )
    if provider_error is not None:
        return _ReplayParticipationProvider(
            provider_error=string_value(
                provider_error,
                "runtime.replay_participation_error",
            )
        )
    if decision_payload is None:
        return None
    if not isinstance(decision_payload, dict):
        raise ValueError("runtime.replay_participation_decision must be a JSON object")
    action = string_value(
        decision_payload.get("action"),
        "runtime.replay_participation_decision.action",
    )
    reason = string_value(
        decision_payload.get("reason"),
        "runtime.replay_participation_decision.reason",
    )
    confidence = ratio(
        decision_payload.get("confidence", 0.5),
        "runtime.replay_participation_decision.confidence",
    )
    text = decision_payload.get("text")
    if text is not None:
        text = string_value(text, "runtime.replay_participation_decision.text")
    return _ReplayParticipationProvider(
        decision=LLMParticipationDecision(
            action=action,
            reason=reason,
            confidence=confidence,
            text=text,
            metadata={
                "provider": "qq_replay",
                "model": "replay_participation_decision",
                "usage": {},
            },
        )
    )


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
        decision_loop=decision_loop_from_config(config),
        capability_bridge=capability_bridge_from_config(config),
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
        capability=capability_runtime_config_from_config(config),
    )


def capability_runtime_config_from_config(config: dict[str, Any]) -> SocialCapabilityRuntimeConfig:
    runtime = dict_field(config, "runtime", default={})
    capability = dict_field(runtime, "capability", default={})
    enabled = bool_value(capability.get("enabled", False), "runtime.capability.enabled")
    if not enabled:
        return SocialCapabilityRuntimeConfig()
    input_defaults = dict_field(capability, "input_defaults", default={})
    return SocialCapabilityRuntimeConfig(
        enabled=True,
        capability_id=string_value(
            capability.get("capability_id"),
            "runtime.capability.capability_id",
        ),
        trigger_keywords=string_tuple_from_list(capability.get("trigger_keywords", [])),
        input_defaults=dict(input_defaults),
        query_input_key=string_value(
            capability.get("query_input_key", "query"),
            "runtime.capability.query_input_key",
        ),
        approval_keywords=string_tuple_from_list(capability.get("approval_keywords", [])),
    )


def capability_bridge_from_config(config: dict[str, Any]) -> SocialCapabilityBridge | None:
    runtime = dict_field(config, "runtime", default={})
    capability = dict_field(runtime, "capability", default={})
    capability_config = capability_runtime_config_from_config(config)
    if not capability_config.enabled:
        return None
    approval_required = bool_value(
        capability.get("approval_required", True),
        "runtime.capability.approval_required",
    )
    approval_required_capabilities = (
        (capability_config.capability_id,) if approval_required else ()
    )
    return SocialCapabilityBridge(
        policy=SocialCapabilityPolicy(
            approval_required_capabilities=approval_required_capabilities,
        )
    )


def decision_loop_from_config(config: dict[str, Any]) -> SocialDecisionLoop:
    runtime = dict_field(config, "runtime", default={})
    participation_name = string_value(
        runtime.get("participation_provider", "rules"),
        "runtime.participation_provider",
    )
    provider_name = string_value(
        runtime.get("reply_provider", "deterministic"),
        "runtime.reply_provider",
    )
    llm_provider: Any | None = None
    if participation_name == "llm":
        resolution = resolve_llm_chat_provider()
        if resolution.status != "configured" or resolution.provider is None:
            raise ValueError(
                "LLM participation provider is not configured: "
                f"{resolution.reason_code}"
            )
        llm_provider = resolution.provider
    elif participation_name != "rules":
        raise ValueError("runtime.participation_provider must be rules or llm")

    participation_provider = (
        LLMSocialParticipationProvider(chat_provider=llm_provider)
        if llm_provider is not None
        else None
    )
    if provider_name == "deterministic":
        return SocialDecisionLoop(participation_provider=participation_provider)
    if provider_name != "llm":
        raise ValueError("runtime.reply_provider must be deterministic or llm")
    if llm_provider is None:
        resolution = resolve_llm_chat_provider()
        if resolution.status != "configured" or resolution.provider is None:
            raise ValueError(
                f"LLM reply provider is not configured: {resolution.reason_code}"
            )
        llm_provider = resolution.provider
    return SocialDecisionLoop(
        reply_provider=LLMSocialReplyProvider(chat_provider=llm_provider),
        participation_provider=participation_provider,
    )
