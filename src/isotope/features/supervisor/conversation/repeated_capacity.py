"""Repeated capability-call handling for Supervisor conversations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def capacity_call_key(decision: Mapping[str, Any]) -> str:
    capacity_id = _string_value(decision.get("capacity_id"))
    arguments = decision.get("arguments")
    if not isinstance(arguments, Mapping):
        arguments = {}
    return json.dumps(
        {
            "capacity_id": capacity_id,
            "arguments": arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def repeated_capability_observation(
    decisions: list[dict[str, Any]],
    *,
    completed_calls: Mapping[str, dict[str, Any]],
) -> dict[str, Any] | None:
    for decision in decisions:
        call_key = capacity_call_key(decision)
        if call_key in completed_calls:
            return _repeated_call_observation(
                decision,
                previous_status="completed",
            )
    return None


def repeated_failed_capability_answer(
    decisions: list[dict[str, Any]],
    *,
    failed_calls: Mapping[str, dict[str, Any]],
) -> str | None:
    for decision in decisions:
        call_key = capacity_call_key(decision)
        if call_key not in failed_calls:
            continue
        message = failed_calls[call_key].get("message")
        if not isinstance(message, str) or not message.strip():
            message = "能力执行失败"
        return f"{_string_value(decision.get('capacity_id'))} 执行失败：{message.strip()}"
    return None


def _repeated_call_observation(
    decision: Mapping[str, Any],
    *,
    previous_status: str,
) -> dict[str, Any]:
    return {
        "kind": "invalid_repeated_capability_call",
        "status": "rejected",
        "capacity_id": _string_value(decision.get("capacity_id")),
        "previous_status": previous_status,
        "arguments": _safe_arguments(decision.get("arguments")),
        "instruction": (
            "同一个 capability 可以用新的 arguments 继续纠偏；不要重复执行完全相同 "
            "arguments 的调用。请基于已有 capacity_observation 回答，或改 query/"
            "换 capability 后再调用。"
        ),
    }


def _safe_arguments(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: _safe_value(item)
        for key, item in value.items()
        if isinstance(key, str) and not _unsafe_key(key)
    }


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 500 else value[:499] + "..."
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:10]]
    if isinstance(value, Mapping):
        return _safe_arguments(value)
    return str(value)


def _unsafe_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in ("api_key", "apikey", "secret", "token", "raw", "patch", "argv")
    )


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""
