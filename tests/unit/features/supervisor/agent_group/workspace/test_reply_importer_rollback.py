from __future__ import annotations

import json
from pathlib import Path

from isotope.features.supervisor.agent_group.workspace.importer import (
    import_channel_member_replies,
)
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore


def test_import_channel_member_replies_hides_observations_superseded_by_codex_rollback(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(session_path, _rows_before_rollback())
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=str(session_path),
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )
    first_import = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )
    write_jsonl(session_path, [*_rows_before_rollback(), *_rollback_and_current_rows()])

    second_import = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )

    assert first_import[0]["status"] == "candidate_imported"
    assert second_import == [
        {
            "member_id": member.member_id,
            "display_name": "RNA训练",
            "status": "candidate_imported",
            "imported_count": 1,
            "candidate_count": 1,
            "published_count": 1,
            "last_imported_event_index": 4,
            "last_rollback_event_index": 3,
            "superseded_count": 1,
        }
    ]
    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)
    assert [message.summary for message in messages] == ["当前分支计划。"]
    audit_messages = store.list_messages(
        workspace.workspace_id,
        "channel",
        channel.channel_id,
        include_superseded=True,
    )
    assert [message.summary for message in audit_messages] == [
        "旧分支计划。",
        "Codex thread rolled back.",
        "当前分支计划。",
    ]
    loaded = store.list_channel_members(workspace.workspace_id, channel.channel_id)[0]
    assert loaded.transcript_policy["last_imported_event_index"] == 4
    assert loaded.transcript_policy["last_rollback_event_index"] == 3


def test_import_channel_member_replies_records_rollback_without_new_candidate(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(session_path, _rows_with_old_assistant_only())
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=str(session_path),
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 0,
        },
    )
    import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )
    write_jsonl(
        session_path,
        [
            *_rows_with_old_assistant_only(),
            {
                "type": "event_msg",
                "timestamp": "2026-06-12T00:00:02Z",
                "payload": {"type": "thread_rolled_back", "num_turns": 1},
            },
        ],
    )

    imports = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )

    assert imports == [
        {
            "member_id": member.member_id,
            "display_name": "RNA训练",
            "status": "thread_rolled_back",
            "imported_count": 0,
            "candidate_count": 0,
            "last_imported_event_index": 2,
            "last_rollback_event_index": 2,
            "superseded_count": 1,
        }
    ]
    assert store.list_messages(workspace.workspace_id, "channel", channel.channel_id) == []
    loaded = store.list_channel_members(workspace.workspace_id, channel.channel_id)[0]
    assert loaded.transcript_policy["last_imported_event_index"] == 2
    assert loaded.transcript_policy["last_rollback_event_index"] == 2


def _rows_before_rollback() -> list[dict[str, object]]:
    return [
        {"type": "session_meta", "payload": {"id": "session_training"}},
        {
            "type": "response_item",
            "timestamp": "2026-06-12T00:00:01Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": "先前分支。",
            },
        },
        _assistant_candidate_row(
            timestamp="2026-06-12T00:00:02Z",
            body="旧分支计划。",
            summary="旧分支计划。",
            priority=70,
        ),
    ]


def _rollback_and_current_rows() -> list[dict[str, object]]:
    return [
        {
            "type": "event_msg",
            "timestamp": "2026-06-12T00:00:03Z",
            "payload": {"type": "thread_rolled_back", "num_turns": 1},
        },
        _assistant_candidate_row(
            timestamp="2026-06-12T00:00:04Z",
            body="当前分支计划。",
            summary="当前分支计划。",
            priority=80,
        ),
    ]


def _rows_with_old_assistant_only() -> list[dict[str, object]]:
    return [
        {"type": "session_meta", "payload": {"id": "session_training"}},
        _assistant_candidate_row(
            timestamp="2026-06-12T00:00:01Z",
            body="旧分支计划。",
            summary="旧分支计划。",
            priority=70,
        ),
    ]


def _assistant_candidate_row(
    *,
    timestamp: str,
    body: str,
    summary: str,
    priority: int,
) -> dict[str, object]:
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": (
                f"{body}\n\n"
                "GROUP_CHAT_INTENT: respond\n"
                f"GROUP_CHAT_SUMMARY: {summary}\n"
                f"GROUP_CHAT_PRIORITY: {priority}\n"
            ),
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
