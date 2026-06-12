"""Rollback metadata helpers for workspace Codex conversations."""

from __future__ import annotations

from ..contracts import WorkspaceConversationMessage


ROLLBACK_STATUS_KIND = "codex_thread_rolled_back"


def codex_rollback_superseded_message_ids(
    messages: list[WorkspaceConversationMessage],
) -> set[str]:
    superseded: set[str] = set()
    for message in messages:
        if not is_codex_rollback_status(message):
            continue
        value = message.payload.get("superseded_message_ids")
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, str) and item.strip():
                superseded.add(item)
    return superseded


def is_codex_rollback_status(message: WorkspaceConversationMessage) -> bool:
    return (
        message.message_type == "status"
        and message.payload.get("status_kind") == ROLLBACK_STATUS_KIND
    )
