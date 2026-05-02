import pytest

from isotope_kernel import checkpoint_store, event_store, events, projector


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


def _proposal(event_id="evt_002", proposal_id="prop_001"):
    return _event(
        event_id,
        "action.proposed",
        {
            "proposal_id": proposal_id,
            "agent_id": "agent_supervisor",
            "action_type": "call_tool",
        },
    )


def _decision(event_id="evt_003", proposal_id="prop_001", decision_id="dec_001"):
    return _event(
        event_id,
        "action.decided",
        {
            "decision_id": decision_id,
            "proposal_id": proposal_id,
            "outcome": "approved",
        },
    )


def _started(event_id="evt_004", proposal_id="prop_001", decision_id="dec_001", execution_id="exec_001"):
    return _event(
        event_id,
        "action.started",
        {
            "execution_id": execution_id,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
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
            "error": "tool failed",
        },
    )


def _retry_requested(**overrides):
    payload = {
        "retry_id": "retry_001",
        "run_id": "run_001",
        "original_proposal_id": "prop_001",
        "original_execution_id": "exec_001",
        "reason": "transient tool failure",
        "requested_by": "agent_supervisor",
    }
    payload.update(overrides)
    return _event("evt_006", "action.retry_requested", payload)


def _retry_created(**overrides):
    payload = {
        "retry_id": "retry_001",
        "new_proposal_id": "prop_retry_001",
        "original_proposal_id": "prop_001",
        "basis_event_id": "evt_006",
        "policy_basis": {"decision_id": "dec_retry_001"},
    }
    payload.update(overrides)
    return _event("evt_007", "action.retry_created", payload)


def _failed_action_events():
    return [_run_created(), _proposal(), _decision(), _started(), _failed()]


def _without(mapping: dict, key: str) -> dict:
    result = dict(mapping)
    result.pop(key)
    return result


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def test_retry_read_model_preserves_original_action_lineage():
    state = projector.RunProjector().project([*_failed_action_events(), _retry_requested(), _retry_created()])

    assert hasattr(state, "action_retries")
    assert state.action_retries["retry_001"] == {
        "retry_id": "retry_001",
        "original_proposal_id": "prop_001",
        "original_execution_id": "exec_001",
        "new_proposal_id": "prop_retry_001",
        "status": "created",
        "basis_event_id": "evt_006",
    }
    assert state.actions["exec_001"]["status"] == "failed"


def test_retry_checkpoint_state_contains_retry_read_model():
    checkpoint = projector.RunProjector().create_checkpoint(
        "run_001",
        [*_failed_action_events(), _retry_requested(), _retry_created()],
    )

    assert "action_retries" in checkpoint["state"]
    assert checkpoint["state"]["action_retries"]["retry_001"]["original_execution_id"] == "exec_001"


def test_retry_execution_still_requires_policy_decision():
    with pytest.raises(ValueError, match="action.started before approved decision"):
        projector.RunProjector().project(
            [
                *_failed_action_events(),
                _retry_requested(),
                _retry_created(),
                _proposal("evt_008", "prop_retry_001"),
                _started("evt_009", "prop_retry_001", "dec_retry_001", "exec_retry_001"),
            ]
        )


def test_retry_request_malformed_event_fails_fast():
    payload = _without(_retry_requested().payload, "retry_id")

    with pytest.raises(ValueError, match="action.retry_requested missing required field: retry_id"):
        projector.RunProjector().project([*_failed_action_events(), _event("evt_006", "action.retry_requested", payload)])


def test_retry_created_basis_event_must_match_retry_request():
    with pytest.raises(ValueError, match="action.retry_created basis_event_id must match action.retry_requested"):
        projector.RunProjector().project(
            [
                *_failed_action_events(),
                _retry_requested(),
                _retry_created(basis_event_id="evt_wrong"),
            ]
        )


def test_retry_created_must_use_new_proposal_identity():
    with pytest.raises(ValueError, match="action.retry_created new_proposal_id must differ from original_proposal_id"):
        projector.RunProjector().project(
            [
                *_failed_action_events(),
                _retry_requested(),
                _retry_created(new_proposal_id="prop_001"),
            ]
        )


def test_projector_reuse_does_not_allow_stale_retry_request_state():
    project = projector.RunProjector()
    project.project([*_failed_action_events(), _retry_requested()])

    with pytest.raises(ValueError, match="action.retry_created requires action.retry_requested"):
        project.project([*_failed_action_events(), _retry_created()])


def test_retry_read_model_checkpoint_assisted_rebuild_matches_full_replay(tmp_path):
    canonical_events = [*_failed_action_events(), _retry_requested(), _retry_created()]
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:6])
    checkpoints.save_checkpoint("run_001", checkpoint)

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)
    full = projector.RunProjector().project(canonical_events)

    assert assisted == full
    assert assisted.action_retries["retry_001"]["status"] == "created"
