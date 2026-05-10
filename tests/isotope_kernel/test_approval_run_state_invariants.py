import json
from dataclasses import asdict

import pytest

from isotope_kernel import checkpoint_store, server


EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


def _submit_pending_approval(tmp_path, *, checkpoints=None):
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
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


def _submit_pending_approval_with_text(tmp_path, text: str, *, checkpoints=None):
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="request approval before writing")
    result = api.submit_tool_request(
        run["run_id"],
        tool="write_artifact_tool",
        text=text,
        requires_approval=True,
    )
    approval = _single_event_payload(api, run["run_id"], "approval.requested")
    return api, run["run_id"], result, approval


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


def _single_event_payload(api, run_id: str, event_type: str) -> dict:
    matches = [event.payload for event in api.get_events(run_id) if event.event_type == event_type]
    assert len(matches) == 1
    return matches[0]


def _event_types(api, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def test_pending_approval_state_has_explicit_blocked_signal_and_summary(tmp_path):
    api, run_id, result, approval = _submit_pending_approval(tmp_path)

    state = api.get_run_state(run_id)

    assert state.status == "pending_user_approval"
    assert state.approvals[approval["approval_id"]] == {
        "approval_id": approval["approval_id"],
        "run_id": run_id,
        "proposal_id": approval["proposal_id"],
        "decision_id": approval["decision_id"],
        "status": "pending",
        "reason_codes": ["approval_required"],
        "requested_action_summary": {"action_type": "call_tool"},
    }
    assert state.actions[result["decision"].proposal_id]["status"] == "pending_user_approval"


def test_pending_approval_does_not_complete_or_create_execution_artifact(tmp_path):
    api, run_id, _result, _approval = _submit_pending_approval(tmp_path)
    state = api.get_run_state(run_id)

    assert state.status == "pending_user_approval"
    assert not EXECUTION_EVENTS.intersection(_event_types(api, run_id))
    assert state.artifacts == []
    assert api.artifact_store.list_artifacts(run_id) == []


def test_approved_resolution_clears_pending_signal_and_completes_run(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)

    response = api.resolve_approval(approval["approval_id"], _approved_body())
    state = response["run_state"]

    assert state.status == "completed"
    assert state.approvals[approval["approval_id"]]["status"] == "approved"
    assert state.approvals[approval["approval_id"]]["resolution"] == "approved"
    assert state.approvals[approval["approval_id"]]["reason"] == _approved_body()["reason"]
    assert state.approvals[approval["approval_id"]]["resolver"] == "test_operator"
    assert state.actions[approval["proposal_id"]]["status"] == "approved"
    assert any(action.get("status") == "completed" for action in state.actions.values())
    assert state.artifacts


def test_denied_resolution_clears_pending_signal_without_execution_or_artifact(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)

    response = api.resolve_approval(approval["approval_id"], _denied_body())
    state = response["run_state"]

    assert state.status == "denied"
    assert state.approvals[approval["approval_id"]]["status"] == "denied"
    assert state.approvals[approval["approval_id"]]["resolution"] == "denied"
    assert state.actions[approval["proposal_id"]]["status"] == "denied"
    assert not EXECUTION_EVENTS.intersection(_event_types(api, run_id))
    assert state.artifacts == []
    assert api.artifact_store.list_artifacts(run_id) == []


def test_duplicate_resolution_does_not_change_projected_state(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)
    api.resolve_approval(approval["approval_id"], _denied_body())
    before_state = api.get_run_state(run_id)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="already resolved"):
        api.resolve_approval(approval["approval_id"], _denied_body())

    assert api.get_run_state(run_id) == before_state
    assert api.get_events(run_id) == before_events


def test_replay_restores_approval_read_model_from_event_log(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)
    api.resolve_approval(approval["approval_id"], _approved_body())

    rebuilt = server.InProcessServer(tmp_path).get_run_state(run_id)

    assert rebuilt.status == "completed"
    assert rebuilt.approvals[approval["approval_id"]]["status"] == "approved"
    assert rebuilt.approvals[approval["approval_id"]]["resolution"] == "approved"
    assert rebuilt.artifacts


def test_checkpoint_assisted_rebuild_restores_approval_read_model(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    api, run_id, _result, approval = _submit_pending_approval(tmp_path, checkpoints=checkpoints)
    saved = api.save_checkpoint_for_run(run_id)

    checkpoint = checkpoints.load_latest_checkpoint(run_id)
    assert checkpoint["basis_event_id"] == saved["basis_event_id"]
    assert checkpoint["state"]["approvals"][approval["approval_id"]]["status"] == "pending"

    fresh = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
    rebuilt = fresh.get_run_state(run_id)

    assert rebuilt.status == "pending_user_approval"
    assert rebuilt.approvals[approval["approval_id"]]["status"] == "pending"
    assert rebuilt.approvals[approval["approval_id"]]["proposal_id"] == approval["proposal_id"]


def test_approval_read_model_does_not_require_server_memory(tmp_path):
    api, run_id, _result, approval = _submit_pending_approval(tmp_path)
    api._pending_approvals.clear()

    rebuilt = server.InProcessServer(tmp_path).get_run_state(run_id)

    assert rebuilt.approvals[approval["approval_id"]]["status"] == "pending"


def test_restarted_server_can_resolve_pending_approval_without_process_memory(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    api, run_id, _result, approval = _submit_pending_approval(tmp_path, checkpoints=checkpoints)
    api.save_checkpoint_for_run(run_id)
    restarted = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)

    response = restarted.resolve_approval(approval["approval_id"], _approved_body())

    assert response["status"] == "completed"
    event_types = [event.event_type for event in restarted.get_events(run_id)]
    assert event_types.index("approval.resolved") < event_types.index("action.started")
    assert restarted.get_approval(run_id, approval["approval_id"])["status"] == "approved"


def test_pending_approval_recovery_context_does_not_leak_raw_tool_text(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    secret = "sensitive approval payload text"
    api, run_id, _result, approval = _submit_pending_approval_with_text(
        tmp_path,
        secret,
        checkpoints=checkpoints,
    )
    saved = api.save_checkpoint_for_run(run_id)

    approval_payload_text = json.dumps(approval, sort_keys=True)
    run_state_text = json.dumps(asdict(api.get_run_state(run_id)), sort_keys=True)
    checkpoint_text = json.dumps(saved, sort_keys=True)

    assert secret not in approval_payload_text
    assert secret not in run_state_text
    assert secret not in checkpoint_text

    restarted = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
    response = restarted.resolve_approval(approval["approval_id"], _approved_body())

    assert response["status"] == "completed"
    artifact_ref = response["artifact_ref"]
    assert restarted.artifact_store.get_content(artifact_ref) == secret


def test_restarted_approval_resolution_failure_does_not_append_partial_events(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    api, run_id, _result, approval = _submit_pending_approval(tmp_path, checkpoints=checkpoints)
    api.save_checkpoint_for_run(run_id)
    restarted = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
    before = list(restarted.get_events(run_id))

    with pytest.raises(ValueError, match="resolver"):
        restarted.resolve_approval(approval["approval_id"], {"resolution": "approved", "reason": "ok"})

    assert restarted.get_events(run_id) == before
