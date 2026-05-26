"""Agent-to-agent conversation message contract and turn arbiter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


VISIBLE_INTENTS = {"respond", "interrupt"}
INTERNAL_INTENTS = {"internal_note", "silent"}
INTENT_RANK = {
    "interrupt": 0,
    "respond": 1,
    "internal_note": 2,
    "silent": 3,
}
RAW_CONVERSATION_FIELDS = {
    "api_key",
    "artifact_content",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_artifact_content",
    "raw_content",
    "raw_prompt",
    "raw_response",
    "stdout",
    "stderr",
    "stdin",
}


@dataclass(frozen=True)
class AgentConversationMessage:
    """One agent's candidate utterance before arbiter selection."""

    message_id: str
    agent_id: str
    intent: str
    summary: str
    priority: int = 0
    interrupt_reason: str | None = None
    state_lock: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_string(self.message_id, "message_id")
        _require_string(self.agent_id, "agent_id")
        _require_string(self.summary, "summary")
        if self.intent not in VISIBLE_INTENTS | INTERNAL_INTENTS:
            raise ValueError("intent must be respond, interrupt, internal_note, or silent")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("priority must be an integer")
        if self.interrupt_reason is not None:
            _require_string(self.interrupt_reason, "interrupt_reason")
        if self.intent == "interrupt" and not self.interrupt_reason:
            raise ValueError("interrupt messages require interrupt_reason")
        if self.state_lock is not None:
            _require_string(self.state_lock, "state_lock")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")
        _reject_raw_conversation_payload(self.metadata)

    @property
    def display(self) -> bool:
        return self.intent in VISIBLE_INTENTS

    def to_public_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "message_id": self.message_id,
            "agent_id": self.agent_id,
            "intent": self.intent,
            "summary": self.summary,
            "priority": self.priority,
            "display": self.display,
        }
        if self.interrupt_reason is not None:
            item["interrupt_reason"] = self.interrupt_reason
        if self.state_lock is not None:
            item["state_lock"] = self.state_lock
        if self.metadata:
            item["metadata"] = _copy_public_metadata(self.metadata)
        return item


def arbitrate_agent_conversation_turn(
    candidates: Iterable[AgentConversationMessage],
    *,
    turn_id: str,
    max_visible_messages: int,
) -> dict[str, Any]:
    """Select bounded agent messages for one conversation turn."""
    _require_string(turn_id, "turn_id")
    if isinstance(max_visible_messages, bool) or not isinstance(max_visible_messages, int):
        raise ValueError("max_visible_messages must be a positive integer")
    if max_visible_messages <= 0:
        raise ValueError("max_visible_messages must be a positive integer")

    ordered = sorted(
        list(candidates),
        key=lambda message: (
            INTENT_RANK[message.intent],
            -message.priority,
            message.message_id,
        ),
    )
    selected: list[AgentConversationMessage] = []
    deferred: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    claimed_locks: dict[str, str] = {}

    for message in ordered:
        if message.intent == "silent":
            dropped.append(_drop_record(message, "silent"))
            continue
        if not message.display:
            deferred.append(_defer_record(message, "visible_limit"))
            continue
        if message.state_lock is not None and message.state_lock in claimed_locks:
            deferred.append(_defer_record(message, "state_lock_conflict"))
            continue
        if message.display and len([item for item in selected if item.display]) >= max_visible_messages:
            deferred.append(_defer_record(message, "visible_limit"))
            continue
        selected.append(message)
        if message.state_lock is not None:
            claimed_locks[message.state_lock] = message.message_id

    visible_messages = [
        message.to_public_dict()
        for message in selected
        if message.display
    ]
    return {
        "kind": "agent_conversation_turn",
        "turn_id": turn_id,
        "status": "selected" if visible_messages else "silent",
        "visible_messages": visible_messages,
        "deferred_messages": deferred,
        "dropped_messages": dropped,
        "state_locks": list(claimed_locks),
        "safety": {
            "agent_conversation_interface": True,
            "bounded": True,
            "max_visible_messages": max_visible_messages,
            "arbiter": "deterministic_priority",
            "real_llm_provider": False,
        },
    }


def _defer_record(message: AgentConversationMessage, reason: str) -> dict[str, Any]:
    record = {
        "message_id": message.message_id,
        "agent_id": message.agent_id,
        "reason": reason,
    }
    if message.state_lock is not None:
        record["state_lock"] = message.state_lock
    return record


def _drop_record(message: AgentConversationMessage, reason: str) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "agent_id": message.agent_id,
        "reason": reason,
    }


def _copy_public_metadata(value: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_conversation_payload(value)
    return {
        str(key): _copy_public_value(nested)
        for key, nested in value.items()
    }


def _copy_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _copy_public_metadata(value)
    if isinstance(value, list):
        return [_copy_public_value(item) for item in value]
    return value


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _reject_raw_conversation_payload(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = RAW_CONVERSATION_FIELDS.intersection(value)
        if forbidden:
            raise ValueError("raw conversation payload is not accepted")
        for nested in value.values():
            _reject_raw_conversation_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_conversation_payload(nested)
