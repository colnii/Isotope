import json
from pathlib import Path

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
        "registry_id": "default",
        "registry_version": "v0.2",
    }
    payload.update(overrides)
    return _event("evt_003", "action.proposed", payload)


def _decided(**overrides):
    payload = {
        "decision_id": "dec_001",
        "proposal_id": "prop_001",
        "outcome": "approved",
        "policy_profile_id": "default",
        "policy_version": "v0.2",
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


def _artifact_created(**overrides):
    artifact = {
        "ref": ARTIFACT_REF,
        "artifact_type": "text",
        "summary": "hello artifact",
        "provenance": {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"},
    }
    artifact.update(overrides)
    return _event("evt_006", "artifact.created", {"artifact": artifact})


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


def _happy_path_events(**run_created_overrides):
    return [
        _run_created(**run_created_overrides),
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


def _event_log_text(root: Path, run_id="run_001"):
    path = root / "runs" / run_id / "events.jsonl"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_run_projector_save_checkpoint_exists():
    assert hasattr(projector.RunProjector(), "save_checkpoint")


def test_save_checkpoint_reads_canonical_events_from_event_store(tmp_path):
    class RecordingEventStore:
        def __init__(self, canonical_events):
            self.canonical_events = canonical_events
            self.listed_run_ids = []

        def list_events(self, run_id):
            self.listed_run_ids.append(run_id)
            return list(self.canonical_events)

    events_store = RecordingEventStore(_happy_path_events())
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)

    projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert events_store.listed_run_ids == ["run_001"]


def test_save_checkpoint_uses_projector_owned_create_checkpoint(monkeypatch, tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    project = projector.RunProjector()
    calls = []
    real_create = project.create_checkpoint

    def recording_create_checkpoint(run_id, events_arg, projector_version="run_projector@v1"):
        events_list = list(events_arg)
        calls.append((run_id, [event.event_id for event in events_list], projector_version))
        return real_create(run_id, events_list, projector_version)

    monkeypatch.setattr(project, "create_checkpoint", recording_create_checkpoint)

    project.save_checkpoint("run_001", events_store, checkpoint_store.FileCheckpointStore(tmp_path))

    assert calls == [("run_001", [event.event_id for event in canonical_events], "run_projector@v1")]


def test_save_checkpoint_calls_checkpoint_store_save(tmp_path):
    class RecordingCheckpointStore:
        def __init__(self):
            self.saved = []

        def save_checkpoint(self, run_id, checkpoint):
            self.saved.append((run_id, checkpoint))
            return checkpoint

    events_store = event_store.FileEventStore(tmp_path)
    _write_events(events_store, _happy_path_events())
    checkpoints = RecordingCheckpointStore()

    saved = projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.saved == [("run_001", saved)]
    assert saved["basis_event_id"] == "evt_008"


def test_saved_checkpoint_can_be_loaded_from_checkpoint_store(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, _happy_path_events())

    saved = projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.load_latest_checkpoint("run_001") == saved


def test_saved_checkpoint_can_be_used_for_assisted_rebuild(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)

    projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)
    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_save_checkpoint_rejects_empty_event_log_without_writing_checkpoint(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)

    with pytest.raises(ValueError, match="cannot create checkpoint from empty events"):
        projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.load_latest_checkpoint("run_001") is None


def test_save_checkpoint_rejects_lifecycle_invalid_events_without_writing_checkpoint(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(
        events_store,
        [
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
        ],
    )

    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.load_latest_checkpoint("run_001") is None


def test_save_checkpoint_rejects_malformed_event_payload_without_writing_checkpoint(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, [_run_created(), _proposed(), _event("evt_004", "action.decided", {})])

    with pytest.raises(ValueError, match="action.decided missing required field"):
        projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.load_latest_checkpoint("run_001") is None


def test_save_checkpoint_does_not_modify_event_log(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, _happy_path_events())
    before = _event_log_text(tmp_path)

    projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert _event_log_text(tmp_path) == before


def test_save_checkpoint_only_uses_event_store_and_checkpoint_store_boundary(tmp_path):
    class BoundaryEventStore:
        def __init__(self, canonical_events):
            self.canonical_events = canonical_events
            self.called = []

        def list_events(self, run_id):
            self.called.append(("list_events", run_id))
            return list(self.canonical_events)

    class BoundaryCheckpointStore:
        def __init__(self):
            self.called = []

        def save_checkpoint(self, run_id, checkpoint):
            self.called.append(("save_checkpoint", run_id))
            return checkpoint

    events_store = BoundaryEventStore(_happy_path_events())
    checkpoints = BoundaryCheckpointStore()

    projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert events_store.called == [("list_events", "run_001")]
    assert checkpoints.called == [("save_checkpoint", "run_001")]


def test_saved_checkpoint_basis_event_id_is_last_event_id(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, _happy_path_events())

    saved = projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert saved["basis_event_id"] == "evt_008"


def test_saved_checkpoint_excludes_artifact_content_and_external_raw_input(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(
        events_store,
        _happy_path_events(
            raw_input="raw user input",
            provider_response={"raw": "provider"},
            imported_snapshot={"raw": "snapshot"},
        ),
    )

    saved = projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)
    serialized = json.dumps(saved)

    assert "content" not in saved["state"]["artifacts"][0]
    assert "raw_input" not in serialized
    assert "provider_response" not in serialized
    assert "imported_snapshot" not in serialized
