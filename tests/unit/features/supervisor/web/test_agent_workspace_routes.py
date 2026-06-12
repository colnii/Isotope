from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.workspace.api import (
    add_channel_member_payload,
    create_channel_payload,
    ensure_workspace_payload,
    remove_channel_member_payload,
    update_channel_member_payload,
)
from isotope.features.supervisor.web.routes.agent_workspaces import (
    agent_workspace_id_from_path,
    channel_members_path_ids,
    conversation_chat_path_ids,
    conversation_control_path_ids,
    parse_channel_member_payload,
    parse_codex_session_scope,
    parse_workspace_channel_payload,
    parse_workspace_chat_payload,
    parse_workspace_control_payload,
    parse_workspace_member_update_payload,
)


def test_route_helpers_parse_workspace_channel_and_conversation_paths():
    assert (
        agent_workspace_id_from_path("/desktop/agent-workspaces/workspace_rna")
        == "workspace_rna"
    )
    assert channel_members_path_ids(
        "/desktop/agent-workspaces/workspace_rna/channels/channel_research/members"
    ) == ("workspace_rna", "channel_research", None)
    assert channel_members_path_ids(
        "/desktop/agent-workspaces/workspace_rna/channels/channel_research/members/member_research"
    ) == ("workspace_rna", "channel_research", "member_research")
    assert conversation_chat_path_ids(
        "/desktop/agent-workspaces/workspace_rna/conversations/channel_research/chat"
    ) == ("workspace_rna", "channel_research")
    assert conversation_control_path_ids(
        "/desktop/agent-workspaces/workspace_rna/conversations/channel_research/control"
    ) == ("workspace_rna", "channel_research")


def test_parse_codex_session_scope():
    assert parse_codex_session_scope("scope=cwd") == "cwd"
    assert parse_codex_session_scope("scope=all") == "all"
    assert parse_codex_session_scope("") == "cwd"
    with pytest.raises(ValueError, match="scope must be cwd or all"):
        parse_codex_session_scope("scope=project")


def test_parse_channel_member_payload():
    payload = parse_channel_member_payload(
        {
            "display_name": "Research Codex",
            "role": "Explore RNA strategy.",
            "goal": "Find research directions.",
            "send_policy": "confirm",
            "resume_session_id": "session_research",
            "source_path": "/tmp/research.jsonl",
            "managed_record_id": None,
        }
    )

    assert payload["send_policy"] == "confirm"
    assert payload["resume_session_id"] == "session_research"


def test_parse_workspace_chat_payload():
    assert parse_workspace_chat_payload(
        {"message": "sync lanes", "mode": "interrupt"}
    ) == {
        "message": "sync lanes",
        "mode": "interrupt",
    }
    with pytest.raises(ValueError, match="mode must be queue or interrupt"):
        parse_workspace_chat_payload({"message": "sync lanes", "mode": "drop"})


def test_parse_channel_control_and_member_update_payloads():
    assert parse_workspace_channel_payload(
        {"name": "rna-research", "topic": "Research"}
    ) == {
        "name": "rna-research",
        "topic": "Research",
    }
    assert parse_workspace_control_payload(
        {
            "intent": "terminate",
            "target": "member",
            "target_member_id": "member_research",
            "reason": "User pressed Stop.",
        }
    ) == {
        "intent": "terminate",
        "target": "member",
        "target_member_id": "member_research",
        "reason": "User pressed Stop.",
    }
    assert parse_workspace_member_update_payload(
        {"send_policy": "draft_only", "status": "terminated"}
    ) == {
        "send_policy": "draft_only",
        "status": "terminated",
        "role": None,
        "goal": None,
    }


def test_workspace_api_creates_workspace_channel_and_member(tmp_path):
    root_path = tmp_path / "AI_Camp_RNA_2026"
    root_path.mkdir()
    workspace_payload = ensure_workspace_payload(tmp_path / ".codex", root_path=root_path)
    workspace_id = workspace_payload["workspace"]["workspace_id"]
    channel_payload = create_channel_payload(
        tmp_path / ".codex",
        workspace_id=workspace_id,
        name="rna-research",
        topic="Research direction",
    )
    member_payload = add_channel_member_payload(
        tmp_path / ".codex",
        workspace_id=workspace_id,
        channel_id=channel_payload["channel"]["channel_id"],
        display_name="Research Codex",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy="confirm",
        resume_session_id="session_research",
        source_path=None,
        managed_record_id=None,
    )
    updated_payload = update_channel_member_payload(
        tmp_path / ".codex",
        workspace_id=workspace_id,
        channel_id=channel_payload["channel"]["channel_id"],
        member_id=member_payload["member"]["member_id"],
        send_policy="draft_only",
        status="terminated",
        role=None,
        goal=None,
    )
    removed_payload = remove_channel_member_payload(
        tmp_path / ".codex",
        workspace_id=workspace_id,
        channel_id=channel_payload["channel"]["channel_id"],
        member_id=member_payload["member"]["member_id"],
    )

    assert workspace_payload["status"] == "ok"
    assert channel_payload["channel"]["name"] == "rna-research"
    assert member_payload["member"]["display_name"] == "Research Codex"
    assert updated_payload["member"]["send_policy"] == "draft_only"
    assert removed_payload["member"]["status"] == "archived"
