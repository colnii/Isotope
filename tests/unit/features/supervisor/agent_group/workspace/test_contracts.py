from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.workspace.contracts import (
    AgentChannel,
    AgentDirectMessage,
    AgentWorkspace,
    ChannelMembership,
    WorkspaceConversationMessage,
)


def test_workspace_channel_dm_and_membership_public_shapes():
    workspace = AgentWorkspace(
        workspace_id="workspace_rna",
        title="AI Camp RNA",
        root_path="/home/lumber/Github/AI_Camp_RNA_2026",
        status="active",
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
    channel = AgentChannel(
        channel_id="channel_research",
        workspace_id="workspace_rna",
        name="rna-research",
        topic="Research direction",
        status="active",
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
    dm = AgentDirectMessage(
        dm_id="dm_coordinator",
        workspace_id="workspace_rna",
        dm_kind="coordinator",
        title="Coordinator AI",
        target_member_id=None,
        status="active",
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
    member = ChannelMembership(
        member_id="member_research",
        workspace_id="workspace_rna",
        channel_id="channel_research",
        display_name="Research Codex",
        member_kind="codex_session",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy="confirm",
        status="active",
        resume_session_id="session_research",
        source_path="/tmp/session_research.jsonl",
        managed_record_id=None,
        transcript_policy={"page_size": 200},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
    message = WorkspaceConversationMessage(
        message_id="msg_1",
        workspace_id="workspace_rna",
        conversation_type="channel",
        conversation_id="channel_research",
        from_actor="user",
        to_actor=None,
        message_type="user",
        summary="把研究进展同步给工程 Codex。",
        payload={"mode": "queue"},
        created_at="2026-06-12T00:00:01Z",
    )

    assert workspace.to_public_dict()["root_path"].endswith("AI_Camp_RNA_2026")
    assert channel.to_public_dict()["name"] == "rna-research"
    assert dm.to_public_dict()["dm_kind"] == "coordinator"
    assert member.to_public_dict()["send_policy"] == "confirm"
    assert message.to_public_dict()["conversation_id"] == "channel_research"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_status", "paused"),
        ("channel_status", "paused"),
        ("dm_kind", "group"),
        ("send_policy", "manual"),
        ("member_status", "stopped"),
        ("conversation_type", "group"),
        ("message_type", "raw_json"),
    ],
)
def test_contracts_reject_invalid_choices(field: str, value: str):
    if field == "workspace_status":
        with pytest.raises(ValueError, match="workspace status"):
            AgentWorkspace("workspace_rna", "RNA", "/tmp/rna", value, "now", "now")
    elif field == "channel_status":
        with pytest.raises(ValueError, match="channel status"):
            AgentChannel("channel_rna", "workspace_rna", "rna", "", value, "now", "now")
    elif field == "dm_kind":
        with pytest.raises(ValueError, match="dm_kind"):
            AgentDirectMessage(
                "dm_1",
                "workspace_rna",
                value,
                "Bad",
                None,
                "active",
                "now",
                "now",
            )
    elif field == "send_policy":
        with pytest.raises(ValueError, match="send_policy"):
            ChannelMembership(
                "member_1",
                "workspace_rna",
                "channel_rna",
                "Codex",
                "codex_session",
                "Role",
                "Goal",
                value,
                "active",
                "session_1",
                None,
                None,
                {},
                "now",
                "now",
            )
    elif field == "member_status":
        with pytest.raises(ValueError, match="member status"):
            ChannelMembership(
                "member_1",
                "workspace_rna",
                "channel_rna",
                "Codex",
                "codex_session",
                "Role",
                "Goal",
                "confirm",
                value,
                "session_1",
                None,
                None,
                {},
                "now",
                "now",
            )
    elif field == "conversation_type":
        with pytest.raises(ValueError, match="conversation_type"):
            WorkspaceConversationMessage(
                "msg_1",
                "workspace_rna",
                value,
                "channel_rna",
                "user",
                None,
                "user",
                "text",
                {},
                "now",
            )
    else:
        with pytest.raises(ValueError, match="message_type"):
            WorkspaceConversationMessage(
                "msg_1",
                "workspace_rna",
                "channel",
                "channel_rna",
                "user",
                None,
                value,
                "text",
                {},
                "now",
            )


def test_workspace_message_rejects_raw_payload_fields():
    with pytest.raises(ValueError, match="raw workspace payload"):
        WorkspaceConversationMessage(
            message_id="msg_1",
            workspace_id="workspace_rna",
            conversation_type="channel",
            conversation_id="channel_rna",
            from_actor="coordinator",
            to_actor=None,
            message_type="model_reply",
            summary="Public summary",
            payload={"model_prompt": "secret raw prompt"},
            created_at="2026-06-12T00:00:00Z",
        )
