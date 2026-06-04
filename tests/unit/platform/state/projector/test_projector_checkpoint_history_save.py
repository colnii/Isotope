import pytest

import isotope.platform.state.checkpoint_store as checkpoint_store
import isotope.platform.state.event_store as event_store
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
            "registry_id": "default",
            "registry_version": "v0.2",
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
            "policy_profile_id": "default",
            "policy_version": "v0.2",
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
                "provenance": {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"},
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


def _history_candidate_files(root, run_id="run_001"):
    checkpoint_dir = root / "runs" / run_id / "checkpoints"
    if not checkpoint_dir.exists():
        return []
    return sorted(path for path in checkpoint_dir.glob("*.json") if path.name != "latest.json")


def _latest_checkpoint_path(root, run_id="run_001"):
    return root / "runs" / run_id / "checkpoints" / "latest.json"


def test_run_projector_exposes_explicit_save_checkpoint_history_method():
    assert hasattr(projector.RunProjector(), "save_checkpoint_history")


def test_save_checkpoint_history_reads_canonical_events_from_event_store(tmp_path):
    class RecordingEventStore:
        def __init__(self, canonical_events):
            self.canonical_events = canonical_events
            self.listed_run_ids = []

        def list_events(self, run_id):
            self.listed_run_ids.append(run_id)
            return list(self.canonical_events)

    events_store = RecordingEventStore(_happy_path_events())
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)

    projector.RunProjector().save_checkpoint_history("run_001", events_store, checkpoints)

    assert events_store.listed_run_ids == ["run_001"]


def test_save_checkpoint_history_uses_projector_owned_create_checkpoint(monkeypatch, tmp_path):
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

    project.save_checkpoint_history("run_001", events_store, checkpoint_store.FileCheckpointStore(tmp_path))

    assert calls == [("run_001", [event.event_id for event in canonical_events], "run_projector@v1")]


def test_save_checkpoint_history_calls_checkpoint_store_history_save(tmp_path):
    class RecordingCheckpointStore:
        def __init__(self):
            self.history_saved = []

        def save_checkpoint_history(self, run_id, checkpoint):
            self.history_saved.append((run_id, checkpoint))
            return checkpoint

        def save_checkpoint(self, run_id, checkpoint):
            raise AssertionError("history save must not call latest save")

    events_store = event_store.FileEventStore(tmp_path)
    _write_events(events_store, _happy_path_events())
    checkpoints = RecordingCheckpointStore()

    saved = projector.RunProjector().save_checkpoint_history("run_001", events_store, checkpoints)

    assert checkpoints.history_saved == [("run_001", saved)]
    assert saved["basis_event_id"] == "evt_008"


def test_save_checkpoint_history_does_not_write_latest_checkpoint(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, _happy_path_events())

    saved = projector.RunProjector().save_checkpoint_history("run_001", events_store, checkpoints)

    assert _latest_checkpoint_path(tmp_path).exists() is False
    assert checkpoints.load_checkpoint_candidates("run_001") == [saved]
    assert _history_candidate_files(tmp_path)


def test_save_checkpoint_history_rejects_empty_event_log_without_writing_history(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)

    with pytest.raises(ValueError, match="cannot create checkpoint from empty events"):
        projector.RunProjector().save_checkpoint_history("run_001", events_store, checkpoints)

    assert _history_candidate_files(tmp_path) == []
    assert checkpoints.load_latest_checkpoint("run_001") is None


def test_save_checkpoint_history_rejects_lifecycle_invalid_events_without_writing_history(tmp_path):
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
        projector.RunProjector().save_checkpoint_history("run_001", events_store, checkpoints)

    assert _history_candidate_files(tmp_path) == []
    assert checkpoints.load_latest_checkpoint("run_001") is None


def test_save_checkpoint_history_rejects_malformed_events_without_writing_history(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, [_run_created(), _proposed(), _event("evt_004", "action.decided", {})])

    with pytest.raises(ValueError, match="action.decided missing required field"):
        projector.RunProjector().save_checkpoint_history("run_001", events_store, checkpoints)

    assert _history_candidate_files(tmp_path) == []
    assert checkpoints.load_latest_checkpoint("run_001") is None


def test_save_checkpoint_history_failure_does_not_stub_success(tmp_path):
    class FailingHistoryCheckpointStore:
        def save_checkpoint_history(self, run_id, checkpoint):
            raise RuntimeError("history write failed")

        def save_checkpoint(self, run_id, checkpoint):
            raise AssertionError("history save must not call latest save")

    events_store = event_store.FileEventStore(tmp_path)
    _write_events(events_store, _happy_path_events())

    with pytest.raises(RuntimeError, match="history write failed"):
        projector.RunProjector().save_checkpoint_history(
            "run_001",
            events_store,
            FailingHistoryCheckpointStore(),
        )


def test_save_checkpoint_remains_latest_only_and_does_not_call_history_save(tmp_path):
    class LatestOnlyCheckpointStore:
        def __init__(self):
            self.latest_saved = []

        def save_checkpoint(self, run_id, checkpoint):
            self.latest_saved.append((run_id, checkpoint))
            return checkpoint

        def save_checkpoint_history(self, run_id, checkpoint):
            raise AssertionError("latest save must not call history save")

    events_store = event_store.FileEventStore(tmp_path)
    _write_events(events_store, _happy_path_events())
    checkpoints = LatestOnlyCheckpointStore()

    saved = projector.RunProjector().save_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.latest_saved == [("run_001", saved)]
