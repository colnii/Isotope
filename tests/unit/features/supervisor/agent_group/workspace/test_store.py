from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore


def test_store_creates_default_workspace_channel_and_coordinator_dm(tmp_path):
    root_path = tmp_path / "AI_Camp_RNA_2026"
    root_path.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")

    workspace = store.ensure_default_workspace(root_path=root_path)

    assert workspace.title == "AI_Camp_RNA_2026"
    assert workspace.root_path == str(root_path)
    channels = store.list_channels(workspace.workspace_id)
    dms = store.list_direct_messages(workspace.workspace_id)
    assert [channel.name for channel in channels] == ["general"]
    assert [dm.dm_kind for dm in dms] == ["coordinator"]


def test_store_adds_channel_member_and_rejects_duplicate_session(tmp_path):
    root_path = tmp_path / "repo"
    root_path.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")
    workspace = store.ensure_default_workspace(root_path=root_path)
    channel = store.create_channel(
        workspace_id=workspace.workspace_id,
        name="rna-research",
        topic="Research direction",
    )

    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="Research Codex",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy="confirm",
        resume_session_id="session_research",
        source_path="/tmp/session_research.jsonl",
        managed_record_id=None,
    )

    assert member.display_name == "Research Codex"
    assert (
        store.list_channel_members(workspace.workspace_id, channel.channel_id)[
            0
        ].send_policy
        == "confirm"
    )
    with pytest.raises(ValueError, match="already present"):
        store.add_channel_member(
            workspace_id=workspace.workspace_id,
            channel_id=channel.channel_id,
            display_name="Research Codex duplicate",
            role="Explore RNA strategy.",
            goal="Find research directions.",
            send_policy="confirm",
            resume_session_id="session_research",
            source_path="/tmp/session_research.jsonl",
            managed_record_id=None,
        )


def test_store_updates_member_permission_and_records_message_and_control(tmp_path):
    root_path = tmp_path / "repo"
    root_path.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")
    workspace = store.ensure_default_workspace(root_path=root_path)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="Engineering Codex",
        role="Push engineering.",
        goal="Keep implementation moving.",
        send_policy="auto",
        resume_session_id="session_engineering",
        source_path=None,
        managed_record_id="managed_engineering",
    )

    updated = store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        send_policy="draft_only",
        status="terminated",
    )
    message = store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        from_actor="user",
        to_actor=None,
        message_type="user",
        summary="Stop engineering lane.",
        payload={"mode": "interrupt"},
    )
    control = store.record_control(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        intent="terminate",
        target="member",
        target_member_id=member.member_id,
        reason="User pressed member Stop.",
    )

    assert updated.send_policy == "draft_only"
    assert updated.status == "terminated"
    assert (
        store.list_messages(workspace.workspace_id, "channel", channel.channel_id)[
            0
        ].message_id
        == message.message_id
    )
    assert (
        store.list_control_events(workspace.workspace_id)[0]["payload"]["control_id"]
        == control.control_id
    )


def test_store_collapses_duplicate_member_observations_by_transcript_ref(tmp_path):
    root_path = tmp_path / "repo"
    root_path.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")
    workspace = store.ensure_default_workspace(root_path=root_path)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="Engineering",
        goal="Keep implementation moving.",
        send_policy="auto",
        resume_session_id="session_training",
        source_path="/tmp/session_training.jsonl",
        managed_record_id=None,
    )
    payload = {
        "member_id": member.member_id,
        "resume_session_id": "session_training",
        "event_index": 42,
        "transcript_ref": {
            "session_id": "session_training",
            "event_index": 42,
            "offset": 42,
            "limit": 1,
        },
    }
    first = store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        from_actor=member.member_id,
        to_actor=None,
        message_type="member_observation",
        summary="2",
        payload=payload,
    )
    store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        from_actor=member.member_id,
        to_actor=None,
        message_type="member_observation",
        summary="2",
        payload=payload,
    )

    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)

    assert [message.message_id for message in messages] == [first.message_id]


def test_store_hides_messages_superseded_by_codex_rollback_by_default(tmp_path):
    root_path = tmp_path / "repo"
    root_path.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")
    workspace = store.ensure_default_workspace(root_path=root_path)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="Engineering",
        goal="Keep implementation moving.",
        send_policy="auto",
        resume_session_id="session_training",
        source_path="/tmp/session_training.jsonl",
        managed_record_id=None,
    )
    old_message = store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        from_actor=member.member_id,
        to_actor=None,
        message_type="member_observation",
        summary="旧分支回复。",
        payload={
            "member_id": member.member_id,
            "resume_session_id": "session_training",
            "event_index": 42,
            "transcript_ref": {
                "session_id": "session_training",
                "event_index": 42,
                "offset": 42,
                "limit": 1,
            },
        },
    )
    rollback_status = store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        from_actor=member.member_id,
        to_actor=None,
        message_type="status",
        summary="Codex thread rolled back.",
        payload={
            "status_kind": "codex_thread_rolled_back",
            "member_id": member.member_id,
            "resume_session_id": "session_training",
            "rollback_event_index": 43,
            "superseded_message_ids": [old_message.message_id],
        },
    )

    default_messages = store.list_messages(
        workspace.workspace_id,
        "channel",
        channel.channel_id,
    )
    audit_messages = store.list_messages(
        workspace.workspace_id,
        "channel",
        channel.channel_id,
        include_superseded=True,
    )

    assert default_messages == []
    assert [message.message_id for message in audit_messages] == [
        old_message.message_id,
        rollback_status.message_id,
    ]


def test_store_updates_workspace_title_and_root_path(tmp_path):
    root_path = tmp_path / "repo"
    updated_root = tmp_path / "AI_Camp_RNA_2026"
    root_path.mkdir()
    updated_root.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")
    workspace = store.ensure_default_workspace(root_path=root_path)

    updated = store.update_workspace(
        workspace_id=workspace.workspace_id,
        title="RNA 工作区",
        root_path=updated_root,
    )
    loaded = store.load_workspace(workspace.workspace_id)

    assert updated.title == "RNA 工作区"
    assert updated.root_path == str(updated_root)
    assert loaded.title == "RNA 工作区"
    assert loaded.root_path == str(updated_root)
    assert len(store.list_workspaces()) == 1
