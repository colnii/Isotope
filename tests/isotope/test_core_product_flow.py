from __future__ import annotations

from typing import Any

from isotope.core import ProductCore


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_product_core_runs_single_user_message_through_in_process_runtime(tmp_path):
    core = ProductCore.in_process(tmp_path)

    session = core.start_session()
    run = core.start_run(session.session_id, goal="produce a hello artifact")
    response = core.submit_user_message(run.run_id, "hello")

    assert session.session_id.startswith("session_")
    assert run.run_id.startswith("run_")
    assert response.status == "completed"
    assert response.run_id == run.run_id
    assert response.run_status == "completed"
    assert response.artifact_summary == "hello artifact"
    assert response.artifact_ref["ref_type"] == "artifact"
    assert response.artifact_ref["run_id"] == run.run_id
    assert response.event_count >= 7
    _assert_no_forbidden_content_keys(response.to_dict())


def test_product_core_keeps_runtime_available_for_existing_callers(tmp_path):
    core = ProductCore.in_process(tmp_path)

    assert core.runtime.root == tmp_path


def test_product_core_tracks_conversation_turns_across_completed_runs(tmp_path):
    core = ProductCore.in_process(tmp_path)

    conversation = core.start_conversation(goal="collect two notes")
    first = core.submit_message(conversation.conversation_id, "first note")
    second = core.submit_message(conversation.conversation_id, "second note")
    state = core.get_conversation(conversation.conversation_id)

    assert conversation.conversation_id == conversation.session_id
    assert conversation.run_id == first.run_id
    assert [turn.text for turn in state.turns] == ["first note", "second note"]
    assert all(turn.response.artifact_summary for turn in state.turns)
    assert state.turns[0].response.artifact_ref != state.turns[1].response.artifact_ref
    assert state.latest_response == second
    assert first.run_id != second.run_id
    assert state.run_ids == (first.run_id, second.run_id)
    _assert_no_forbidden_content_keys(state.to_dict())
