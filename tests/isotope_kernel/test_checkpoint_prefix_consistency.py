from dataclasses import asdict

import pytest

from isotope_kernel import checkpoint_store, event_store, events, projector


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


def _agent_created():
    return _event("evt_002", "agent.created", {"agent_id": "agent_supervisor"})


def _proposed():
    return _event(
        "evt_003",
        "action.proposed",
        {
            "proposal_id": "prop_001",
            "agent_id": "agent_supervisor",
            "action_type": "call_tool",
        },
    )


def _decided():
    return _event(
        "evt_004",
        "action.decided",
        {
            "decision_id": "dec_001",
            "proposal_id": "prop_001",
            "outcome": "approved",
        },
    )


def _started():
    return _event(
        "evt_005",
        "action.started",
        {
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
        },
    )


def _artifact_created():
    return _event(
        "evt_006",
        "artifact.created",
        {
            "artifact": {
                "ref": ARTIFACT_REF,
                "artifact_type": "text",
                "summary": "hello artifact",
                "provenance": {"execution_id": "exec_001"},
            }
        },
    )


def _completed():
    return _event(
        "evt_007",
        "action.completed",
        {
            "execution_id": "exec_001",
            "status": "completed",
            "artifact_refs": [ARTIFACT_REF],
        },
    )


def _run_completed():
    return _event("evt_008", "run.completed", {"status": "completed"})


def _happy_path_events():
    return [
        _run_created(),
        _agent_created(),
        _proposed(),
        _decided(),
        _started(),
        _artifact_created(),
        _completed(),
        _run_completed(),
    ]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def _state_at(canonical_events, event_id):
    index = next(index for index, event in enumerate(canonical_events) if event.event_id == event_id)
    return asdict(projector.RunProjector().project(canonical_events[: index + 1]))


def _checkpoint(state, basis_event_id="evt_008"):
    return {
        "run_id": "run_001",
        "projector_version": "run_projector@v1",
        "basis_event_id": basis_event_id,
        "state": state,
        "created_at": "2026-04-28T00:00:00Z",
    }


def _stores_with_checkpoint(tmp_path, checkpoint, canonical_events=None):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events or _happy_path_events())
    checkpoints.save_checkpoint("run_001", checkpoint)
    return events_store, checkpoints


def test_consistent_checkpoint_state_rebuilds_equivalent_to_full_rebuild(tmp_path):
    canonical_events = _happy_path_events()
    checkpoint = _checkpoint(_state_at(canonical_events, "evt_005"), basis_event_id="evt_005")
    events_store, checkpoints = _stores_with_checkpoint(tmp_path, checkpoint, canonical_events)

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_checkpoint_status_mismatch_falls_back_to_full_rebuild(tmp_path):
    state = _state_at(_happy_path_events(), "evt_008")
    state["status"] = "running"
    events_store, checkpoints = _stores_with_checkpoint(tmp_path, _checkpoint(state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_checkpoint_current_agent_mismatch_falls_back_to_full_rebuild(tmp_path):
    state = _state_at(_happy_path_events(), "evt_008")
    state["current_agent"] = "agent_other"
    events_store, checkpoints = _stores_with_checkpoint(tmp_path, _checkpoint(state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_checkpoint_actions_mismatch_falls_back_to_full_rebuild(tmp_path):
    state = _state_at(_happy_path_events(), "evt_008")
    state["actions"]["exec_001"]["status"] = "failed"
    events_store, checkpoints = _stores_with_checkpoint(tmp_path, _checkpoint(state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_checkpoint_artifacts_mismatch_falls_back_to_full_rebuild(tmp_path):
    state = _state_at(_happy_path_events(), "evt_008")
    state["artifacts"][0]["summary"] = "corrupted summary"
    events_store, checkpoints = _stores_with_checkpoint(tmp_path, _checkpoint(state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_checkpoint_extra_action_falls_back_to_full_rebuild(tmp_path):
    state = _state_at(_happy_path_events(), "evt_008")
    state["actions"]["exec_extra"] = {"execution_id": "exec_extra", "status": "completed"}
    events_store, checkpoints = _stores_with_checkpoint(tmp_path, _checkpoint(state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_checkpoint_missing_artifact_falls_back_to_full_rebuild(tmp_path):
    state = _state_at(_happy_path_events(), "evt_008")
    state["artifacts"] = []
    events_store, checkpoints = _stores_with_checkpoint(tmp_path, _checkpoint(state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_mismatch_fallback_full_rebuild_still_validates_event_log(tmp_path):
    invalid_events = [
        _run_created(),
        _agent_created(),
        _proposed(),
        _decided(),
        _started(),
        _event(
            "evt_006",
            "action.completed",
            {
                "execution_id": "exec_other",
                "status": "completed",
                "artifact_refs": [ARTIFACT_REF],
            },
        ),
    ]
    state = _state_at(_happy_path_events(), "evt_005")
    state["status"] = "completed"
    events_store, checkpoints = _stores_with_checkpoint(
        tmp_path,
        _checkpoint(state, basis_event_id="evt_005"),
        invalid_events,
    )

    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_file_checkpoint_store_remains_opaque_for_prefix_consistency(tmp_path):
    state = _state_at(_happy_path_events(), "evt_008")
    state["current_agent"] = "agent_other"
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint = _checkpoint(state)

    checkpoints.save_checkpoint("run_001", checkpoint)

    assert checkpoints.load_latest_checkpoint("run_001") == checkpoint
