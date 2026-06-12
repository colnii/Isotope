"""Structured Codex runtime event contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CODEX_RUNTIME_EVENT_KINDS = {
    "message",
    "reasoning",
    "tool_call",
    "tool_output",
    "error",
    "status",
    "unknown",
}


@dataclass(frozen=True)
class CodexRuntimeEvent:
    kind: str
    title: str
    text: str
    event_index: int
    event_type: str = "unknown"
    item_type: str | None = None
    role: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in CODEX_RUNTIME_EVENT_KINDS:
            raise ValueError("unsupported codex runtime event kind")
        _require_string("title", self.title)
        _require_string("text", self.text)
        if not isinstance(self.event_index, int) or self.event_index < 0:
            raise ValueError("event_index must be a non-negative integer")
        _require_string("event_type", self.event_type)
        if self.item_type is not None:
            _require_string("item_type", self.item_type)
        if self.role is not None:
            _require_string("role", self.role)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "event_index": self.event_index,
            "event_type": self.event_type,
        }
        if self.item_type is not None:
            payload["item_type"] = self.item_type
        if self.role is not None:
            payload["role"] = self.role
        return payload


def _require_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value
