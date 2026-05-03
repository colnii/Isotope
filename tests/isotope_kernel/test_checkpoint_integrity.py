import copy
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone

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
                "summary": "中文 summary",
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


def _hash_payload(checkpoint):
    payload = copy.deepcopy(checkpoint)
    payload.pop("integrity", None)
    payload.pop("checkpoint_hash", None)
    return payload


def _expected_hash(checkpoint):
    encoded = json.dumps(
        _hash_payload(checkpoint),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _attach_integrity(checkpoint, checkpoint_hash=None):
    checkpoint = copy.deepcopy(checkpoint)
    checkpoint["integrity"] = {
        "algorithm": "sha256",
        "checkpoint_hash": checkpoint_hash or _expected_hash(checkpoint),
    }
    return checkpoint


def _state_at(canonical_events, event_id):
    index = next(index for index, event in enumerate(canonical_events) if event.event_id == event_id)
    return asdict(projector.RunProjector().project(canonical_events[: index + 1]))


def _legacy_checkpoint(state, basis_event_id="evt_005"):
    return {
        "run_id": "run_001",
        "projector_version": "run_projector@v1",
        "basis_event_id": basis_event_id,
        "state": state,
        "created_at": "2026-04-28T00:00:00Z",
    }


def _stores(tmp_path, canonical_events=None):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events or _happy_path_events())
    return events_store, checkpoints


def test_create_checkpoint_includes_integrity_field():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert "integrity" in checkpoint


def test_checkpoint_integrity_contains_sha256_algorithm_and_hash():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert checkpoint["integrity"]["algorithm"] == "sha256"
    assert checkpoint["integrity"]["checkpoint_hash"]


def test_checkpoint_hash_uses_deterministic_canonical_json_excluding_integrity():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert checkpoint["integrity"]["checkpoint_hash"] == _expected_hash(checkpoint)


def test_checkpoint_hash_is_stable_for_same_checkpoint_content(monkeypatch):
    class FrozenDateTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 4, 28, 0, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(projector, "datetime", FrozenDateTime)

    first = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())
    second = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert first["integrity"]["checkpoint_hash"] == second["integrity"]["checkpoint_hash"]


def test_modified_checkpoint_state_fails_hash_validation_and_falls_back(tmp_path, monkeypatch):
    canonical_events = _happy_path_events()
    events_store, checkpoints = _stores(tmp_path, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:5])
    checkpoint["state"]["status"] = "completed"
    checkpoints.save_checkpoint("run_001", checkpoint)

    def fail_if_checkpoint_state_is_used(*args, **kwargs):
        raise AssertionError("hash mismatch checkpoint must not be used")

    project = projector.RunProjector()
    monkeypatch.setattr(project, "_run_state_from_checkpoint", fail_if_checkpoint_state_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_hash_mismatch_falls_back_to_full_rebuild(tmp_path, monkeypatch):
    canonical_events = _happy_path_events()
    events_store, checkpoints = _stores(tmp_path, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:5])
    checkpoint["integrity"]["checkpoint_hash"] = "0" * 64
    checkpoints.save_checkpoint("run_001", checkpoint)

    def fail_if_checkpoint_state_is_used(*args, **kwargs):
        raise AssertionError("hash mismatch checkpoint must not be used")

    project = projector.RunProjector()
    monkeypatch.setattr(project, "_run_state_from_checkpoint", fail_if_checkpoint_state_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_legacy_checkpoint_without_hash_still_uses_existing_validation(tmp_path):
    canonical_events = _happy_path_events()
    events_store, checkpoints = _stores(tmp_path, canonical_events)
    checkpoints.save_checkpoint("run_001", _legacy_checkpoint(_state_at(canonical_events, "evt_005")))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_hash_match_still_validates_checkpoint_state_schema(tmp_path):
    events_store, checkpoints = _stores(tmp_path)
    checkpoint = _attach_integrity(_legacy_checkpoint({"run_id": "run_001"}, basis_event_id="evt_005"))
    checkpoints.save_checkpoint("run_001", checkpoint)

    with pytest.raises(ValueError, match="checkpoint state missing required field"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_hash_match_still_validates_prefix_consistency(tmp_path):
    canonical_events = _happy_path_events()
    events_store, checkpoints = _stores(tmp_path, canonical_events)
    state = _state_at(canonical_events, "evt_005")
    state["status"] = "completed"
    checkpoint = _attach_integrity(_legacy_checkpoint(state, basis_event_id="evt_005"))
    checkpoints.save_checkpoint("run_001", checkpoint)

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_malformed_checkpoint_file_still_fails_fast(tmp_path):
    events_store, checkpoints = _stores(tmp_path)
    path = checkpoints.checkpoint_path("run_001")
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed checkpoint file"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_file_checkpoint_store_persists_integrity_without_interpreting_state(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint = _attach_integrity(
        _legacy_checkpoint(
            {"status": "nonsense_but_opaque"},
            basis_event_id="evt_999",
        )
    )

    checkpoints.save_checkpoint("run_001", checkpoint)

    assert checkpoints.load_latest_checkpoint("run_001") == checkpoint


def test_hash_mismatch_cannot_hide_lifecycle_invalid_event_log(tmp_path):
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
    events_store, checkpoints = _stores(tmp_path, invalid_events)
    state = _state_at(_happy_path_events(), "evt_005")
    checkpoint = _attach_integrity(_legacy_checkpoint(state, basis_event_id="evt_005"), checkpoint_hash="0" * 64)
    checkpoints.save_checkpoint("run_001", checkpoint)

    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)
