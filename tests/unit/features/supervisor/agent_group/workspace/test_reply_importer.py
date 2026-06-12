from __future__ import annotations

import json
from pathlib import Path

from isotope.features.supervisor.agent_group.workspace.importer import (
    import_channel_member_replies,
)
from isotope.features.supervisor.agent_group.workspace.runtime_bridge import runtime_group_id
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore


def test_import_channel_member_replies_adds_member_observation_once(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_research"}},
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:01Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": "请同步当前进展。",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:02Z",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": {"cmd": "pytest -q"},
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:03Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "科研侧已经完成 readiness 审计，建议工程侧继续验证。",
                },
            },
        ],
    )
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.create_channel(
        workspace_id=workspace.workspace_id,
        name="rna",
        topic="同步科研和工程。",
    )
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="rna探索",
        role="科研探索",
        goal="给工程侧提供判断。",
        send_policy="auto",
        resume_session_id="session_research",
        source_path=str(session_path),
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        status="running",
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )

    imports = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )
    repeated = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )

    assert imports == [
        {
            "member_id": member.member_id,
            "display_name": "rna探索",
            "status": "imported",
            "imported_count": 1,
            "last_imported_event_index": 3,
        }
    ]
    assert repeated == []
    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)
    assert [(message.from_actor, message.message_type) for message in messages] == [
        (member.member_id, "member_observation")
    ]
    assert messages[0].summary == "科研侧已经完成 readiness 审计，建议工程侧继续验证。"
    assert messages[0].payload == {
        "member_id": member.member_id,
        "display_name": "rna探索",
        "resume_session_id": "session_research",
        "source_path": str(session_path),
        "runtime_group_id": runtime_group_id(workspace.workspace_id, channel.channel_id),
        "event_index": 3,
        "transcript_ref": {
            "session_id": "session_research",
            "event_index": 3,
            "offset": 3,
            "limit": 1,
        },
    }
    loaded = store.list_channel_members(workspace.workspace_id, channel.channel_id)[0]
    assert loaded.status == "idle"


def test_import_channel_member_replies_skips_existing_transcript_ref(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_research"}},
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:01Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": "请同步当前进展。",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:02Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "科研侧已经完成 readiness 审计。",
                },
            },
        ],
    )
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="rna探索",
        role="科研探索",
        goal="给工程侧提供判断。",
        send_policy="auto",
        resume_session_id="session_research",
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
    store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        from_actor=member.member_id,
        to_actor=None,
        message_type="member_observation",
        summary="科研侧已经完成 readiness 审计。",
        payload={
            "member_id": member.member_id,
            "resume_session_id": "session_research",
            "event_index": 2,
            "transcript_ref": {
                "session_id": "session_research",
                "event_index": 2,
                "offset": 2,
                "limit": 1,
            },
        },
    )

    imports = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )

    assert imports == []
    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)
    assert len(messages) == 1
    loaded = store.list_channel_members(workspace.workspace_id, channel.channel_id)[0]
    assert loaded.transcript_policy["last_imported_event_index"] == 2


def test_import_channel_member_replies_marks_empty_assistant_turn_idle(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_training"}},
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:01Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": "测试你是否可以选择沉默。",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:02Z",
                "payload": {"type": "reasoning"},
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:03Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "",
                },
            },
        ],
    )
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
        managed_record_id="managed-training",
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        status="running",
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 1,
        },
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
            "status": "silent",
            "imported_count": 0,
            "last_imported_event_index": 3,
        }
    ]
    assert store.list_messages(workspace.workspace_id, "channel", channel.channel_id) == []
    loaded = store.list_channel_members(workspace.workspace_id, channel.channel_id)[0]
    assert loaded.status == "idle"
    assert loaded.managed_record_id == "managed-training"
    assert loaded.transcript_policy["last_imported_event_index"] == 3


def test_import_channel_member_replies_sets_initial_baseline_without_old_messages(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_training"}},
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:01Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "这是加入群聊前的旧回复。",
                },
            },
        ],
    )
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

    imports = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )

    assert imports == []
    assert store.list_messages(workspace.workspace_id, "channel", channel.channel_id) == []
    loaded = store.list_channel_members(workspace.workspace_id, channel.channel_id)[0]
    assert loaded.member_id == member.member_id
    assert loaded.transcript_policy["last_imported_event_index"] == 1


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
