from __future__ import annotations

from isotope.features.supervisor.agent_group.contracts import AgentMember
from isotope.features.supervisor.agent_group.store import AgentGroupStore


def test_store_creates_group_members_and_initial_message(tmp_path):
    store = AgentGroupStore(tmp_path)

    group = store.create_group(
        title="Feature group",
        goal="Discuss the feature.",
        members=[
            AgentMember(
                member_id="member_planner",
                group_id="pending",
                name="planner",
                role="Plan work.",
                goal="Find first steps.",
            ),
            AgentMember(
                member_id="member_reviewer",
                group_id="pending",
                name="reviewer",
                role="Review risk.",
                goal="Find missing tests.",
            ),
        ],
        initial_message="Start with risks.",
    )

    assert group.group_id.startswith("group_")
    members = store.list_members(group.group_id)
    assert [member.name for member in members] == ["planner", "reviewer"]
    messages = store.list_group_messages(group.group_id)
    assert len(messages) == 1
    assert messages[0].from_member == "supervisor"
    assert messages[0].message_type == "task"
    assert messages[0].summary == "Start with risks."


def test_store_publishes_directed_and_broadcast_messages(tmp_path):
    store = AgentGroupStore(tmp_path)
    group = store.create_group(
        title="Feature group",
        goal="Discuss the feature.",
        members=[],
        initial_message="Start.",
    )

    broadcast = store.publish_message(
        group_id=group.group_id,
        turn_id="turn_manual",
        from_member="member_a",
        to_member=None,
        message_type="reply",
        summary="Broadcast note.",
        payload={"kind": "safe"},
    )
    directed = store.publish_message(
        group_id=group.group_id,
        turn_id="turn_manual",
        from_member="member_a",
        to_member="member_b",
        message_type="question",
        summary="Question for B.",
        payload={},
    )

    messages = store.list_group_messages(group.group_id)
    assert [message.message_id for message in messages[-2:]] == [
        broadcast.message_id,
        directed.message_id,
    ]
    assert messages[-1].to_member == "member_b"


def test_store_records_turn(tmp_path):
    store = AgentGroupStore(tmp_path)
    group = store.create_group(
        title="Feature group",
        goal="Discuss the feature.",
        members=[],
        initial_message="Start.",
    )

    turn = store.record_turn(
        group_id=group.group_id,
        input_message_ids=("msg_input",),
        candidate_messages=("candidate_a", "candidate_b"),
        selected_message_ids=("msg_selected",),
        queued_messages=({"message_id": "candidate_b", "reason": "visible_limit"},),
        dropped_messages=(),
        status="selected",
        supervisor_summary="One reply selected.",
    )

    assert store.list_turns(group.group_id)[0].turn_id == turn.turn_id
    assert store.list_groups()[0].group_id == group.group_id
