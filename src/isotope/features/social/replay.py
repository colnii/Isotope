"""QQ replay templates and decision reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPLAY_RUNTIME = {
    "wake_keywords": ["看看", "帮我", "bot"],
    "autonomy_score": 1.0,
    "sticker_emotion": "positive",
    "sticker_scene_tags": ["review"],
    "allow_sticker_only": True,
}


@dataclass(frozen=True)
class QQReplayTemplateConfig:
    output: Path
    group_id: str
    bot_user_id: str

    def __post_init__(self) -> None:
        _required_text(str(self.output), "output")
        _required_text(self.group_id, "group")
        _required_text(self.bot_user_id, "bot_user_id")


@dataclass(frozen=True)
class QQReplayTemplateResult:
    output: Path
    event_count: int

    def to_public_dict(self) -> dict[str, Any]:
        return {"output": str(self.output), "event_count": self.event_count}


def create_qq_replay_template(config: QQReplayTemplateConfig) -> QQReplayTemplateResult:
    payload = _template_payload(config)
    config.output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(config.output, payload)
    return QQReplayTemplateResult(output=config.output, event_count=len(payload["events"]))


def load_qq_replay(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("replay events must be a non-empty list")
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("replay events items must be JSON objects")
    runtime = payload.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError("replay runtime must be a JSON object")
    return {"events": [dict(event) for event in events], "runtime": dict(runtime)}


def runtime_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(payload.get("runtime", {}))
    return {
        "wake_keywords": _string_tuple(runtime.get("wake_keywords", []), "wake_keywords"),
        "autonomy_score": _ratio(runtime.get("autonomy_score", 1.0), "autonomy_score"),
        "sticker_emotion": _required_text(
            str(runtime.get("sticker_emotion", "ack")),
            "sticker_emotion",
        ),
        "sticker_scene_tags": _string_tuple(
            runtime.get("sticker_scene_tags", []),
            "sticker_scene_tags",
        ),
        "allow_sticker_only": _bool(runtime.get("allow_sticker_only", False), "allow_sticker_only"),
    }


def build_replay_report(
    *,
    replay_path: Path,
    config_path: Path,
    state_file: Path,
    dry_run: bool,
    event_count: int,
    turns: list[dict[str, Any]],
    sent_group_messages: list[dict[str, Any]],
    sent_private_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": "qq_replay_report",
        "replay_json": str(replay_path),
        "config_json": str(config_path),
        "state_file": str(state_file),
        "dry_run": dry_run,
        "summary": _summary(
            event_count=event_count,
            turns=turns,
            sent_group_messages=sent_group_messages,
            sent_private_messages=sent_private_messages,
        ),
        "turns": turns,
        "sent_group_messages": sent_group_messages,
        "sent_private_messages": sent_private_messages,
    }


def write_replay_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, report)


def _template_payload(config: QQReplayTemplateConfig) -> dict[str, Any]:
    group_id = int(config.group_id)
    return {
        "schema_version": "isotope.qq_replay.v1",
        "name": "QQ controlled replay",
        "runtime": dict(DEFAULT_REPLAY_RUNTIME),
        "events": [
            {
                "message_id": 9001,
                "message_type": "group",
                "group_id": group_id,
                "user_id": 10001,
                "sender": {"nickname": "小林", "role": "member"},
                "time": 1780560000,
                "message": [
                    {"type": "at", "data": {"qq": config.bot_user_id}},
                    {"type": "text", "data": {"text": " 帮我看看这个 PR"}},
                ],
                "raw_message": f"[CQ:at,qq={config.bot_user_id}] 帮我看看这个 PR",
            },
            {
                "message_id": 9002,
                "message_type": "group",
                "group_id": group_id,
                "user_id": 10002,
                "sender": {"nickname": "阿周", "role": "member"},
                "time": 1780560060,
                "message": [{"type": "text", "data": {"text": "这个结果可以发了吗？"}}],
                "raw_message": "这个结果可以发了吗？",
            },
        ],
    }


def _summary(
    *,
    event_count: int,
    turns: list[dict[str, Any]],
    sent_group_messages: list[dict[str, Any]],
    sent_private_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    proposed = 0
    selected = 0
    sticker_candidates = 0
    blocked = 0
    send_feedback = 0
    for turn in turns:
        if not turn.get("policy", {}).get("allowed", False):
            blocked += 1
        decision = turn.get("decision")
        if not isinstance(decision, dict):
            continue
        proposed_items = decision.get("proposed", [])
        selected_items = decision.get("selected", [])
        if isinstance(proposed_items, list):
            proposed += len(proposed_items)
            sticker_candidates += sum(1 for item in proposed_items if _is_sticker_candidate(item))
        if isinstance(selected_items, list):
            selected += len(selected_items)
        feedback_items = turn.get("send_feedback", [])
        if isinstance(feedback_items, list):
            send_feedback += len(feedback_items)
    return {
        "event_count": event_count,
        "processed_events": len(turns),
        "proposed_action_count": proposed,
        "selected_action_count": selected,
        "sticker_candidate_count": sticker_candidates,
        "blocked_turn_count": blocked,
        "send_feedback_count": send_feedback,
        "sent_group_message_count": len(sent_group_messages),
        "sent_private_message_count": len(sent_private_messages),
    }


def _is_sticker_candidate(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    action = item.get("reply_action")
    if not isinstance(action, dict):
        return False
    parts = action.get("parts", [])
    if not isinstance(parts, list):
        return False
    return any(isinstance(part, dict) and part.get("kind") == "sticker" for part in parts)


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


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings")
        result.append(item.strip())
    return tuple(result)


def _ratio(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be between 0 and 1")
    result = float(value)
    if result < 0 or result > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return result


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a bool")
    return value
