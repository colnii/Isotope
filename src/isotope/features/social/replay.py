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

DEFAULT_REPLAY_EXPECTATIONS = {
    "require_processed_events": 2,
    "min_proposed_actions": 1,
    "min_sticker_candidates": 1,
    "require_sticker_candidate_ids": ["ship-it"],
    "forbid_sticker_candidate_ids": [],
    "require_sticker_block_reasons": [],
    "forbid_sticker_block_reasons": [],
    "max_selected_sticker_actions": 0,
    "max_send_feedback": 0,
    "max_sent_group_messages": 0,
    "require_all_dry_run": True,
}

EXPECTATION_NAMES = (
    "require_processed_events",
    "min_proposed_actions",
    "min_sticker_candidates",
    "require_sticker_candidate_ids",
    "forbid_sticker_candidate_ids",
    "require_sticker_block_reasons",
    "forbid_sticker_block_reasons",
    "max_selected_sticker_actions",
    "max_send_feedback",
    "max_sent_group_messages",
    "require_all_dry_run",
)


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
    payload = qq_replay_template_payload(config)
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
    expectations = payload.get("expectations", {})
    if not isinstance(expectations, dict):
        raise ValueError("replay expectations must be a JSON object")
    return {
        "events": [dict(event) for event in events],
        "runtime": dict(runtime),
        "expectations": dict(expectations),
    }


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
    expectations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = _summary(
        event_count=event_count,
        turns=turns,
        sent_group_messages=sent_group_messages,
        sent_private_messages=sent_private_messages,
    )
    expectation_results = evaluate_expectations(expectations or {}, summary, turns=turns)
    return {
        "kind": "qq_replay_report",
        "replay_json": str(replay_path),
        "config_json": str(config_path),
        "state_file": str(state_file),
        "dry_run": dry_run,
        "passed": all(result["ok"] for result in expectation_results),
        "expectations": expectation_results,
        "summary": summary,
        "turns": turns,
        "sent_group_messages": sent_group_messages,
        "sent_private_messages": sent_private_messages,
    }


def write_replay_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, report)


def evaluate_expectations(
    expectations: dict[str, Any],
    summary: dict[str, Any],
    *,
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(expectations, dict):
        raise ValueError("expectations must be a JSON object")
    results: list[dict[str, Any]] = []
    for name in EXPECTATION_NAMES:
        if name not in expectations:
            continue
        expected = expectations[name]
        actual = _expectation_actual(name, summary=summary, turns=turns)
        results.append(
            {
                "name": name,
                "ok": _expectation_ok(name, expected=expected, actual=actual),
                "expected": expected,
                "actual": actual,
            }
        )
    unknown = sorted(set(expectations) - {item["name"] for item in results})
    for name in unknown:
        results.append(
            {
                "name": name,
                "ok": False,
                "expected": expectations[name],
                "actual": "unsupported expectation",
            }
        )
    return results


def qq_replay_template_payload(config: QQReplayTemplateConfig) -> dict[str, Any]:
    group_id = int(config.group_id)
    return {
        "schema_version": "isotope.qq_replay.v1",
        "name": "QQ controlled replay",
        "runtime": dict(DEFAULT_REPLAY_RUNTIME),
        "expectations": dict(DEFAULT_REPLAY_EXPECTATIONS),
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
    sticker_candidate_ids: list[str] = []
    selected_sticker_ids: list[str] = []
    sticker_block_reason_counts: dict[str, int] = {}
    selected_sticker_action_count = 0
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
            for item in proposed_items:
                sticker_ids = _sticker_ids_from_candidate(item)
                if sticker_ids:
                    sticker_candidates += 1
                    _append_unique(sticker_candidate_ids, sticker_ids)
                for reason in _sticker_block_reasons_from_candidate(item):
                    sticker_block_reason_counts[reason] = (
                        sticker_block_reason_counts.get(reason, 0) + 1
                    )
        if isinstance(selected_items, list):
            selected += len(selected_items)
            for item in selected_items:
                sticker_ids = _sticker_ids_from_candidate(item)
                if sticker_ids:
                    selected_sticker_action_count += 1
                    _append_unique(selected_sticker_ids, sticker_ids)
        feedback_items = turn.get("send_feedback", [])
        if isinstance(feedback_items, list):
            send_feedback += len(feedback_items)
    return {
        "event_count": event_count,
        "processed_events": len(turns),
        "proposed_action_count": proposed,
        "selected_action_count": selected,
        "sticker_candidate_count": sticker_candidates,
        "sticker_candidate_ids": sticker_candidate_ids,
        "sticker_candidate_block_reason_counts": sticker_block_reason_counts,
        "selected_sticker_ids": selected_sticker_ids,
        "selected_sticker_action_count": selected_sticker_action_count,
        "blocked_turn_count": blocked,
        "send_feedback_count": send_feedback,
        "sent_group_message_count": len(sent_group_messages),
        "sent_private_message_count": len(sent_private_messages),
    }


def _sticker_ids_from_candidate(item: object) -> tuple[str, ...]:
    if not isinstance(item, dict):
        return ()
    result: list[str] = []
    metadata = item.get("metadata", {})
    if isinstance(metadata, dict):
        selection = metadata.get("sticker_selection")
        if isinstance(selection, dict):
            entry = selection.get("entry", {})
            if isinstance(entry, dict):
                _append_sticker_id(result, entry.get("sticker_id"))
    action = item.get("reply_action")
    if not isinstance(action, dict):
        return tuple(result)
    parts = action.get("parts", [])
    if not isinstance(parts, list):
        return tuple(result)
    for part in parts:
        if not isinstance(part, dict) or part.get("kind") != "sticker":
            continue
        platform_data = part.get("platform_data", {})
        if isinstance(platform_data, dict):
            _append_sticker_id(result, platform_data.get("sticker_id"))
    return tuple(result)


def _sticker_block_reasons_from_candidate(item: object) -> tuple[str, ...]:
    if not isinstance(item, dict):
        return ()
    metadata = item.get("metadata", {})
    if not isinstance(metadata, dict):
        return ()
    selection = metadata.get("sticker_selection")
    if not isinstance(selection, dict) or selection.get("selected") is True:
        return ()
    reasons = selection.get("blocked_reasons", [])
    if not isinstance(reasons, list):
        return ()
    result: list[str] = []
    for reason in reasons:
        if isinstance(reason, str) and reason.strip():
            _append_unique(result, (reason.strip(),))
    return tuple(result)


def _append_unique(target: list[str], items: tuple[str, ...]) -> None:
    for item in items:
        if item not in target:
            target.append(item)


def _append_sticker_id(target: list[str], value: object) -> None:
    if isinstance(value, str) and value.strip() and value.strip() not in target:
        target.append(value.strip())


def _expectation_actual(
    name: str,
    *,
    summary: dict[str, Any],
    turns: list[dict[str, Any]],
) -> object:
    if name == "require_processed_events":
        return summary["processed_events"]
    if name == "min_proposed_actions":
        return summary["proposed_action_count"]
    if name == "min_sticker_candidates":
        return summary["sticker_candidate_count"]
    if name in {"require_sticker_candidate_ids", "forbid_sticker_candidate_ids"}:
        return list(summary["sticker_candidate_ids"])
    if name in {"require_sticker_block_reasons", "forbid_sticker_block_reasons"}:
        return list(summary["sticker_candidate_block_reason_counts"])
    if name == "max_selected_sticker_actions":
        return summary["selected_sticker_action_count"]
    if name == "max_send_feedback":
        return summary["send_feedback_count"]
    if name == "max_sent_group_messages":
        return summary["sent_group_message_count"]
    if name == "require_all_dry_run":
        return all(_turn_is_dry_run(turn) for turn in turns)
    return None


def _expectation_ok(name: str, *, expected: object, actual: object) -> bool:
    if name == "require_processed_events":
        return _int_value(actual, "actual") == _int_value(expected, name)
    if name in {"min_proposed_actions", "min_sticker_candidates"}:
        return _int_value(actual, "actual") >= _int_value(expected, name)
    if name == "require_sticker_candidate_ids":
        actual_ids = set(_string_list_value(actual, "actual"))
        return all(item in actual_ids for item in _string_list_value(expected, name))
    if name == "forbid_sticker_candidate_ids":
        actual_ids = set(_string_list_value(actual, "actual"))
        return all(item not in actual_ids for item in _string_list_value(expected, name))
    if name == "require_sticker_block_reasons":
        actual_reasons = set(_string_list_value(actual, "actual"))
        return all(item in actual_reasons for item in _string_list_value(expected, name))
    if name == "forbid_sticker_block_reasons":
        actual_reasons = set(_string_list_value(actual, "actual"))
        return all(item not in actual_reasons for item in _string_list_value(expected, name))
    if name == "max_selected_sticker_actions":
        return _int_value(actual, "actual") <= _int_value(expected, name)
    if name in {"max_send_feedback", "max_sent_group_messages"}:
        return _int_value(actual, "actual") <= _int_value(expected, name)
    if name == "require_all_dry_run":
        return _bool(expected, name) == bool(actual)
    return False


def _turn_is_dry_run(turn: dict[str, Any]) -> bool:
    decision = turn.get("decision")
    return isinstance(decision, dict) and decision.get("dry_run") is True


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


def _int_value(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _string_list_value(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings")
        result.append(item.strip())
    return result
