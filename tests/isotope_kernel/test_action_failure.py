from isotope_kernel import server


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="fail write artifact")
    return api, run["run_id"]


def _submit_failing_action(tmp_path, monkeypatch):
    api, run_id = _new_run(tmp_path)

    def fail_create_artifact(*args, **kwargs):
        raise RuntimeError("deterministic tool failure")

    monkeypatch.setattr(api.artifact_store, "create_artifact", fail_create_artifact)
    result = api.submit_tool_request(
        run_id,
        tool="write_artifact_tool",
        text="hello",
    )
    return api, run_id, result


def test_tool_execution_failure_appends_action_failed(tmp_path, monkeypatch):
    api, run_id, result = _submit_failing_action(tmp_path, monkeypatch)

    event_types = [event.event_type for event in api.get_events(run_id)]
    assert result["status"] == "failed"
    assert "action.failed" in event_types
    assert event_types.index("action.started") < event_types.index("action.failed")


def test_failed_action_does_not_mark_run_completed(tmp_path, monkeypatch):
    api, run_id, result = _submit_failing_action(tmp_path, monkeypatch)

    event_types = [event.event_type for event in api.get_events(run_id)]
    assert result["status"] == "failed"
    assert "run.completed" not in event_types


def test_projector_projects_failed_action_status_from_event_log(tmp_path, monkeypatch):
    api, run_id, result = _submit_failing_action(tmp_path, monkeypatch)

    state = api.get_run_state(run_id)

    assert result["status"] == "failed"
    assert state.status == "failed"
    assert state.actions[result["execution_id"]]["status"] == "failed"


def test_failed_result_does_not_depend_on_executor_memory_state(tmp_path, monkeypatch):
    api, run_id, result = _submit_failing_action(tmp_path, monkeypatch)
    fresh_api = server.InProcessServer(tmp_path)

    rebuilt_state = fresh_api.get_run_state(run_id)

    assert result["status"] == "failed"
    assert rebuilt_state.status == "failed"
    assert rebuilt_state.actions[result["execution_id"]]["status"] == "failed"
