"""Contracts for Codex-backed Supervisor Agent Group Chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MEMBER_KINDS = {"codex_session", "internal_agent", "supervisor"}
SEND_POLICIES = {"auto", "confirm", "draft_only"}
CONNECTED_MEMBER_STATUSES = {
    "active",
    "running",
    "idle",
    "needs_user",
    "terminated",
    "blocked",
    "archived",
}
PRIVATE_CHAT_ROLES = {"user", "assistant", "system"}
COORDINATOR_ACTIONS = {
    "reply_group",
    "reply_private",
    "send_member",
    "draft_member_send",
    "wait",
    "record_gap",
}
CONTROL_INTENTS = {"queue", "interrupt", "terminate"}
CONTROL_TARGETS = {"current_run", "member"}
RAW_CODEX_CHAT_FIELDS = {
    "api_key",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_content",
    "raw_prompt",
    "raw_response",
    "secret",
    "stderr",
    "stdin",
    "stdout",
    "token",
}


@dataclass(frozen=True)
class ConnectedCodexMember:
    member_id: str
    group_id: str
    display_name: str
    member_kind: str
    role: str
    goal: str
    send_policy: str
    status: str
    resume_session_id: str | None
    source_path: str | None
    managed_record_id: str | None
    transcript_policy: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        _require_text(self.member_id, "member_id")
        _require_text(self.group_id, "group_id")
        _require_text(self.display_name, "display_name")
        _require_text(self.role, "role")
        _require_choice(self.member_kind, MEMBER_KINDS, "member_kind")
        _require_choice(self.send_policy, SEND_POLICIES, "send_policy")
        _require_choice(self.status, CONNECTED_MEMBER_STATUSES, "member status")
        _require_optional_text(self.resume_session_id, "resume_session_id")
        _require_optional_text(self.source_path, "source_path")
        _require_optional_text(self.managed_record_id, "managed_record_id")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        if not isinstance(self.transcript_policy, dict):
            raise ValueError("transcript_policy must be a dict")
        _reject_raw_codex_chat_payload(self.transcript_policy)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "group_id": self.group_id,
            "display_name": self.display_name,
            "member_kind": self.member_kind,
            "role": self.role,
            "goal": self.goal,
            "send_policy": self.send_policy,
            "status": self.status,
            "resume_session_id": self.resume_session_id,
            "source_path": self.source_path,
            "managed_record_id": self.managed_record_id,
            "transcript_policy": _copy_public_payload(self.transcript_policy),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class PrivateChatMessage:
    message_id: str
    group_id: str
    role: str
    content: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.message_id, "message_id")
        _require_text(self.group_id, "group_id")
        _require_choice(self.role, PRIVATE_CHAT_ROLES, "private chat role")
        _require_text(self.content, "content")
        _require_text(self.created_at, "created_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "group_id": self.group_id,
            "channel": "private_human_chat",
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CoordinatorDecision:
    decision_id: str
    group_id: str
    action: str
    target_member_id: str | None
    content: str
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.decision_id, "decision_id")
        _require_text(self.group_id, "group_id")
        _require_choice(self.action, COORDINATOR_ACTIONS, "decision action")
        _require_optional_text(self.target_member_id, "target_member_id")
        _require_text(self.content, "content")
        _require_text(self.reason, "reason")
        _require_text(self.created_at, "created_at")
        if self.action in {"send_member", "draft_member_send"} and not self.target_member_id:
            raise ValueError("target_member_id is required for member send decisions")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "group_id": self.group_id,
            "action": self.action,
            "target_member_id": self.target_member_id,
            "content": self.content,
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeControlRequest:
    control_id: str
    group_id: str
    intent: str
    target: str
    target_member_id: str | None
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.control_id, "control_id")
        _require_text(self.group_id, "group_id")
        _require_choice(self.intent, CONTROL_INTENTS, "control intent")
        _require_choice(self.target, CONTROL_TARGETS, "control target")
        _require_optional_text(self.target_member_id, "target_member_id")
        _require_text(self.reason, "reason")
        _require_text(self.created_at, "created_at")
        if self.target == "member" and not self.target_member_id:
            raise ValueError("target_member_id is required for member controls")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "group_id": self.group_id,
            "intent": self.intent,
            "target": self.target,
            "target_member_id": self.target_member_id,
            "reason": self.reason,
            "created_at": self.created_at,
        }


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_optional_text(value: object, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be null or a non-empty string")


def _require_choice(value: object, choices: set[str], field_name: str) -> None:
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{field_name} must be one of: {options}")


def _reject_raw_codex_chat_payload(value: Any) -> None:
    if isinstance(value, dict):
        if RAW_CODEX_CHAT_FIELDS.intersection(value):
            raise ValueError("raw codex chat payload is not accepted")
        for nested in value.values():
            _reject_raw_codex_chat_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_codex_chat_payload(nested)


def _copy_public_payload(value: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_codex_chat_payload(value)
    return {str(key): _copy_public_value(nested) for key, nested in value.items()}


def _copy_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _copy_public_payload(value)
    if isinstance(value, list):
        return [_copy_public_value(item) for item in value]
    return value
