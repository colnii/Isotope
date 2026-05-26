import isotope.runtime.in_process as server


def _submit_pending_approval(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="request approval before writing")
    result = api.submit_tool_request(
        run["run_id"],
        tool="write_artifact_tool",
        text="hello",
        requires_approval=True,
    )
    return api, run["run_id"], result


def _event_payload(api, run_id, event_type):
    matches = [event.payload for event in api.get_events(run_id) if event.event_type == event_type]
    assert len(matches) == 1
    return matches[0]


def test_pending_approval_appends_approval_requested_event(tmp_path):
    api, run_id, result = _submit_pending_approval(tmp_path)

    payload = _event_payload(api, run_id, "approval.requested")

    assert result["status"] == "pending_user_approval"
    assert payload["run_id"] == run_id
    assert payload["proposal_id"] == result["decision"].proposal_id
    assert payload["decision_id"] == result["decision"].decision_id
    assert payload["action_type"] == "call_tool"
    assert payload["approval_id"]


def test_pending_approval_does_not_start_execution(tmp_path):
    api, run_id, result = _submit_pending_approval(tmp_path)

    event_types = [event.event_type for event in api.get_events(run_id)]

    assert result["execution"] is None
    assert "approval.requested" in event_types
    assert "action.started" not in event_types
    assert "action.completed" not in event_types


def test_pending_approval_does_not_create_artifact(tmp_path):
    api, run_id, result = _submit_pending_approval(tmp_path)

    event_types = [event.event_type for event in api.get_events(run_id)]

    assert result["status"] == "pending_user_approval"
    assert "artifact.created" not in event_types
    assert api.artifact_store.list_artifacts(run_id) == []


def test_projector_projects_pending_approval_from_event_log(tmp_path):
    api, run_id, result = _submit_pending_approval(tmp_path)
    approval_payload = _event_payload(api, run_id, "approval.requested")

    state = api.get_run_state(run_id)

    assert state.status == "pending_user_approval"
    assert state.actions[result["decision"].proposal_id]["status"] == "pending_user_approval"
    assert state.actions[result["decision"].proposal_id]["approval_id"] == approval_payload["approval_id"]


def test_fresh_projector_rebuilds_pending_approval_from_event_log(tmp_path):
    api, run_id, result = _submit_pending_approval(tmp_path)
    approval_payload = _event_payload(api, run_id, "approval.requested")
    fresh_api = server.InProcessServer(tmp_path)

    rebuilt_state = fresh_api.get_run_state(run_id)

    assert rebuilt_state.status == "pending_user_approval"
    assert rebuilt_state.actions[result["decision"].proposal_id]["status"] == "pending_user_approval"
    assert rebuilt_state.actions[result["decision"].proposal_id]["approval_id"] == approval_payload["approval_id"]
