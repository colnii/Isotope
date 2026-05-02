import json

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


def _run_created(**overrides):
    payload = {"run_id": "run_001"}
    payload.update(overrides)
    return _event("evt_001", "run.created", payload)


def _agent_created():
    return _event("evt_002", "agent.created", {"agent_id": "agent_supervisor"})


def _proposed(**overrides):
    payload = {
        "proposal_id": "prop_001",
        "agent_id": "agent_supervisor",
        "action_type": "call_tool",
    }
    payload.update(overrides)
    return _event("evt_003", "action.proposed", payload)


def _decided(**overrides):
    payload = {
        "decision_id": "dec_001",
        "proposal_id": "prop_001",
        "outcome": "approved",
    }
    payload.update(overrides)
    return _event("evt_004", "action.decided", payload)


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


def test_run_projector_create_checkpoint_exists():
    assert hasattr(projector.RunProjector(), "create_checkpoint")


def test_create_checkpoint_projects_canonical_events_and_returns_blob():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert checkpoint["run_id"] == "run_001"
    assert checkpoint["projector_version"] == "run_projector@v1"
    assert checkpoint["state"]["status"] == "completed"
    assert checkpoint["state"]["current_agent"] == "agent_supervisor"
    assert checkpoint["state"]["last_event_id"] == "evt_008"
    assert checkpoint["state"]["artifacts"][0]["summary"] == "hello artifact"


def test_checkpoint_contains_required_fields():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert set(checkpoint) == {"run_id", "projector_version", "basis_event_id", "state", "created_at", "integrity"}


def test_checkpoint_basis_event_id_is_last_replayed_event_id():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert checkpoint["basis_event_id"] == "evt_008"


def test_checkpoint_state_contains_minimal_projected_state_fields():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert set(checkpoint["state"]) == {
        "run_id",
        "status",
        "current_agent",
        "agents",
        "workers",
        "workspaces",
        "actions",
        "approvals",
        "artifacts",
        "external_observations",
        "memory_records",
        "last_event_id",
    }
    assert checkpoint["state"]["run_id"] == "run_001"


def test_checkpoint_state_excludes_artifact_content():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert "content" not in checkpoint["state"]["artifacts"][0]


def test_checkpoint_excludes_external_raw_input_keys():
    canonical_events = [
        _run_created(raw_input="raw user input", provider_response={"raw": "model"}, imported_snapshot={"raw": "snap"}),
        _agent_created(),
        _proposed(raw_input="raw proposal"),
        _decided(),
        _started(),
        _artifact_created(),
        _completed(),
        _run_completed(),
    ]

    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events)
    serialized = json.dumps(checkpoint)

    assert "raw_input" not in serialized
    assert "provider_response" not in serialized
    assert "imported_snapshot" not in serialized


def test_create_checkpoint_fails_fast_for_lifecycle_invalid_events():
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
    ]

    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().create_checkpoint("run_001", invalid_events)


def test_create_checkpoint_fails_fast_for_malformed_event_payload():
    malformed_events = [_run_created(), _proposed(), _event("evt_004", "action.decided", {"proposal_id": "prop_001"})]

    with pytest.raises(ValueError, match="action.decided missing required field"):
        projector.RunProjector().create_checkpoint("run_001", malformed_events)


def test_create_checkpoint_rejects_empty_events():
    with pytest.raises(ValueError, match="cannot create checkpoint from empty events"):
        projector.RunProjector().create_checkpoint("run_001", [])


def test_create_checkpoint_does_not_write_checkpoint_store(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)

    projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert store.load_latest_checkpoint("run_001") is None
    assert not store.checkpoint_path("run_001").exists()


def test_created_checkpoint_can_be_saved_and_used_for_assisted_rebuild(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:5])

    checkpoints.save_checkpoint("run_001", checkpoint)
    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().project(canonical_events)
