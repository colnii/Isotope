from isotope_kernel import server


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="try unsupported tool")
    return api, run["run_id"]


def test_unsupported_tool_produces_denied_policy_decision(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_tool_request(
        run_id,
        tool="unsupported_tool",
        text="hello",
    )

    assert result["status"] == "denied"
    assert result["decision"].outcome == "denied"
    assert result["decision"].reason_codes == ["unsupported_tool"]


def test_denied_action_does_not_create_action_execution(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_tool_request(
        run_id,
        tool="unsupported_tool",
        text="hello",
    )

    event_types = [event.event_type for event in api.get_events(run_id)]
    assert result["execution"] is None
    assert "action.started" not in event_types
    assert "action.completed" not in event_types


def test_denied_action_does_not_create_artifact(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_tool_request(
        run_id,
        tool="unsupported_tool",
        text="hello",
    )

    assert result["status"] == "denied"
    assert api.artifact_store.list_artifacts(run_id) == []


def test_denied_action_records_proposed_and_decided_but_not_started(tmp_path):
    api, run_id = _new_run(tmp_path)

    api.submit_tool_request(
        run_id,
        tool="unsupported_tool",
        text="hello",
    )

    event_types = [event.event_type for event in api.get_events(run_id)]
    assert "action.proposed" in event_types
    assert "action.decided" in event_types
    assert "action.started" not in event_types

    proposed_index = event_types.index("action.proposed")
    decided_index = event_types.index("action.decided")
    assert proposed_index < decided_index
