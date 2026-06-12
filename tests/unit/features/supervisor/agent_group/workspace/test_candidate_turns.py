from __future__ import annotations

from isotope.features.supervisor.agent_group.store import AgentGroupStore
from isotope.features.supervisor.agent_group.workspace.coordination.candidates import (
    CodexGroupCandidate,
)
from isotope.features.supervisor.agent_group.workspace.coordination.inbox import (
    MemberInboxStore,
)
from isotope.features.supervisor.agent_group.workspace.coordination.turns import (
    run_channel_candidate_turn,
)
from isotope.features.supervisor.agent_group.workspace.runtime_bridge import (
    runtime_group_id,
)
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore


def test_channel_candidate_turn_publishes_selected_visible_reply(tmp_path):
    codex_home = tmp_path / ".codex"
    store, workspace, channel, training_member, research_member = (
        _workspace_with_two_members(codex_home, tmp_path / "AI_Camp_RNA_2026")
    )
    selected = _candidate(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=training_member.member_id,
        display_name=training_member.display_name,
        resume_session_id="session_training",
        event_index=7,
        intent="respond",
        summary="工程侧建议先补 schema readiness smoke。",
        priority=70,
    )
    lower = _candidate(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=research_member.member_id,
        display_name=research_member.display_name,
        resume_session_id="session_research",
        event_index=8,
        intent="respond",
        summary="科研侧可以稍后同步。",
        priority=10,
    )

    result = run_channel_candidate_turn(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
        candidates=[selected, lower],
        max_visible_messages=1,
    )

    assert result["status"] == "selected"
    assert [item["candidate_id"] for item in result["published_messages"]] == [
        selected.candidate_id
    ]
    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)
    assert [message.summary for message in messages] == [selected.summary]
    assert messages[0].message_type == "member_observation"
    assert messages[0].payload["candidate_id"] == selected.candidate_id

    group_store = AgentGroupStore(codex_home)
    group_id = runtime_group_id(workspace.workspace_id, channel.channel_id)
    group_messages = group_store.list_group_messages(group_id)
    assert group_messages[-1].summary == selected.summary
    assert group_store.list_turns(group_id)[-1].status == "selected"


def test_channel_candidate_turn_drops_silent_candidate_without_public_message(tmp_path):
    codex_home = tmp_path / ".codex"
    store, workspace, channel, training_member, _research_member = (
        _workspace_with_two_members(codex_home, tmp_path / "AI_Camp_RNA_2026")
    )
    silent = _candidate(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=training_member.member_id,
        display_name=training_member.display_name,
        resume_session_id="session_training",
        event_index=7,
        intent="silent",
        summary="当前不需要公开发言，继续训练侧工作。",
        priority=0,
    )

    result = run_channel_candidate_turn(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
        candidates=[silent],
        max_visible_messages=1,
    )

    assert result["status"] == "silent"
    assert result["published_messages"] == []
    assert store.list_messages(workspace.workspace_id, "channel", channel.channel_id) == []
    group_id = runtime_group_id(workspace.workspace_id, channel.channel_id)
    turn = AgentGroupStore(codex_home).list_turns(group_id)[-1]
    assert turn.dropped_messages == (
        {
            "message_id": silent.candidate_id,
            "agent_id": training_member.member_id,
            "reason": "silent",
        },
    )


def test_channel_candidate_turn_enqueues_selected_reply_for_other_members(tmp_path):
    codex_home = tmp_path / ".codex"
    store, workspace, channel, training_member, research_member = (
        _workspace_with_two_members(codex_home, tmp_path / "AI_Camp_RNA_2026")
    )
    selected = _candidate(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=research_member.member_id,
        display_name=research_member.display_name,
        resume_session_id="session_research",
        event_index=11,
        intent="respond",
        summary="科研侧建议先做 schema readiness 审计。",
        priority=80,
    )

    result = run_channel_candidate_turn(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
        candidates=[selected],
        max_visible_messages=1,
    )

    pending = MemberInboxStore(codex_home).list_pending(
        workspace.workspace_id,
        channel.channel_id,
        training_member.member_id,
    )
    assert result["enqueued_count"] == 1
    assert len(pending) == 1
    assert pending[0].from_actor == research_member.member_id
    assert pending[0].summary == "科研侧建议先做 schema readiness 审计。"


def _workspace_with_two_members(codex_home, workspace_root):
    workspace_root.mkdir()
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    training_member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="推进训练任务。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=None,
        managed_record_id=None,
    )
    research_member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="rna探索",
        role="科研探索",
        goal="探索科研方向。",
        send_policy="auto",
        resume_session_id="session_research",
        source_path=None,
        managed_record_id=None,
    )
    return store, workspace, channel, training_member, research_member


def _candidate(
    *,
    workspace_id: str,
    channel_id: str,
    member_id: str,
    display_name: str,
    resume_session_id: str,
    event_index: int,
    intent: str,
    summary: str,
    priority: int,
) -> CodexGroupCandidate:
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
        state_lock=None,
        transcript_ref={"session_id": resume_session_id, "event_index": event_index},
    )
