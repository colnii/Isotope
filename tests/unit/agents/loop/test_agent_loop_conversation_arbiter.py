from __future__ import annotations

import pytest

import isotope.runtime.in_process as server
from isotope.agents.loop.conversation import (
    AgentConversationMessage,
    arbitrate_agent_conversation_turn,
)


FORBIDDEN_CONTENT_KEYS = {
    "artifact_content",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_response",
    "raw_artifact_content",
    "raw_content",
    "raw_prompt",
    "raw_response",
}


def _assert_no_forbidden_content_keys(value):
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_conversation_arbiter_allows_silence_without_forcing_agent_reply():
    result = arbitrate_agent_conversation_turn(
        [],
        turn_id="turn_001",
        max_visible_messages=2,
    )

    assert result["kind"] == "agent_conversation_turn"
    assert result["turn_id"] == "turn_001"
    assert result["status"] == "silent"
    assert result["visible_messages"] == []
    assert result["queued_messages"] == []
    assert result["dropped_messages"] == []
    assert result["safety"]["agent_conversation_interface"] is True
    assert result["safety"]["limited"] is True
    _assert_no_forbidden_content_keys(result)


def test_conversation_arbiter_prioritizes_interrupts_and_limits_visible_messages():
    result = arbitrate_agent_conversation_turn(
        [
            AgentConversationMessage(
                message_id="msg_coder",
                agent_id="agent_coder",
                intent="respond",
                summary="Implementation can proceed after tests are written.",
                priority=60,
            ),
            AgentConversationMessage(
                message_id="msg_critic",
                agent_id="agent_critic",
                intent="interrupt",
                summary="The plan misses a failing-test gate.",
                priority=50,
                interrupt_reason="test gate missing",
            ),
            AgentConversationMessage(
                message_id="msg_memo",
                agent_id="agent_memo",
                intent="internal_note",
                summary="Prior decision says memory writes require proposal first.",
                priority=90,
            ),
        ],
        turn_id="turn_002",
        max_visible_messages=1,
    )

    assert result["status"] == "selected"
    assert [item["message_id"] for item in result["visible_messages"]] == ["msg_critic"]
    assert result["visible_messages"][0]["intent"] == "interrupt"
    assert result["visible_messages"][0]["display"] is True
    assert {item["message_id"] for item in result["queued_messages"]} == {
        "msg_coder",
        "msg_memo",
    }
    assert {item["reason"] for item in result["queued_messages"]} == {
        "visible_limit",
    }
    _assert_no_forbidden_content_keys(result)


def test_conversation_arbiter_defers_state_lock_conflicts():
    result = arbitrate_agent_conversation_turn(
        [
            AgentConversationMessage(
                message_id="msg_loop",
                agent_id="agent_loop",
                intent="respond",
                summary="Loop should update run state.",
                priority=70,
                state_lock="run:123",
            ),
            AgentConversationMessage(
                message_id="msg_supr",
                agent_id="agent_supr",
                intent="respond",
                summary="Supervisor should also update run state.",
                priority=80,
                state_lock="run:123",
            ),
            AgentConversationMessage(
                message_id="msg_screen",
                agent_id="agent_screen",
                intent="respond",
                summary="Screen can report independent UI state.",
                priority=40,
                state_lock="screen:main",
            ),
        ],
        turn_id="turn_003",
        max_visible_messages=3,
    )

    assert [item["message_id"] for item in result["visible_messages"]] == [
        "msg_supr",
        "msg_screen",
    ]
    assert result["queued_messages"] == [
        {
            "message_id": "msg_loop",
            "agent_id": "agent_loop",
            "reason": "state_lock_conflict",
            "state_lock": "run:123",
        }
    ]
    assert result["state_locks"] == ["run:123", "screen:main"]
    _assert_no_forbidden_content_keys(result)


def test_conversation_arbiter_rejects_invalid_or_raw_candidate_payloads():
    with pytest.raises(ValueError, match="priority must be an integer"):
        AgentConversationMessage(
            message_id="msg_bad",
            agent_id="agent_bad",
            intent="respond",
            summary="bad priority",
            priority=True,
        )

    with pytest.raises(ValueError, match="raw conversation payload is not accepted"):
        AgentConversationMessage(
            message_id="msg_raw",
            agent_id="agent_raw",
            intent="respond",
            summary="raw payload should be rejected",
            priority=1,
            metadata={"raw_response": "SHOULD_NOT_LEAK"},
        )


def test_in_process_runtime_exposes_conversation_arbiter(tmp_path):
    api = server.InProcessServer(tmp_path)

    result = api.arbitrate_agent_conversation_turn(
        [
            AgentConversationMessage(
                message_id="msg_loop",
                agent_id="agent_loop",
                intent="respond",
                summary="Loop has a limited next step.",
                priority=10,
            )
        ],
        turn_id="turn_runtime",
        max_visible_messages=1,
    )

    assert result["kind"] == "agent_conversation_turn"
    assert result["status"] == "selected"
    assert result["visible_messages"][0]["agent_id"] == "agent_loop"
    _assert_no_forbidden_content_keys(result)
