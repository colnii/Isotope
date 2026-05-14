import pytest

from isotope import server


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="try unsupported tool")
    return api, run["run_id"]


def test_unsupported_tool_fails_closed_at_compiler_boundary(tmp_path):
    api, run_id = _new_run(tmp_path)

    with pytest.raises(ValueError, match="unknown tool unsupported_tool"):
        api.submit_tool_request(
            run_id,
            tool="unsupported_tool",
            text="hello",
        )


def test_unknown_tool_does_not_create_action_execution(tmp_path):
    api, run_id = _new_run(tmp_path)

    with pytest.raises(ValueError, match="unknown tool unsupported_tool"):
        api.submit_tool_request(
            run_id,
            tool="unsupported_tool",
            text="hello",
        )

    event_types = [event.event_type for event in api.get_events(run_id)]
    assert "action.started" not in event_types
    assert "action.completed" not in event_types


def test_unknown_tool_does_not_create_artifact(tmp_path):
    api, run_id = _new_run(tmp_path)

    with pytest.raises(ValueError, match="unknown tool unsupported_tool"):
        api.submit_tool_request(
            run_id,
            tool="unsupported_tool",
            text="hello",
        )

    assert api.artifact_store.list_artifacts(run_id) == []


def test_unknown_tool_does_not_record_action_lifecycle_events(tmp_path):
    api, run_id = _new_run(tmp_path)

    with pytest.raises(ValueError, match="unknown tool unsupported_tool"):
        api.submit_tool_request(
            run_id,
            tool="unsupported_tool",
            text="hello",
        )

    event_types = [event.event_type for event in api.get_events(run_id)]
    assert "action.proposed" not in event_types
    assert "action.decided" not in event_types
    assert "action.started" not in event_types
