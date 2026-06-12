"""Contracts for workspace-based Agent Group Chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


WORKSPACE_STATUSES = {"active", "archived", "error"}
CHANNEL_STATUSES = {"active", "archived", "error"}
DM_KINDS = {"coordinator", "codex_member"}
MEMBER_KINDS = {"codex_session", "internal_agent", "supervisor"}
SEND_POLICIES = {"auto", "confirm", "draft_only"}
MEMBER_STATUSES = {
    "active",
    "running",
    "idle",
    "needs_user",
    "terminated",
    "blocked",
    "archived",
}
CONVERSATION_TYPES = {"channel", "dm"}
MESSAGE_TYPES = {
    "user",
    "model_reply",
    "private_note",
    "draft_send",
    "sent_to_member",
    "member_observation",
    "runtime_control",
    "status",
    "approval",
    "error",
}
CONTROL_INTENTS = {"queue", "interrupt", "terminate"}
CONTROL_TARGETS = {"current_run", "member"}
TRIGGER_KIND_USER_MESSAGE = "user_message"
TRIGGER_KIND_MEMBER_OBSERVATION_RELAY = "member_observation_relay"
MAX_MEMBER_OBSERVATION_RELAY_DEPTH = 1
RAW_WORKSPACE_FIELDS = {
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


def relay_depth_from_payload(payload: dict[str, Any]) -> int:
    value = payload.get("relay_depth")
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


@dataclass(frozen=True)
class AgentWorkspace:
    workspace_id: str
    title: str
    root_path: str
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.title, "title")
        _require_text(self.root_path, "root_path")
        _require_choice(self.status, WORKSPACE_STATUSES, "workspace status")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "title": self.title,
            "root_path": self.root_path,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class AgentChannel:
    channel_id: str
    workspace_id: str
    name: str
    topic: str
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.channel_id, "channel_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.name, "name")
        _require_choice(self.status, CHANNEL_STATUSES, "channel status")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "topic": self.topic,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class AgentDirectMessage:
    dm_id: str
    workspace_id: str
    dm_kind: str
    title: str
    target_member_id: str | None
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.dm_id, "dm_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_choice(self.dm_kind, DM_KINDS, "dm_kind")
        _require_text(self.title, "title")
        _require_optional_text(self.target_member_id, "target_member_id")
        _require_choice(self.status, CHANNEL_STATUSES, "dm status")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        if self.dm_kind == "codex_member" and not self.target_member_id:
            raise ValueError("target_member_id is required for codex_member DM")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "dm_id": self.dm_id,
            "workspace_id": self.workspace_id,
            "dm_kind": self.dm_kind,
            "title": self.title,
            "target_member_id": self.target_member_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ChannelMembership:
    member_id: str
    workspace_id: str
    channel_id: str
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
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.channel_id, "channel_id")
        _require_text(self.display_name, "display_name")
        _require_choice(self.member_kind, MEMBER_KINDS, "member_kind")
        _require_text(self.role, "role")
        _require_choice(self.send_policy, SEND_POLICIES, "send_policy")
        _require_choice(self.status, MEMBER_STATUSES, "member status")
        _require_optional_text(self.resume_session_id, "resume_session_id")
        _require_optional_text(self.source_path, "source_path")
        _require_optional_text(self.managed_record_id, "managed_record_id")
        if not isinstance(self.transcript_policy, dict):
            raise ValueError("transcript_policy must be a dict")
        _reject_raw_workspace_payload(self.transcript_policy)
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "workspace_id": self.workspace_id,
            "channel_id": self.channel_id,
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
class WorkspaceConversationMessage:
    message_id: str
    workspace_id: str
    conversation_type: str
    conversation_id: str
    from_actor: str
    to_actor: str | None
    message_type: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        _require_text(self.message_id, "message_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_choice(self.conversation_type, CONVERSATION_TYPES, "conversation_type")
        _require_text(self.conversation_id, "conversation_id")
        _require_text(self.from_actor, "from_actor")
        _require_optional_text(self.to_actor, "to_actor")
        _require_choice(self.message_type, MESSAGE_TYPES, "message_type")
        _require_text(self.summary, "summary")
        _require_text(self.created_at, "created_at")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        _reject_raw_workspace_payload(self.payload)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "workspace_id": self.workspace_id,
            "conversation_type": self.conversation_type,
            "conversation_id": self.conversation_id,
            "from_actor": self.from_actor,
            "to_actor": self.to_actor,
            "message_type": self.message_type,
            "summary": self.summary,
            "payload": _copy_public_payload(self.payload),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class WorkspaceRuntimeControl:
    control_id: str
    workspace_id: str
    conversation_type: str
    conversation_id: str
    intent: str
    target: str
    target_member_id: str | None
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.control_id, "control_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_choice(self.conversation_type, CONVERSATION_TYPES, "conversation_type")
        _require_text(self.conversation_id, "conversation_id")
        _require_choice(self.intent, CONTROL_INTENTS, "control intent")
        _require_choice(self.target, CONTROL_TARGETS, "control target")
        _require_optional_text(self.target_member_id, "target_member_id")
        _require_text(self.reason, "reason")
        _require_text(self.created_at, "created_at")
        if self.target == "member" and not self.target_member_id:
            raise ValueError("target_member_id is required for member target")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "workspace_id": self.workspace_id,
            "conversation_type": self.conversation_type,
            "conversation_id": self.conversation_id,
            "intent": self.intent,
            "target": self.target,
            "target_member_id": self.target_member_id,
            "reason": self.reason,
            "created_at": self.created_at,
        }


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_optional_text(value: object, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be null or a non-empty string")


def _require_choice(value: object, choices: set[str], field_name: str) -> None:
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{field_name} must be one of: {options}")


def _reject_raw_workspace_payload(value: Any) -> None:
    if isinstance(value, dict):
        if RAW_WORKSPACE_FIELDS.intersection(value):
            raise ValueError("raw workspace payload is not accepted")
        for nested in value.values():
            _reject_raw_workspace_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_workspace_payload(nested)


def _copy_public_payload(value: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_workspace_payload(value)
    return {str(key): _copy_public_value(nested) for key, nested in value.items()}


def _copy_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _copy_public_payload(value)
    if isinstance(value, list):
        return [_copy_public_value(item) for item in value]
    return value
