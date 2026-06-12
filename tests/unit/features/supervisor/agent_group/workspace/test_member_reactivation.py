from __future__ import annotations

from isotope.features.supervisor.agent_group.workspace import api
from isotope.features.supervisor.agent_group.workspace import dispatcher
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore
from isotope.features.supervisor.registry.records import ManagedCodexRecord


def test_terminated_member_requires_explicit_reactivation_before_dispatch(
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
        goal="继续训练和提交链路。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=None,
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        status="terminated",
    )
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        return ManagedCodexRecord(
            record_id=f"managed-{len(resumed_calls)}",
            name=str(kwargs["name"]),
            cwd=str(kwargs["cwd"]),
            prompt=str(kwargs["prompt"]),
            command=("codex", "resume", str(kwargs["session_id"])),
            pid=1234 + len(resumed_calls),
            started_at="2026-06-12T00:00:00Z",
            log_path=str(
                codex_home
                / "supervisor"
                / "logs"
                / f"managed-{len(resumed_calls)}.log"
            ),
            status="resumed",
            backend="codex_exec_resume",
            resume_session_id=str(kwargs["session_id"]),
        )

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    stopped_payload = api.conversation_chat_payload(
        codex_home,
        workspace_id=workspace.workspace_id,
        conversation_id=channel.channel_id,
        message="这条消息不应唤醒已停止成员。",
        mode="queue",
    )

    assert stopped_payload["dispatches"] == []
    assert resumed_calls == []

    reactivated = api.update_channel_member_payload(
        codex_home,
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        send_policy=None,
        status="active",
        role=None,
        goal=None,
    )
    active_payload = api.conversation_chat_payload(
        codex_home,
        workspace_id=workspace.workspace_id,
        conversation_id=channel.channel_id,
        message="这条消息应恢复发送给成员。",
        mode="queue",
    )

    assert reactivated["member"]["status"] == "active"
    assert [call["session_id"] for call in resumed_calls] == ["session_training"]
    assert active_payload["dispatches"][0]["status"] == "sent"
