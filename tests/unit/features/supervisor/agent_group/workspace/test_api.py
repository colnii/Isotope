from __future__ import annotations

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
