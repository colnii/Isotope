from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.codex_chat.contracts import (
    ConnectedCodexMember,
    CoordinatorDecision,
    PrivateChatMessage,
    RuntimeControlRequest,
)


def test_connected_codex_member_public_dict():
    member = ConnectedCodexMember(
        member_id="member_research",
        group_id="group_rna",
        display_name="Research Codex",
        member_kind="codex_session",
        role="Explore RNA strategy.",
        goal="Find promising research directions.",
        send_policy="confirm",
        status="active",
        resume_session_id="019e9830-8a72-7ff1-8b2e-310b9d66372b",
        source_path="/home/lumber/.codex/sessions/rollout.jsonl",
        managed_record_id=None,
        transcript_policy={"page_size": 200, "raw_view": True},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )

    assert member.to_public_dict() == {
        "member_id": "member_research",
        "group_id": "group_rna",
        "display_name": "Research Codex",
        "member_kind": "codex_session",
        "role": "Explore RNA strategy.",
        "goal": "Find promising research directions.",
        "send_policy": "confirm",
        "status": "active",
        "resume_session_id": "019e9830-8a72-7ff1-8b2e-310b9d66372b",
        "source_path": "/home/lumber/.codex/sessions/rollout.jsonl",
        "managed_record_id": None,
        "transcript_policy": {"page_size": 200, "raw_view": True},
        "created_at": "2026-06-12T00:00:00Z",
        "updated_at": "2026-06-12T00:00:00Z",
    }


def test_private_chat_message_is_not_group_broadcast():
    message = PrivateChatMessage(
        message_id="priv_1",
        group_id="group_rna",
        role="assistant",
        content="Engineering Codex is blocked; ask before sending.",
        created_at="2026-06-12T00:00:01Z",
    )

    assert message.to_public_dict()["channel"] == "private_human_chat"
    assert (
        message.to_public_dict()["content"]
        == "Engineering Codex is blocked; ask before sending."
    )


def test_coordinator_decision_public_dict_for_confirm_send():
    decision = CoordinatorDecision(
        decision_id="decision_1",
        group_id="group_rna",
        action="send_member",
        target_member_id="member_engineering",
        content="Research found that the input schema changed; inspect /saisdata/56.",
        reason="Engineering needs the research update.",
        created_at="2026-06-12T00:00:02Z",
    )

    assert decision.to_public_dict()["action"] == "send_member"
    assert decision.to_public_dict()["target_member_id"] == "member_engineering"


def test_runtime_control_request_public_dict_for_terminate():
    request = RuntimeControlRequest(
        control_id="control_1",
        group_id="group_rna",
        intent="terminate",
        target="member",
        target_member_id="member_research",
        reason="User pressed member Stop.",
        created_at="2026-06-12T00:00:03Z",
    )

    assert request.to_public_dict()["intent"] == "terminate"
    assert request.to_public_dict()["target_member_id"] == "member_research"


@pytest.mark.parametrize(
    ("factory", "kwargs", "message"),
    [
        (
            ConnectedCodexMember,
            {
                "member_id": "",
                "group_id": "group_rna",
                "display_name": "Research",
                "member_kind": "codex_session",
                "role": "role",
                "goal": "",
                "send_policy": "confirm",
                "status": "active",
                "resume_session_id": "session",
                "source_path": None,
                "managed_record_id": None,
                "transcript_policy": {},
                "created_at": "now",
                "updated_at": "now",
            },
            "member_id must be a non-empty string",
        ),
        (
            ConnectedCodexMember,
            {
                "member_id": "member_research",
                "group_id": "group_rna",
                "display_name": "Research",
                "member_kind": "codex_session",
                "role": "role",
                "goal": "",
                "send_policy": "silent_auto",
                "status": "active",
                "resume_session_id": "session",
                "source_path": None,
                "managed_record_id": None,
                "transcript_policy": {},
                "created_at": "now",
                "updated_at": "now",
            },
            "send_policy must be one of",
        ),
        (
            CoordinatorDecision,
            {
                "decision_id": "decision_1",
                "group_id": "group_rna",
                "action": "route_by_keyword",
                "target_member_id": None,
                "content": "x",
                "reason": "x",
                "created_at": "now",
            },
            "decision action must be one of",
        ),
        (
            RuntimeControlRequest,
            {
                "control_id": "control_1",
                "group_id": "group_rna",
                "intent": "kill_everything",
                "target": "member",
                "target_member_id": "member_research",
                "reason": "x",
                "created_at": "now",
            },
            "control intent must be one of",
        ),
    ],
)
def test_contracts_reject_invalid_values(factory, kwargs, message):
    with pytest.raises(ValueError, match=message):
        factory(**kwargs)


def test_payload_guards_reject_raw_or_secret_fields():
    with pytest.raises(ValueError, match="raw codex chat payload is not accepted"):
        ConnectedCodexMember(
            member_id="member_research",
            group_id="group_rna",
            display_name="Research",
            member_kind="codex_session",
            role="role",
            goal="",
            send_policy="confirm",
            status="active",
            resume_session_id="session",
            source_path=None,
            managed_record_id=None,
            transcript_policy={"nested": {"raw_response": "secret"}},
            created_at="now",
            updated_at="now",
        )
