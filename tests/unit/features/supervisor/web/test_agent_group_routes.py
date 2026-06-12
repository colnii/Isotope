from __future__ import annotations

import pytest

from isotope.features.supervisor.web.routes.agent_groups import (
    agent_group_id_from_path,
    codex_session_id_from_transcript_path,
    parse_agent_group_chat_payload,
    parse_agent_group_control_payload,
    parse_codex_transcript_query,
)


def test_agent_group_id_from_path():
    assert agent_group_id_from_path("/desktop/agent-groups/group_rna") == "group_rna"
    assert agent_group_id_from_path("/desktop/agent-groups/group_rna/chat") is None


def test_codex_session_id_from_transcript_path():
    assert (
        codex_session_id_from_transcript_path(
            "/desktop/codex-sessions/session_1/transcript"
        )
        == "session_1"
    )
    assert codex_session_id_from_transcript_path("/desktop/codex-sessions/session_1") is None


def test_parse_agent_group_chat_payload():
    payload = parse_agent_group_chat_payload(
        {
            "message": "summarize the current state",
            "mode": "interrupt",
        }
    )

    assert payload == {"message": "summarize the current state", "mode": "interrupt"}


def test_parse_agent_group_control_payload():
    payload = parse_agent_group_control_payload(
        {
            "intent": "terminate",
            "target": "member",
            "target_member_id": "member_research",
            "reason": "User pressed Stop.",
        }
    )

    assert payload["intent"] == "terminate"
    assert payload["target_member_id"] == "member_research"


def test_parse_codex_transcript_query():
    assert parse_codex_transcript_query(
        "offset=20&limit=50&include_raw=true"
    ) == {
        "offset": 20,
        "limit": 50,
        "include_raw": True,
        "latest": False,
    }
    assert parse_codex_transcript_query("latest=true")["latest"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "", "mode": "queue"},
        {"message": "x", "mode": "drop"},
    ],
)
def test_parse_agent_group_chat_payload_rejects_invalid_values(payload):
    with pytest.raises(ValueError):
        parse_agent_group_chat_payload(payload)
