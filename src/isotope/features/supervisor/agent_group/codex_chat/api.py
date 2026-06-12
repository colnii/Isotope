"""Endpoint-facing helpers for Codex-backed Agent Group Chat."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from isotope.features.supervisor.agent_group.runtime import AgentGroupRuntime
from isotope.features.supervisor.registry.session_lookup import (
    find_codex_session_snapshot,
)
from isotope.integrations.codex.transcript import read_codex_transcript_page

from .contracts import ConnectedCodexMember, CoordinatorDecision
from .runtime import CodexGroupChatRuntime


def list_agent_groups_payload(state_root: Path | str) -> dict[str, Any]:
    return AgentGroupRuntime(state_root).list_groups()


def agent_group_payload(state_root: Path | str, group_id: str) -> dict[str, Any]:
    group_payload = AgentGroupRuntime(state_root).list_group(group_id)
    chat_runtime = CodexGroupChatRuntime(state_root)
    group_payload["connected_members"] = [
        member.to_public_dict() for member in chat_runtime.store.list_members(group_id)
    ]
    group_payload["private_chat"] = [
        message.to_public_dict()
        for message in chat_runtime.store.list_private_chat(group_id)
    ]
    return group_payload


def add_codex_member_payload(
    state_root: Path | str,
    *,
    group_id: str,
    member_id: str,
    display_name: str,
    role: str,
    goal: str,
    send_policy: str,
    resume_session_id: str,
) -> dict[str, Any]:
    snapshot = find_codex_session_snapshot(
        codex_home=state_root,
        session_id=resume_session_id,
    )
    source_path = str(snapshot.source_path) if snapshot is not None else None
    now = _utc_now()
    member = ConnectedCodexMember(
        member_id=member_id,
        group_id=group_id,
        display_name=display_name,
        member_kind="codex_session",
        role=role,
        goal=goal,
        send_policy=send_policy,
        status="active",
        resume_session_id=resume_session_id,
        source_path=source_path,
        managed_record_id=None,
        transcript_policy={"page_size": 200, "raw_view": True},
        created_at=now,
        updated_at=now,
    )
    saved = CodexGroupChatRuntime(state_root).store.save_member(member)
    return {"status": "ok", "member": saved.to_public_dict()}


def transcript_payload(
    state_root: Path | str,
    *,
    session_id: str,
    offset: int,
    limit: int,
    include_raw: bool,
    latest: bool = False,
) -> dict[str, Any]:
    snapshot = find_codex_session_snapshot(codex_home=state_root, session_id=session_id)
    if snapshot is None:
        raise ValueError(f"Codex session not found: {session_id}")
    return read_codex_transcript_page(
        snapshot.source_path,
        offset=offset,
        limit=limit,
        include_raw=include_raw,
        latest=latest,
    )


def apply_chat_decision_payload(
    state_root: Path | str,
    *,
    group_id: str,
    message: str,
    mode: str,
) -> dict[str, Any]:
    runtime = CodexGroupChatRuntime(state_root)
    if mode == "interrupt":
        runtime.store.record_control(
            group_id=group_id,
            intent="interrupt",
            target="current_run",
            target_member_id=None,
            reason="User interrupted with a new message.",
        )
    decision = CoordinatorDecision(
        decision_id=f"decision_user_{uuid.uuid4().hex[:12]}",
        group_id=group_id,
        action="reply_private",
        target_member_id=None,
        content=message,
        reason="MVP records the user message in private coordinator chat.",
        created_at=_utc_now(),
    )
    return runtime.apply_decision(decision)


def control_payload(
    state_root: Path | str,
    *,
    group_id: str,
    intent: str,
    target: str,
    target_member_id: str | None,
    reason: str,
) -> dict[str, Any]:
    runtime = CodexGroupChatRuntime(state_root)
    if intent == "terminate" and target == "member" and target_member_id:
        return runtime.terminate_member(
            group_id=group_id,
            member_id=target_member_id,
            reason=reason,
        )
    if intent == "terminate" and target == "current_run":
        return runtime.stop_current_run(group_id=group_id, reason=reason)
    control = runtime.store.record_control(
        group_id=group_id,
        intent=intent,
        target=target,
        target_member_id=target_member_id,
        reason=reason,
    )
    return {"status": "ok", "control": control.to_public_dict()}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
