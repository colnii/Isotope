import pytest

from isotope_kernel import checkpoint_store, event_store, events, projector


ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_001",
}


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-02T00:00:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _proposal():
    return _event(
        "evt_002",
        "action.proposed",
        {
            "proposal_id": "prop_001",
            "agent_id": "agent_supervisor",
            "action_type": "call_tool",
            "registry_id": "default",
            "registry_version": "v0.2",
        },
    )


def _decision():
    return _event(
        "evt_003",
        "action.decided",
        {
            "decision_id": "dec_001",
            "proposal_id": "prop_001",
            "outcome": "approved",
            "policy_profile_id": "default",
            "policy_version": "v0.2",
        },
    )


def _started():
    return _event(
        "evt_004",
        "action.started",
        {
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
        },
    )


def _completed(event_id="evt_007"):
    return _event(
        event_id,
        "action.completed",
        {
            "execution_id": "exec_001",
            "status": "completed",
            "artifact_refs": [ARTIFACT_REF],
        },
    )


def _cancel_requested(**overrides):
    payload = {
        "cancel_id": "cancel_001",
        "run_id": "run_001",
        "proposal_id": "prop_001",
        "execution_id": "exec_001",
        "reason": "user stopped the action",
        "requested_by": "agent_supervisor",
    }
    payload.update(overrides)
    return _event("evt_005", "action.cancel_requested", payload)


def _cancelled(**overrides):
    payload = {
        "cancel_id": "cancel_001",
        "proposal_id": "prop_001",
        "execution_id": "exec_001",
        "status": "cancelled",
        "basis_event_id": "evt_005",
        "reason": "user stopped the action",
    }
    payload.update(overrides)
    return _event("evt_006", "action.cancelled", payload)


def _running_action_events():
    return [_run_created(), _proposal(), _decision(), _started()]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def test_cancelled_action_is_projected_from_canonical_events():
    state = projector.RunProjector().project([*_running_action_events(), _cancel_requested(), _cancelled()])

    assert hasattr(state, "action_cancellations")
    assert state.action_cancellations["cancel_001"]["proposal_id"] == "prop_001"
    assert state.actions["exec_001"]["status"] == "cancelled"


def test_cancelled_action_cannot_complete_later_without_retry_or_supersede():
    with pytest.raises(ValueError, match="action.completed after action.cancelled"):
        projector.RunProjector().project([*_running_action_events(), _cancel_requested(), _cancelled(), _completed()])


def test_cancel_after_completed_action_is_controlled():
    with pytest.raises(ValueError, match="action.cancel_requested after terminal action state"):
        projector.RunProjector().project([*_running_action_events(), _completed("evt_005"), _cancel_requested()])


def test_cancel_checkpoint_state_contains_cancellation_read_model():
    checkpoint = projector.RunProjector().create_checkpoint(
        "run_001",
        [*_running_action_events(), _cancel_requested(), _cancelled()],
    )

    assert "action_cancellations" in checkpoint["state"]
    assert checkpoint["state"]["action_cancellations"]["cancel_001"]["status"] == "cancelled"


def test_existing_projector_still_rejects_completion_before_start():
    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().project([_run_created(), _proposal(), _decision(), _completed("evt_004")])


def test_cancel_requested_proposal_must_match_running_execution():
    with pytest.raises(ValueError, match="action.cancel_requested proposal_id must match execution proposal"):
        projector.RunProjector().project(
            [*_running_action_events(), _cancel_requested(proposal_id="prop_other")]
        )


def test_cancelled_requires_prior_cancel_request():
    with pytest.raises(ValueError, match="action.cancelled requires action.cancel_requested"):
        projector.RunProjector().project([*_running_action_events(), _cancelled()])


def test_cancelled_basis_event_must_match_cancel_request():
    with pytest.raises(ValueError, match="action.cancelled basis_event_id must match action.cancel_requested"):
        projector.RunProjector().project(
            [*_running_action_events(), _cancel_requested(), _cancelled(basis_event_id="evt_wrong")]
        )


def test_cancel_read_model_checkpoint_assisted_rebuild_matches_full_replay(tmp_path):
    canonical_events = [*_running_action_events(), _cancel_requested(), _cancelled()]
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:5])
    checkpoints.save_checkpoint("run_001", checkpoint)

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)
    full = projector.RunProjector().project(canonical_events)

    assert assisted == full
    assert assisted.action_cancellations["cancel_001"]["status"] == "cancelled"
