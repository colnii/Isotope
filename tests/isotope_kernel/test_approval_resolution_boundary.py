import pytest

from isotope_kernel import server


ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


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
    approval = _single_event_payload(api, run["run_id"], "approval.requested")
    return api, run["run_id"], result, approval


def _single_event_payload(api, run_id: str, event_type: str) -> dict:
    matches = [event.payload for event in api.get_events(run_id) if event.event_type == event_type]
    assert len(matches) == 1
    return matches[0]


def _event_types(api, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def _events_of_type(api, run_id: str, event_type: str):
    return [event for event in api.get_events(run_id) if event.event_type == event_type]


def _approved_body(**overrides):
    body = {
        "resolution": "approved",
        "reason": "operator approved deterministic artifact write",
        "resolver": "test_operator",
    }
    body.update(overrides)
    return body


def _denied_body(**overrides):
    body = {
        "resolution": "denied",
        "reason": "operator denied deterministic artifact write",
        "resolver": "test_operator",
    }
    body.update(overrides)
    return body


def test_pending_approval_does_not_create_execution_or_artifact(tmp_path):
    api, run_id, result, _approval = _submit_pending_approval(tmp_path)

    assert result["status"] == "pending_user_approval"
    assert result["execution"] is None
    assert not ACTION_EXECUTION_EVENTS.intersection(_event_types(api, run_id))
    assert api.artifact_store.list_artifacts(run_id) == []


def test_approval_requested_event_contains_resolution_identity_fields(tmp_path):
    api, run_id, result, approval = _submit_pending_approval(tmp_path)

    assert approval["approval_id"]
    assert approval["run_id"] == run_id
    assert approval["proposal_id"] == result["decision"].proposal_id
    assert approval["decision_id"] == result["decision"].decision_id


def test_projector_rebuild_restores_pending_approval_state(tmp_path):
    api, run_id, result, approval = _submit_pending_approval(tmp_path)
    fresh_api = server.InProcessServer(tmp_path)

    state = fresh_api.get_run_state(run_id)

    assert state.status == "pending_user_approval"
    assert state.actions[result["decision"].proposal_id]["status"] == "pending_user_approval"
    assert state.actions[result["decision"].proposal_id]["approval_id"] == approval["approval_id"]


def test_approved_resolution_appends_canonical_approval_resolved_event(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)

    api.resolve_approval(approval["approval_id"], _approved_body())

    resolved = _single_event_payload(api, run_id, "approval.resolved")
    assert resolved["approval_id"] == approval["approval_id"]
    assert resolved["run_id"] == run_id
    assert resolved["proposal_id"] == approval["proposal_id"]
    assert resolved["decision_id"] == approval["decision_id"]
    assert resolved["resolution"] == "approved"


def test_approved_resolution_starts_execution_only_after_resolution_event(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)

    response = api.resolve_approval(approval["approval_id"], _approved_body())

    assert response["status"] == "completed"
    event_types = _event_types(api, run_id)
    assert event_types.index("approval.resolved") < event_types.index("action.started")
    assert "artifact.created" in event_types
    assert "action.completed" in event_types


def test_approved_resolution_uses_original_policy_grants_not_resolution_body_grants(
    tmp_path,
    monkeypatch,
):
    api, _run_id, _result, approval = _submit_pending_approval(tmp_path)
    captured = {}
    original_execute = api.executor.execute

    def capture_execute(decision, proposal):
        captured["grants"] = decision.grants
        return original_execute(decision, proposal)

    monkeypatch.setattr(api.executor, "execute", capture_execute)

    api.resolve_approval(
        approval["approval_id"],
        _approved_body(grants={"tools": ["forged_tool"], "workspace": {"mode": "shared_rw"}}),
    )

    assert captured["grants"]["tools"] == ["write_artifact_tool"]
    assert "forged_tool" not in captured["grants"]["tools"]
    assert captured["grants"]["workspace"]["mode"] == "shared_ro"


def test_denied_resolution_appends_canonical_approval_resolved_event(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)

    api.resolve_approval(approval["approval_id"], _denied_body())

    resolved = _single_event_payload(api, run_id, "approval.resolved")
    assert resolved["approval_id"] == approval["approval_id"]
    assert resolved["run_id"] == run_id
    assert resolved["resolution"] == "denied"


def test_denied_resolution_does_not_create_execution_or_artifact(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)

    response = api.resolve_approval(approval["approval_id"], _denied_body())

    assert response["status"] == "denied"
    event_types = _event_types(api, run_id)
    assert "approval.resolved" in event_types
    assert "action.started" not in event_types
    assert "artifact.created" not in event_types
    assert "action.completed" not in event_types
    assert api.artifact_store.list_artifacts(run_id) == []


def test_duplicate_resolution_is_controlled_without_second_resolution_event(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)

    first = api.resolve_approval(approval["approval_id"], _denied_body())
    try:
        second = api.resolve_approval(approval["approval_id"], _denied_body())
    except ValueError as exc:
        assert "already resolved" in str(exc) or "conflict" in str(exc)
    else:
        assert second == first or second["status"] in {"denied", "conflict"}

    assert len(_events_of_type(api, run_id, "approval.resolved")) == 1


def test_unknown_approval_resolution_returns_controlled_error_without_event(tmp_path):
    api = server.InProcessServer(tmp_path)

    with pytest.raises(ValueError, match="unknown approval"):
        api.resolve_approval("approval_missing", _approved_body())

    assert api.event_store.list_events("run_missing") == []


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"resolution": "approved"},
        {"resolution": "maybe", "reason": "invalid", "resolver": "test_operator"},
        {"resolution": "approved", "reason": "", "resolver": "test_operator"},
        {"resolution": "approved", "reason": "ok", "resolver": ""},
    ],
)
def test_malformed_resolution_body_returns_controlled_error_without_event(tmp_path, body):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)
    before = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="resolution|reason|resolver|body"):
        api.resolve_approval(approval["approval_id"], body)

    assert api.get_events(run_id) == before


def test_resolution_state_is_rebuildable_from_events_not_direct_state_mutation(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)

    response = api.resolve_approval(approval["approval_id"], _approved_body())
    rebuilt = server.InProcessServer(tmp_path).get_run_state(run_id)

    assert response["run_state"] == rebuilt
    assert rebuilt.status == "completed"
    assert rebuilt.artifacts
