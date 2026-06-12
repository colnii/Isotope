"""Low-sensitive Codex runtime summary aggregation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .events import CodexRuntimeEvent


@dataclass(frozen=True)
class CodexRuntimeSummary:
    status: str
    reason_code: str
    last_agent_message: str | None
    event_counts: dict[str, int]
    tool_call_count: int
    tool_output_count: int
    error_messages: list[str]
    malformed_event_count: int
    has_agent_message: bool
    stderr_preview: str

    def __post_init__(self) -> None:
        _require_string("status", self.status)
        _require_string("reason_code", self.reason_code)
        if self.last_agent_message is not None:
            _require_string("last_agent_message", self.last_agent_message)
        if not isinstance(self.event_counts, dict):
            raise ValueError("event_counts must be a dict")
        for key, value in self.event_counts.items():
            _require_string("event_counts key", key)
            if not isinstance(value, int) or value < 0:
                raise ValueError("event_counts values must be non-negative integers")
        for field_name in (
            "tool_call_count",
            "tool_output_count",
            "malformed_event_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.has_agent_message, bool):
            raise ValueError("has_agent_message must be a bool")
        _require_string("stderr_preview", self.stderr_preview)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "last_agent_message": self.last_agent_message,
            "event_counts": dict(self.event_counts),
            "tool_call_count": self.tool_call_count,
            "tool_output_count": self.tool_output_count,
            "error_messages": list(self.error_messages),
            "malformed_event_count": self.malformed_event_count,
            "has_agent_message": self.has_agent_message,
            "stderr_preview": self.stderr_preview,
        }


def summarize_codex_runtime_events(
    *,
    events: list[CodexRuntimeEvent],
    status: str,
    reason_code: str,
    malformed_event_count: int,
    stderr_preview: str,
) -> CodexRuntimeSummary:
    counts = Counter(event.kind for event in events)
    last_agent_message = _last_agent_message(events)
    error_messages = [
        event.text
        for event in events
        if event.kind == "error" and event.text.strip()
    ][:20]
    return CodexRuntimeSummary(
        status=status,
        reason_code=reason_code,
        last_agent_message=last_agent_message,
        event_counts=dict(sorted(counts.items())),
        tool_call_count=counts.get("tool_call", 0),
        tool_output_count=counts.get("tool_output", 0),
        error_messages=error_messages,
        malformed_event_count=malformed_event_count,
        has_agent_message=last_agent_message is not None,
        stderr_preview=stderr_preview,
    )


def _last_agent_message(events: list[CodexRuntimeEvent]) -> str | None:
    for event in reversed(events):
        if event.kind != "message":
            continue
        if event.role not in {None, "assistant", "agent"}:
            continue
        if event.text.strip():
            return event.text
    return None


def _require_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value
