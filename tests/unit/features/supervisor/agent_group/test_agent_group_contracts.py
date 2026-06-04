from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.contracts import (
    AgentGroup,
    AgentGroupMessage,
    AgentMember,
    AgentTurn,
)


def test_agent_group_contracts_to_public_dicts():
    group = AgentGroup(
        group_id="group_001",
        title="Feature group",
        goal="Design agent group chat.",
        status="active",
        created_at="2026-06-04T00:00:00Z",
        updated_at="2026-06-04T00:00:00Z",
    )
    member = AgentMember(
        member_id="member_planner",
        group_id="group_001",
        name="planner",
        role="Plan the work.",
        goal="Find risks.",
        model_profile="default",
        allowed_capabilities=("memory.query",),
        status="active",
    )
    message = AgentGroupMessage(
        message_id="msg_001",
        group_id="group_001",
        turn_id="turn_001",
        from_member="supervisor",
        to_member=None,
        message_type="task",
        summary="Start with risks.",
        payload={"priority": "normal"},
        created_at="2026-06-04T00:00:01Z",
    )
    turn = AgentTurn(
        turn_id="turn_001",
        group_id="group_001",
        input_message_ids=("msg_001",),
        candidate_messages=("candidate_001",),
        selected_message_ids=("msg_002",),
        queued_messages=({"message_id": "candidate_002", "reason": "visible_limit"},),
        dropped_messages=(),
        status="selected",
        supervisor_summary="Planner replied.",
        created_at="2026-06-04T00:00:02Z",
    )

    assert group.to_public_dict()["goal"] == "Design agent group chat."
    assert member.to_public_dict()["allowed_capabilities"] == ["memory.query"]
    assert message.to_public_dict()["to_member"] is None
    assert turn.to_public_dict()["selected_message_ids"] == ["msg_002"]


@pytest.mark.parametrize(
    ("factory", "kwargs", "message"),
    [
        (
            AgentGroup,
            {
                "group_id": "",
                "title": "x",
                "goal": "x",
                "status": "active",
                "created_at": "now",
                "updated_at": "now",
            },
            "group_id must be a non-empty string",
        ),
        (
            AgentMember,
            {
                "member_id": "member_1",
                "group_id": "group_1",
                "name": "worker",
                "role": "role",
                "goal": "goal",
                "model_profile": "default",
                "allowed_capabilities": (),
                "status": "running",
            },
            "member status must be one of",
        ),
        (
            AgentGroupMessage,
            {
                "message_id": "msg_1",
                "group_id": "group_1",
                "turn_id": "turn_1",
                "from_member": "supervisor",
                "to_member": None,
                "message_type": "raw",
                "summary": "x",
                "payload": {},
                "created_at": "now",
            },
            "message_type must be one of",
        ),
    ],
)
def test_contracts_reject_invalid_values(factory, kwargs, message):
    with pytest.raises(ValueError, match=message):
        factory(**kwargs)


def test_group_message_rejects_raw_payload_keys():
    with pytest.raises(ValueError, match="raw group payload is not accepted"):
        AgentGroupMessage(
            message_id="msg_raw",
            group_id="group_1",
            turn_id="turn_1",
            from_member="member_a",
            to_member=None,
            message_type="reply",
            summary="Do not leak raw content.",
            payload={"raw_response": "secret"},
            created_at="2026-06-04T00:00:00Z",
        )
