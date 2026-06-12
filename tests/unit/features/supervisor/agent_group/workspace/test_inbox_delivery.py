from __future__ import annotations

from isotope.features.supervisor.agent_group.workspace import api
from isotope.features.supervisor.agent_group.workspace import dispatcher
from isotope.features.supervisor.agent_group.workspace.coordination.inbox import (
    MemberInboxStore,
)
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore
from isotope.features.supervisor.registry.records import ManagedCodexRecord


def test_conversation_chat_queues_for_running_auto_member_without_resume(
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
        managed_record_id="managed-training",
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        status="running",
    )
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        raise AssertionError("running members must not be resumed immediately")

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    payload = api.conversation_chat_payload(
        codex_home,
        workspace_id=workspace.workspace_id,
        conversation_id=channel.channel_id,
        message="请同步当前进展。",
        mode="queue",
    )

    assert resumed_calls == []
    assert payload["dispatches"] == [
        {
            "member_id": member.member_id,
            "display_name": "RNA训练",
            "send_policy": "auto",
            "status": "queued",
            "managed_record_id": "managed-training",
            "resume_session_id": "session_training",
            "pending_count": 1,
        }
    ]


def test_workspace_payload_reports_idle_member_inbox_without_draining(tmp_path, monkeypatch):
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
    inbox = MemberInboxStore(codex_home)
    inbox.enqueue(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        target_member_id=member.member_id,
        source_message_id="msg_user_1",
        from_actor="用户",
        summary="请同步当前进展。",
        payload={"runtime_group_id": "group_workspace_1"},
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

    payload = api.workspace_payload(codex_home, workspace.workspace_id)
    repeated = api.workspace_payload(codex_home, workspace.workspace_id)

    assert resumed_calls == []
    assert payload["inbox"]["pending_counts"].get(member.member_id, 0) == 1
    assert repeated["inbox"]["pending_counts"].get(member.member_id, 0) == 1
    assert len(inbox.list_pending(workspace.workspace_id, channel.channel_id, member.member_id)) == 1


def test_workspace_tick_drains_idle_member_inbox_once(tmp_path, monkeypatch):
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
    inbox = MemberInboxStore(codex_home)
    inbox.enqueue(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        target_member_id=member.member_id,
        source_message_id="msg_user_1",
        from_actor="用户",
        summary="请同步当前进展。",
        payload={"runtime_group_id": "group_workspace_1"},
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

    payload = api.workspace_tick_payload(codex_home, workspace.workspace_id)
    repeated = api.workspace_tick_payload(codex_home, workspace.workspace_id)

    assert len(resumed_calls) == 1
    assert "待处理群聊消息" in str(resumed_calls[0]["prompt"])
    assert "请同步当前进展。" in str(resumed_calls[0]["prompt"])
    assert payload["inbox"]["pending_counts"].get(member.member_id, 0) == 0
    assert repeated["inbox"]["pending_counts"].get(member.member_id, 0) == 0
    assert inbox.list_pending(workspace.workspace_id, channel.channel_id, member.member_id) == []
