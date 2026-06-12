"""Codex group-chat candidate parsing and projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from isotope.agents.loop.conversation import AgentConversationMessage


GROUP_CHAT_INTENTS = {"respond", "interrupt", "internal_note", "silent"}


@dataclass(frozen=True)
class CodexGroupCandidate:
    candidate_id: str
    workspace_id: str
    channel_id: str
    member_id: str
    display_name: str
    resume_session_id: str
    event_index: int
    intent: str
    summary: str
    priority: int = 0
    state_lock: str | None = None
    transcript_ref: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "candidate_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.channel_id, "channel_id")
        _require_text(self.member_id, "member_id")
        _require_text(self.display_name, "display_name")
        _require_text(self.resume_session_id, "resume_session_id")
        if isinstance(self.event_index, bool) or not isinstance(self.event_index, int):
            raise ValueError("event_index must be an integer")
        if self.intent not in GROUP_CHAT_INTENTS:
            raise ValueError(
                "GROUP_CHAT_INTENT must be respond, interrupt, internal_note, or silent"
            )
        _require_text(self.summary, "summary")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("priority must be an integer")
        if self.priority < 0:
            raise ValueError("priority must be non-negative")
        if self.state_lock is not None:
            _require_text(self.state_lock, "state_lock")
        if not isinstance(self.transcript_ref, dict):
            raise ValueError("transcript_ref must be a dict")

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "workspace_id": self.workspace_id,
            "channel_id": self.channel_id,
            "member_id": self.member_id,
            "display_name": self.display_name,
            "resume_session_id": self.resume_session_id,
            "event_index": self.event_index,
            "intent": self.intent,
            "summary": self.summary,
            "priority": self.priority,
            "transcript_ref": dict(self.transcript_ref),
        }
        if self.state_lock is not None:
            payload["state_lock"] = self.state_lock
        return payload


def parse_codex_group_candidate(
    *,
    text: str,
    workspace_id: str,
    channel_id: str,
    member_id: str,
    display_name: str,
    resume_session_id: str,
    event_index: int,
    transcript_ref: dict[str, Any],
) -> CodexGroupCandidate | None:
    markers = _marker_values(text)
    if "GROUP_CHAT_INTENT" not in markers:
        return None
    intent = markers["GROUP_CHAT_INTENT"].strip()
    summary = markers.get("GROUP_CHAT_SUMMARY", "").strip()
    priority_text = markers.get("GROUP_CHAT_PRIORITY", "0").strip()
    state_lock = markers.get("GROUP_CHAT_STATE_LOCK", "").strip() or None
    if intent not in GROUP_CHAT_INTENTS:
        raise ValueError(
            "GROUP_CHAT_INTENT must be respond, interrupt, internal_note, or silent"
        )
    if not summary:
        raise ValueError("GROUP_CHAT_SUMMARY must be non-empty")
    try:
        priority = int(priority_text)
    except ValueError as exc:
        raise ValueError("GROUP_CHAT_PRIORITY must be an integer") from exc
    return CodexGroupCandidate(
        candidate_id=f"candidate_{member_id}_{resume_session_id}_{event_index}_{intent}",
        workspace_id=workspace_id,
        channel_id=channel_id,
        member_id=member_id,
        display_name=display_name,
        resume_session_id=resume_session_id,
        event_index=event_index,
        intent=intent,
        summary=summary,
        priority=priority,
        state_lock=state_lock,
        transcript_ref=dict(transcript_ref),
    )


def candidate_to_agent_message(candidate: CodexGroupCandidate) -> AgentConversationMessage:
    return AgentConversationMessage(
        message_id=candidate.candidate_id,
        agent_id=candidate.member_id,
        intent=candidate.intent,
        summary=candidate.summary,
        priority=candidate.priority,
        interrupt_reason=(
            candidate.summary if candidate.intent == "interrupt" else None
        ),
        state_lock=candidate.state_lock,
        metadata={
            "source": "codex_group_candidate",
            "workspace_id": candidate.workspace_id,
            "channel_id": candidate.channel_id,
            "display_name": candidate.display_name,
            "resume_session_id": candidate.resume_session_id,
            "event_index": candidate.event_index,
            "transcript_ref": dict(candidate.transcript_ref),
        },
    )


def _marker_values(text: str) -> dict[str, str]:
    markers: dict[str, str] = {}
    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        if key.startswith("GROUP_CHAT_"):
            markers[key] = value.strip()
    return markers


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
