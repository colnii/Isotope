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
        created_at=f"2026-04-27T00:00:{event_id[-2:]}Z",
    )


def _proposed():
    return _event(
        "evt_001",
        "action.proposed",
        {
            "proposal_id": "prop_001",
            "agent_id": "agent_supervisor",
            "action_type": "call_tool",
            "registry_id": "default",
            "registry_version": "v0.2",
        },
    )


def _decided(outcome="approved"):
    return _event(
        "evt_002",
        "action.decided",
        {
            "decision_id": "dec_001",
            "proposal_id": "prop_001",
            "outcome": outcome,
            "policy_profile_id": "default",
            "policy_version": "v0.2",
        },
    )


def _started():
    return _event(
        "evt_003",
        "action.started",
        {
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
        },
    )


def _completed():
    return _event(
        "evt_004",
        "action.completed",
        {
            "execution_id": "exec_001",
            "status": "completed",
            "artifact_refs": [ARTIFACT_REF],
        },
    )


def _failed():
    return _event(
        "evt_005",
        "action.failed",
        {
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
            "status": "failed",
            "error_reason_code": "tool_execution_failed",
            "structured_error": {
                "reason_code": "tool_execution_failed",
                "message": "tool failed",
            },
        },
    )


def _approval_requested():
    return _event(
        "evt_006",
        "approval.requested",
        {
            "approval_id": "approval_001",
            "run_id": "run_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
            "action_type": "call_tool",
        },
    )


def _artifact_created():
    return _event(
        "evt_007",
        "artifact.created",
        {
            "artifact": {
                "ref": ARTIFACT_REF,
                "artifact_type": "text",
                "summary": "hello artifact",
                "provenance": {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"},
            }
        },
    )


def test_projector_rejects_started_before_decided():
    with pytest.raises(ValueError, match="action.started before approved decision"):
        projector.RunProjector().project([_proposed(), _started()])


def test_projector_rejects_completed_before_started():
    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().project([_proposed(), _decided(), _completed()])


def test_projector_rejects_started_after_denied_decision():
    with pytest.raises(ValueError, match="action.started after denied decision"):
        projector.RunProjector().project([_proposed(), _decided("denied"), _started()])


def test_projector_rejects_started_after_pending_approval():
    with pytest.raises(ValueError, match="action.started after pending approval"):
        projector.RunProjector().project(
            [_proposed(), _decided("pending_user_approval"), _approval_requested(), _started()]
        )


def test_projector_rejects_failed_then_completed_execution():
    with pytest.raises(ValueError, match="terminal execution already failed"):
        projector.RunProjector().project([_proposed(), _decided(), _started(), _failed(), _completed()])


def test_projector_rejects_completed_then_failed_execution():
    with pytest.raises(ValueError, match="terminal execution already completed"):
        projector.RunProjector().project([_proposed(), _decided(), _started(), _completed(), _failed()])


def test_happy_path_lifecycle_order_still_projects():
    state = projector.RunProjector().project(
        [_proposed(), _decided(), _started(), _artifact_created(), _completed()]
    )

    assert state.actions["exec_001"]["status"] == "completed"
    assert state.artifacts[0]["summary"] == "hello artifact"
