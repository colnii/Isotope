"""Public contracts for Supervisor Agent group chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GROUP_STATUSES = {"active", "paused", "done", "archived"}
MEMBER_STATUSES = {"active", "silent", "blocked", "done", "archived"}
MESSAGE_TYPES = {
    "task",
    "reply",
    "question",
    "observation",
    "summary",
    "interrupt",
    "status",
}
TURN_STATUSES = {"selected", "silent", "blocked", "error"}
RAW_GROUP_FIELDS = {
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
    "stderr",
    "stdin",
    "stdout",
}


@dataclass(frozen=True)
class AgentGroup:
    group_id: str
    title: str
    goal: str
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.group_id, "group_id")
        _require_text(self.title, "title")
        _require_text(self.goal, "goal")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        _require_choice(self.status, GROUP_STATUSES, "group status")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "title": self.title,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class AgentMember:
    member_id: str
    group_id: str
    name: str
    role: str
    goal: str
    model_profile: str = "default"
    allowed_capabilities: tuple[str, ...] = ()
    status: str = "active"

    def __post_init__(self) -> None:
        _require_text(self.member_id, "member_id")
        _require_text(self.group_id, "group_id")
        _require_text(self.name, "name")
        _require_text(self.role, "role")
        _require_text(self.goal, "goal")
        _require_text(self.model_profile, "model_profile")
        _require_choice(self.status, MEMBER_STATUSES, "member status")
        if not isinstance(self.allowed_capabilities, tuple):
            raise ValueError("allowed_capabilities must be a tuple")
        for capability_id in self.allowed_capabilities:
            _require_text(capability_id, "allowed_capability")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "group_id": self.group_id,
            "name": self.name,
            "role": self.role,
            "goal": self.goal,
            "model_profile": self.model_profile,
            "allowed_capabilities": list(self.allowed_capabilities),
            "status": self.status,
        }


@dataclass(frozen=True)
class AgentGroupMessage:
    message_id: str
    group_id: str
    turn_id: str
    from_member: str
    to_member: str | None
    message_type: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        _require_text(self.message_id, "message_id")
        _require_text(self.group_id, "group_id")
        _require_text(self.turn_id, "turn_id")
        _require_text(self.from_member, "from_member")
        if self.to_member is not None:
            _require_text(self.to_member, "to_member")
        _require_choice(self.message_type, MESSAGE_TYPES, "message_type")
        _require_text(self.summary, "summary")
        _require_text(self.created_at, "created_at")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        _reject_raw_group_payload(self.payload)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "group_id": self.group_id,
            "turn_id": self.turn_id,
            "from_member": self.from_member,
            "to_member": self.to_member,
            "message_type": self.message_type,
            "summary": self.summary,
            "payload": _copy_public_payload(self.payload),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class AgentTurn:
    turn_id: str
    group_id: str
    input_message_ids: tuple[str, ...]
    candidate_messages: tuple[str, ...]
    selected_message_ids: tuple[str, ...]
    queued_messages: tuple[dict[str, Any], ...]
    dropped_messages: tuple[dict[str, Any], ...]
    status: str
    supervisor_summary: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.turn_id, "turn_id")
        _require_text(self.group_id, "group_id")
        _require_choice(self.status, TURN_STATUSES, "turn status")
        _require_text(self.supervisor_summary, "supervisor_summary")
        _require_text(self.created_at, "created_at")
        for field_name in (
            "input_message_ids",
            "candidate_messages",
            "selected_message_ids",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            for item in value:
                _require_text(item, field_name)
        for field_name in ("queued_messages", "dropped_messages"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            for item in value:
                if not isinstance(item, dict):
                    raise ValueError(f"{field_name} items must be dicts")
                _reject_raw_group_payload(item)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "group_id": self.group_id,
            "input_message_ids": list(self.input_message_ids),
            "candidate_messages": list(self.candidate_messages),
            "selected_message_ids": list(self.selected_message_ids),
            "queued_messages": [
                _copy_public_payload(item) for item in self.queued_messages
            ],
            "dropped_messages": [
                _copy_public_payload(item) for item in self.dropped_messages
            ],
            "status": self.status,
            "supervisor_summary": self.supervisor_summary,
            "created_at": self.created_at,
        }


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_choice(value: object, choices: set[str], field_name: str) -> None:
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{field_name} must be one of: {options}")


def _reject_raw_group_payload(value: Any) -> None:
    if isinstance(value, dict):
        if RAW_GROUP_FIELDS.intersection(value):
            raise ValueError("raw group payload is not accepted")
        for nested in value.values():
            _reject_raw_group_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_group_payload(nested)


def _copy_public_payload(value: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_group_payload(value)
    return {str(key): _copy_public_value(nested) for key, nested in value.items()}


def _copy_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _copy_public_payload(value)
    if isinstance(value, list):
        return [_copy_public_value(item) for item in value]
    return value
