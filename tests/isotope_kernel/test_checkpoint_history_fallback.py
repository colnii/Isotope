import copy
import json

import pytest

from isotope_kernel import checkpoint_store, event_store, events, projector


def _event(event_id, event_type, payload):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-04-21T00:00:{event_id[-3:]}+00:00",
    )


def _artifact_ref():
    return {
        "ref_type": "artifact",
        "scope": "run",
        "run_id": "run_001",
        "artifact_id": "artifact_001",
    }


def _happy_path_events():
    ref = _artifact_ref()
    return [
        _event("evt_001", "run.created", {"run_id": "run_001"}),
        _event("evt_002", "agent.created", {"agent_id": "agent_supervisor"}),
        _event(
            "evt_003",
            "action.decided",
            {
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
                "outcome": "approved",
            },
        ),
        _event(
            "evt_004",
            "action.started",
            {
                "execution_id": "exec_001",
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
            },
        ),
        _event(
            "evt_005",
            "artifact.created",
            {
                "artifact": {
                    "ref": ref,
                    "artifact_type": "text",
                    "summary": "artifact summary",
                    "provenance": {"execution_id": "exec_001"},
                }
            },
        ),
        _event(
            "evt_006",
            "action.completed",
            {
                "execution_id": "exec_001",
                "status": "completed",
                "artifact_refs": [ref],
            },
        ),
        _event("evt_007", "run.completed", {"status": "completed"}),
    ]


def _lifecycle_invalid_events():
    return [
        _event("evt_001", "run.created", {"run_id": "run_001"}),
        _event(
            "evt_002",
            "action.decided",
            {
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
                "outcome": "denied",
            },
        ),
        _event(
            "evt_003",
            "action.started",
            {
                "execution_id": "exec_001",
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
            },
        ),
    ]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def _checkpoint_for_prefix(canonical_events, basis_event_id):
    basis_index = [event.event_id for event in canonical_events].index(basis_event_id)
    return projector.RunProjector().create_checkpoint("run_001", canonical_events[: basis_index + 1])


def _with_invalid_checkpoint_hash(checkpoint):
    checkpoint = copy.deepcopy(checkpoint)
    checkpoint["integrity"]["checkpoint_hash"] = "0" * 64
    return checkpoint


def _with_invalid_event_prefix_digest(checkpoint):
    checkpoint = copy.deepcopy(checkpoint)
    checkpoint["integrity"]["event_prefix_digest"] = "0" * 64
    return checkpoint


def _with_invalid_event_envelope_version(checkpoint):
    checkpoint = copy.deepcopy(checkpoint)
    checkpoint["integrity"]["event_digest_event_envelope_version"] = "canonical_event@future"
    return checkpoint


class CandidateCheckpointStore:
    def __init__(self, candidates):
        self.candidates = list(candidates)
        self.latest_loads = []
        self.candidate_loads = []

    def load_latest_checkpoint(self, run_id):
        self.latest_loads.append(run_id)
        return self.candidates[0] if self.candidates else None

    def load_checkpoint_candidates(self, run_id):
        self.candidate_loads.append(run_id)
        return list(self.candidates)


def test_file_checkpoint_store_exposes_run_scoped_checkpoint_candidates_newest_to_oldest(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint_dir = tmp_path / "runs" / "run_001" / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    older = {
        "run_id": "run_001",
        "projector_version": "run_projector@v1",
        "basis_event_id": "evt_003",
        "state": {"marker": "older"},
        "created_at": "2026-04-21T00:00:03+00:00",
    }
    latest = {
        "run_id": "run_001",
        "projector_version": "run_projector@v1",
        "basis_event_id": "evt_005",
        "state": {"marker": "latest"},
        "created_at": "2026-04-21T00:00:05+00:00",
    }
    (checkpoint_dir / "checkpoint-older.json").write_text(json.dumps(older), encoding="utf-8")
    (checkpoint_dir / "checkpoint-latest.json").write_text(json.dumps(latest), encoding="utf-8")

    candidates = store.load_checkpoint_candidates("run_001")

    assert [candidate["basis_event_id"] for candidate in candidates] == ["evt_005", "evt_003"]


def test_old_checkpoint_fallback_attempts_candidates_newest_to_oldest(tmp_path, monkeypatch):
    canonical_events = _happy_path_events()
    latest = _with_invalid_checkpoint_hash(_checkpoint_for_prefix(canonical_events, "evt_005"))
    older = _checkpoint_for_prefix(canonical_events, "evt_003")
    checkpoints = CandidateCheckpointStore([latest, older])
    events_store = event_store.FileEventStore(tmp_path)
    _write_events(events_store, canonical_events)
    project = projector.RunProjector()
    used_basis_ids = []
    original = project._run_state_from_checkpoint

    def record_checkpoint_state_use(state, run_id, basis_event_id):
        used_basis_ids.append(basis_event_id)
        return original(state, run_id, basis_event_id)

    monkeypatch.setattr(project, "_run_state_from_checkpoint", record_checkpoint_state_use)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.candidate_loads == ["run_001"]
    assert used_basis_ids == ["evt_003"]
    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


@pytest.mark.parametrize(
    "poison",
    [
        _with_invalid_checkpoint_hash,
        _with_invalid_event_prefix_digest,
        _with_invalid_event_envelope_version,
    ],
)
def test_invalid_latest_checkpoint_is_not_partially_read_before_older_fallback(
    tmp_path,
    monkeypatch,
    poison,
):
    canonical_events = _happy_path_events()
    latest = poison(_checkpoint_for_prefix(canonical_events, "evt_005"))
    older = _checkpoint_for_prefix(canonical_events, "evt_003")
    checkpoints = CandidateCheckpointStore([latest, older])
    events_store = event_store.FileEventStore(tmp_path)
    _write_events(events_store, canonical_events)
    project = projector.RunProjector()
    used_basis_ids = []
    original = project._run_state_from_checkpoint

    def record_checkpoint_state_use(state, run_id, basis_event_id):
        used_basis_ids.append(basis_event_id)
        return original(state, run_id, basis_event_id)

    monkeypatch.setattr(project, "_run_state_from_checkpoint", record_checkpoint_state_use)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert "evt_005" not in used_basis_ids
    assert used_basis_ids == ["evt_003"]
    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_older_checkpoint_fallback_cannot_hide_lifecycle_invalid_event_log(tmp_path):
    valid_events = _happy_path_events()
    invalid_events = _lifecycle_invalid_events()
    latest = _with_invalid_checkpoint_hash(_checkpoint_for_prefix(valid_events, "evt_005"))
    older = _checkpoint_for_prefix(valid_events, "evt_003")
    checkpoints = CandidateCheckpointStore([latest, older])
    events_store = event_store.FileEventStore(tmp_path)
    _write_events(events_store, invalid_events)

    with pytest.raises(ValueError, match="action.started after denied decision"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.candidate_loads == ["run_001"]


def test_all_invalid_checkpoint_candidates_fall_back_to_full_rebuild_without_using_state(
    tmp_path,
    monkeypatch,
):
    canonical_events = _happy_path_events()
    latest = _with_invalid_checkpoint_hash(_checkpoint_for_prefix(canonical_events, "evt_005"))
    older = _with_invalid_event_prefix_digest(_checkpoint_for_prefix(canonical_events, "evt_003"))
    checkpoints = CandidateCheckpointStore([latest, older])
    events_store = event_store.FileEventStore(tmp_path)
    _write_events(events_store, canonical_events)
    project = projector.RunProjector()
    used_basis_ids = []
    original = project._run_state_from_checkpoint

    def record_checkpoint_state_use(state, run_id, basis_event_id):
        used_basis_ids.append(basis_event_id)
        return original(state, run_id, basis_event_id)

    monkeypatch.setattr(project, "_run_state_from_checkpoint", record_checkpoint_state_use)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert checkpoints.candidate_loads == ["run_001"]
    assert used_basis_ids == []
    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_file_checkpoint_store_candidate_loading_remains_opaque(tmp_path):
    store = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint_dir = tmp_path / "runs" / "run_001" / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    opaque_checkpoint = {
        "run_id": "run_001",
        "projector_version": "run_projector@future",
        "basis_event_id": "evt_001",
        "state": {"status": "opaque_to_storage"},
        "created_at": "2026-04-21T00:00:01+00:00",
        "integrity": {"algorithm": "unknown", "checkpoint_hash": "not-storage-business"},
    }
    (checkpoint_dir / "checkpoint-opaque.json").write_text(
        json.dumps(opaque_checkpoint),
        encoding="utf-8",
    )

    candidates = store.load_checkpoint_candidates("run_001")

    assert candidates == [opaque_checkpoint]
