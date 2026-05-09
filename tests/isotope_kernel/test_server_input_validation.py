import pytest

from isotope_kernel import server


ACTION_EVENT_TYPES = {
    "action.proposed",
    "action.decided",
    "action.started",
    "action.completed",
    "action.failed",
    "approval.requested",
    "artifact.created",
    "run.completed",
}


def _api(tmp_path):
    return server.InProcessServer(tmp_path)


def _new_run(tmp_path):
    api = _api(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="hello")
    return api, run["run_id"]


def _event_types(api, run_id):
    return [event.event_type for event in api.get_events(run_id)]


def _event_log_paths(tmp_path):
    runs_dir = tmp_path / "runs"
    if not runs_dir.exists():
        return []
    return sorted(runs_dir.glob("*/events.jsonl"))


def _assert_no_action_events_added(api, run_id, before):
    after = _event_types(api, run_id)
    assert after == before
    assert not any(event_type in ACTION_EVENT_TYPES - {"run.completed"} for event_type in after[len(before):])


@pytest.mark.parametrize("bad_session_id", ["session_missing", None, "", 123])
def test_create_run_rejects_invalid_session_id_without_events(tmp_path, bad_session_id):
    api = _api(tmp_path)

    with pytest.raises(ValueError, match="session_id"):
        api.create_run(bad_session_id, goal="hello")

    assert _event_log_paths(tmp_path) == []


@pytest.mark.parametrize("bad_goal", [None, "", 123])
def test_create_run_rejects_invalid_goal_without_events(tmp_path, bad_goal):
    api = _api(tmp_path)
    session = api.create_session()

    with pytest.raises(ValueError, match="goal"):
        api.create_run(session["session_id"], goal=bad_goal)

    assert [path.parent.name for path in _event_log_paths(tmp_path)] == [session["session_id"]]


@pytest.mark.parametrize("bad_run_id", [None, "", 123, "run_missing"])
def test_submit_input_rejects_invalid_run_id_without_action_events(tmp_path, bad_run_id):
    api, run_id = _new_run(tmp_path)
    before = _event_types(api, run_id)

    with pytest.raises(ValueError, match="run_id"):
        api.submit_input(bad_run_id, text="hello")

    _assert_no_action_events_added(api, run_id, before)
    assert api.artifact_store.list_artifacts(run_id) == []


@pytest.mark.parametrize("bad_text", [None, "", 123])
def test_submit_input_rejects_invalid_text_without_action_events(tmp_path, bad_text):
    api, run_id = _new_run(tmp_path)
    before = _event_types(api, run_id)

    with pytest.raises(ValueError, match="text"):
        api.submit_input(run_id, text=bad_text)

    _assert_no_action_events_added(api, run_id, before)
    assert api.artifact_store.list_artifacts(run_id) == []


@pytest.mark.parametrize("bad_run_id", [None, "", 123, "run_missing"])
def test_submit_tool_request_rejects_invalid_run_id_without_action_events(tmp_path, bad_run_id):
    api, run_id = _new_run(tmp_path)
    before = _event_types(api, run_id)

    with pytest.raises(ValueError, match="run_id"):
        api.submit_tool_request(bad_run_id, tool="write_artifact_tool", text="hello")

    _assert_no_action_events_added(api, run_id, before)
    assert api.artifact_store.list_artifacts(run_id) == []


@pytest.mark.parametrize("bad_tool", [None, "", 123])
def test_submit_tool_request_rejects_invalid_tool_without_side_effects(tmp_path, bad_tool):
    api, run_id = _new_run(tmp_path)
    before = _event_types(api, run_id)

    with pytest.raises(ValueError, match="tool"):
        api.submit_tool_request(run_id, tool=bad_tool, text="hello")

    _assert_no_action_events_added(api, run_id, before)
    assert api.artifact_store.list_artifacts(run_id) == []


@pytest.mark.parametrize("bad_text", [None, "", 123])
def test_submit_tool_request_rejects_invalid_text_without_side_effects(tmp_path, bad_text):
    api, run_id = _new_run(tmp_path)
    before = _event_types(api, run_id)

    with pytest.raises(ValueError, match="text"):
        api.submit_tool_request(run_id, tool="write_artifact_tool", text=bad_text)

    _assert_no_action_events_added(api, run_id, before)
    assert api.artifact_store.list_artifacts(run_id) == []


@pytest.mark.parametrize("bad_requires_approval", [None, "true", 1])
def test_submit_tool_request_rejects_non_bool_requires_approval_without_side_effects(
    tmp_path,
    bad_requires_approval,
):
    api, run_id = _new_run(tmp_path)
    before = _event_types(api, run_id)

    with pytest.raises(ValueError, match="requires_approval"):
        api.submit_tool_request(
            run_id,
            tool="write_artifact_tool",
            text="hello",
            requires_approval=bad_requires_approval,
        )

    _assert_no_action_events_added(api, run_id, before)
    assert api.artifact_store.list_artifacts(run_id) == []


@pytest.mark.parametrize("bad_run_id", [None, "", 123])
def test_get_run_state_rejects_invalid_run_id(tmp_path, bad_run_id):
    api = _api(tmp_path)

    with pytest.raises(ValueError, match="run_id"):
        api.get_run_state(bad_run_id)


@pytest.mark.parametrize("bad_run_id", [None, "", 123])
def test_get_events_rejects_invalid_run_id(tmp_path, bad_run_id):
    api = _api(tmp_path)

    with pytest.raises(ValueError, match="run_id"):
        api.get_events(bad_run_id)


def test_get_run_state_allows_fresh_rebuild_for_known_event_log_without_memory(tmp_path):
    api, run_id = _new_run(tmp_path)
    fresh_api = _api(tmp_path)

    state = fresh_api.get_run_state(run_id)

    assert state.run_id == run_id
    assert state.status == "running"
