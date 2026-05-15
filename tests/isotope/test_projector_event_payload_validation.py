import pytest

import isotope.platform.events.events as events
import isotope.platform.state.projector as projector


ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_001",
}


def _event(event_id, event_type, payload):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-04-28T00:00:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _proposed(proposal_id="prop_001"):
    return _event(
        "evt_002",
        "action.proposed",
        {
            "proposal_id": proposal_id,
            "agent_id": "agent_supervisor",
            "action_type": "call_tool",
            "registry_id": "default",
            "registry_version": "v0.2",
        },
    )


def _decided(outcome="approved", **overrides):
    payload = {
        "decision_id": "dec_001",
        "proposal_id": "prop_001",
        "outcome": outcome,
        "policy_profile_id": "default",
        "policy_version": "v0.2",
    }
    payload.update(overrides)
    return _event("evt_003", "action.decided", payload)


def _started(**overrides):
    payload = {
        "execution_id": "exec_001",
        "proposal_id": "prop_001",
        "decision_id": "dec_001",
    }
    payload.update(overrides)
    return _event("evt_004", "action.started", payload)


def _completed(**overrides):
    payload = {
        "execution_id": "exec_001",
        "status": "completed",
        "artifact_refs": [ARTIFACT_REF],
    }
    payload.update(overrides)
    return _event("evt_005", "action.completed", payload)


def _failed(**overrides):
    payload = {
        "execution_id": "exec_001",
        "proposal_id": "prop_001",
        "decision_id": "dec_001",
        "status": "failed",
        "error": "tool failed",
        "error_reason_code": "tool_execution_failed",
        "structured_error": {
            "reason_code": "tool_execution_failed",
            "message": "tool failed",
        },
    }
    payload.update(overrides)
    return _event("evt_006", "action.failed", payload)


def _artifact_created(**overrides):
    artifact = {
        "ref": ARTIFACT_REF,
        "artifact_type": "text",
        "summary": "hello artifact",
        "provenance": {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"},
    }
    artifact.update(overrides)
    return _event("evt_007", "artifact.created", {"artifact": artifact})


def _approval_requested(**overrides):
    payload = {
        "approval_id": "approval_001",
        "run_id": "run_001",
        "proposal_id": "prop_001",
        "decision_id": "dec_001",
        "action_type": "call_tool",
    }
    payload.update(overrides)
    return _event("evt_008", "approval.requested", payload)


def _without(mapping, key):
    result = dict(mapping)
    result.pop(key)
    return result


def test_action_started_allows_modified_decision():
    state = projector.RunProjector().project([_run_created(), _proposed(), _decided("modified"), _started()])

    assert state.actions["exec_001"]["status"] == "running"


@pytest.mark.parametrize("field", ["proposal_id", "decision_id", "outcome"])
def test_action_decided_requires_payload_fields(field):
    payload = _without(_decided().payload, field)

    with pytest.raises(ValueError, match=f"action.decided missing required field: {field}"):
        projector.RunProjector().project([_run_created(), _event("evt_003", "action.decided", payload)])


def test_action_decided_rejects_unknown_outcome():
    with pytest.raises(ValueError, match="action.decided has unknown outcome"):
        projector.RunProjector().project([_run_created(), _decided("unknown")])


@pytest.mark.parametrize("field", ["execution_id", "proposal_id", "decision_id"])
def test_action_started_requires_payload_fields(field):
    payload = _without(_started().payload, field)

    with pytest.raises(ValueError, match=f"action.started missing required field: {field}"):
        projector.RunProjector().project(
            [_run_created(), _proposed(), _decided(), _event("evt_004", "action.started", payload)]
        )


@pytest.mark.parametrize("field", ["execution_id", "status", "artifact_refs"])
def test_action_completed_requires_payload_fields(field):
    payload = _without(_completed().payload, field)

    with pytest.raises(ValueError, match=f"action.completed missing required field: {field}"):
        projector.RunProjector().project(
            [_run_created(), _proposed(), _decided(), _started(), _event("evt_005", "action.completed", payload)]
        )


def test_action_completed_requires_completed_status():
    with pytest.raises(ValueError, match="action.completed status must be completed"):
        projector.RunProjector().project(
            [_run_created(), _proposed(), _decided(), _started(), _completed(status="failed")]
        )


def test_action_completed_requires_artifact_refs_list():
    with pytest.raises(ValueError, match="action.completed artifact_refs must be a list"):
        projector.RunProjector().project(
            [_run_created(), _proposed(), _decided(), _started(), _completed(artifact_refs="artifact_001")]
        )


@pytest.mark.parametrize("field", ["execution_id", "proposal_id", "decision_id", "status"])
def test_action_failed_requires_payload_fields(field):
    payload = _without(_failed().payload, field)

    with pytest.raises(ValueError, match=f"action.failed missing required field: {field}"):
        projector.RunProjector().project(
            [_run_created(), _proposed(), _decided(), _started(), _event("evt_006", "action.failed", payload)]
        )


def test_action_failed_requires_failed_status():
    with pytest.raises(ValueError, match="action.failed status must be failed"):
        projector.RunProjector().project(
            [_run_created(), _proposed(), _decided(), _started(), _failed(status="completed")]
        )


def test_artifact_created_requires_artifact_payload():
    with pytest.raises(ValueError, match="artifact.created missing required field: artifact"):
        projector.RunProjector().project([_run_created(), _event("evt_007", "artifact.created", {})])


@pytest.mark.parametrize("field", ["ref", "artifact_type", "summary", "provenance"])
def test_artifact_created_requires_artifact_fields(field):
    artifact = _without(_artifact_created().payload["artifact"], field)

    with pytest.raises(ValueError, match=f"artifact.created artifact missing required field: {field}"):
        projector.RunProjector().project([_run_created(), _event("evt_007", "artifact.created", {"artifact": artifact})])


def test_artifact_created_rejects_content_payload():
    with pytest.raises(ValueError, match="artifact.created artifact cannot contain content"):
        projector.RunProjector().project([_run_created(), _artifact_created(content="raw content")])


@pytest.mark.parametrize("field", ["approval_id", "proposal_id", "decision_id", "action_type"])
def test_approval_requested_requires_payload_fields(field):
    payload = _without(_approval_requested().payload, field)

    with pytest.raises(ValueError, match=f"approval.requested missing required field: {field}"):
        projector.RunProjector().project([_run_created(), _event("evt_008", "approval.requested", payload)])
