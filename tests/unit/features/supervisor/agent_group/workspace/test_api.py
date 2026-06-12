from __future__ import annotations

import json
from pathlib import Path

from isotope.features.supervisor.agent_group.workspace import api
from isotope.features.supervisor.agent_group.workspace import dispatcher
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore
from isotope.features.supervisor.registry.records import ManagedCodexRecord


def test_conversation_chat_dispatches_auto_members_and_surfaces_drafts(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.create_channel(
        workspace_id=workspace.workspace_id,
        name="rna",
        topic="同步科研和训练进展。",
    )
    auto_member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练和提交链路。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=None,
        managed_record_id=None,
    )
    draft_member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="rna探索",
        role="科研探索",
        goal="寻找全局优化点。",
        send_policy="draft_only",
        resume_session_id="session_research",
        source_path=None,
        managed_record_id=None,
    )
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        return ManagedCodexRecord(
            record_id="managed-training",
            name=str(kwargs["name"]),
            cwd=str(kwargs["cwd"]),
            prompt=str(kwargs["prompt"]),
            command=("codex", "resume", "session_training"),
            pid=1234,
            started_at="2026-06-12T00:00:00Z",
            log_path=str(codex_home / "supervisor" / "logs" / "managed-training.log"),
            status="resumed",
            backend="codex_exec_resume",
            resume_session_id=str(kwargs["session_id"]),
        )

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    payload = api.conversation_chat_payload(
        codex_home,
        workspace_id=workspace.workspace_id,
        conversation_id=channel.channel_id,
        message="请同步当前进展。",
        mode="queue",
    )

    assert payload["status"] == "ok"
    assert payload["message"]["summary"] == "请同步当前进展。"
    assert payload["dispatches"] == [
        {
            "member_id": auto_member.member_id,
            "display_name": "RNA训练",
            "send_policy": "auto",
            "status": "sent",
            "managed_record_id": "managed-training",
            "resume_session_id": "session_training",
        },
        {
            "member_id": draft_member.member_id,
            "display_name": "rna探索",
            "send_policy": "draft_only",
            "status": "draft",
            "managed_record_id": None,
            "resume_session_id": "session_research",
        },
    ]
    assert resumed_calls[0]["codex_home"] == codex_home
    assert resumed_calls[0]["cwd"] == workspace.root_path
    assert resumed_calls[0]["name"] == "RNA训练"
    assert resumed_calls[0]["session_id"] == "session_training"
    assert "请同步当前进展。" in resumed_calls[0]["prompt"]

    members = {
        member.member_id: member
        for member in store.list_channel_members(workspace.workspace_id, channel.channel_id)
    }
    assert members[auto_member.member_id].status == "running"
    assert members[auto_member.member_id].managed_record_id == "managed-training"
    assert members[draft_member.member_id].status == "needs_user"

    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)
    assert [message.message_type for message in messages] == [
        "user",
        "sent_to_member",
        "draft_send",
    ]
    assert messages[1].to_actor == auto_member.member_id
    assert "已发送给 RNA训练" in messages[1].summary
    assert messages[2].to_actor == draft_member.member_id
    assert "等待确认" in messages[2].summary


def test_workspace_payload_imports_codex_member_replies(tmp_path):
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
                "timestamp": "2026-06-12T00:00:00Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": "收到群聊消息。",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:01Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "工程侧已经开始验证训练链路。",
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
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )

    payload = api.workspace_payload(codex_home, workspace.workspace_id)

    assert payload["imports"] == [
        {
            "member_id": member.member_id,
            "display_name": "RNA训练",
            "status": "imported",
            "imported_count": 1,
            "last_imported_event_index": 2,
        }
    ]
    assert [
        (message["from_actor"], message["message_type"], message["summary"])
        for message in payload["messages"]
    ] == [
        (
            member.member_id,
            "member_observation",
            "工程侧已经开始验证训练链路。",
        )
    ]


def test_conversation_chat_marks_import_baseline_before_auto_resume(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
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
        source_path=None,
        managed_record_id=None,
    )
    calls: list[str] = []

    def fake_baseline(**kwargs):
        calls.append(f"baseline:{kwargs['member'].member_id}")
        return kwargs["member"]

    def fake_resume_managed_codex(**kwargs):
        calls.append(f"resume:{kwargs['session_id']}")
        return ManagedCodexRecord(
            record_id="managed-training",
            name=str(kwargs["name"]),
            cwd=str(kwargs["cwd"]),
            prompt=str(kwargs["prompt"]),
            command=("codex", "resume", "session_training"),
            pid=1234,
            started_at="2026-06-12T00:00:00Z",
            log_path=str(codex_home / "supervisor" / "logs" / "managed-training.log"),
            status="resumed",
            backend="codex_exec_resume",
            resume_session_id=str(kwargs["session_id"]),
        )

    monkeypatch.setattr(
        dispatcher,
        "mark_member_reply_import_baseline",
        fake_baseline,
    )
    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    api.conversation_chat_payload(
        codex_home,
        workspace_id=workspace.workspace_id,
        conversation_id=channel.channel_id,
        message="请同步当前进展。",
        mode="queue",
    )

    assert calls == [f"baseline:{member.member_id}", "resume:session_training"]


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
