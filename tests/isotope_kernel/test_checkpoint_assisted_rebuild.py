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


def _checkpoint(run_id, basis_event_id, state, projector_version="run_projector@v1"):
    return {
        "run_id": run_id,
        "projector_version": projector_version,
        "basis_event_id": basis_event_id,
        "state": asdict(state),
        "created_at": "2026-04-28T00:00:00Z",
    }


def test_rebuild_with_checkpoint_without_checkpoint_matches_full_rebuild(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, _happy_path_events())

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)
    full = projector.RunProjector().rebuild("run_001", events_store)

    assert assisted == full


def test_rebuild_with_checkpoint_ignores_incompatible_checkpoint_version(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    wrong_state = projector.RunState(run_id="run_001", status="nonsense", last_event_id="evt_005")
    checkpoints.save_checkpoint(
        "run_001",
        _checkpoint("run_001", "evt_005", wrong_state, projector_version="old_projector"),
    )

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().project(canonical_events)


def test_rebuild_with_checkpoint_replays_events_after_basis(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    basis_state = projector.RunProjector().project(canonical_events[:5])
    checkpoints.save_checkpoint("run_001", _checkpoint("run_001", "evt_005", basis_state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().project(canonical_events)
    assert assisted.status == "completed"
    assert assisted.artifacts[0]["summary"] == "hello artifact"
    assert assisted.last_event_id == "evt_008"


def test_rebuild_with_checkpoint_rejects_missing_basis_event(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    basis_state = projector.RunProjector().project(canonical_events[:5])
    checkpoints.save_checkpoint("run_001", _checkpoint("run_001", "evt_missing", basis_state))

    with pytest.raises(ValueError, match="checkpoint basis_event_id not found"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_rebuild_with_checkpoint_rejects_mismatched_checkpoint_run_id(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, _happy_path_events())
    path = checkpoints.checkpoint_path("run_001")
    path.parent.mkdir(parents=True)
    path.write_text(
        "{"
        '"run_id": "run_002",'
        '"projector_version": "run_projector@v1",'
        '"basis_event_id": "evt_005",'
        '"state": {"run_id": "run_002"},'
        '"created_at": "2026-04-28T00:00:00Z"'
        "}",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="malformed checkpoint file|checkpoint run_id"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_checkpoint_cannot_hide_lifecycle_invalid_event_before_basis(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    invalid_events = [
        _run_created(),
        _event(
            "evt_002",
            "action.completed",
            {
                "execution_id": "exec_001",
                "status": "completed",
                "artifact_refs": [ARTIFACT_REF],
            },
        ),
        _event("evt_003", "agent.created", {"agent_id": "agent_supervisor"}),
    ]
    _write_events(events_store, invalid_events)
    checkpoints.save_checkpoint(
        "run_001",
        _checkpoint("run_001", "evt_003", projector.RunState(run_id="run_001", status="completed")),
    )

    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_rebuild_with_checkpoint_reads_checkpoint_store_and_event_log(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    basis_state = projector.RunProjector().project(canonical_events[:5])
    checkpoints.save_checkpoint("run_001", _checkpoint("run_001", "evt_005", basis_state))

    class RecordingCheckpointStore:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.loaded_run_ids = []

        def load_latest_checkpoint(self, run_id):
            self.loaded_run_ids.append(run_id)
            return self.wrapped.load_latest_checkpoint(run_id)

    class RecordingEventStore:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.listed_run_ids = []

        def list_events(self, run_id):
            self.listed_run_ids.append(run_id)
            return self.wrapped.list_events(run_id)

    recording_checkpoints = RecordingCheckpointStore(checkpoints)
    recording_events = RecordingEventStore(events_store)

    state = projector.RunProjector().rebuild_with_checkpoint(
        "run_001",
        recording_events,
        recording_checkpoints,
    )

    assert state == projector.RunProjector().project(canonical_events)
    assert recording_checkpoints.loaded_run_ids == ["run_001"]
    assert recording_events.listed_run_ids == ["run_001"]
