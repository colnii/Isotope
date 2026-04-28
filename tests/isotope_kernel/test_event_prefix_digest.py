import copy
import hashlib
import json
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


def _proposed(**overrides):
    payload = {
        "proposal_id": "prop_001",
        "agent_id": "agent_supervisor",
        "action_type": "call_tool",
    }
    payload.update(overrides)
    return _event("evt_003", "action.proposed", payload)


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


def _happy_path_events_with_changed_prefix_payload():
    return [
        _run_created(),
        _agent_created(),
        _proposed(action_type="call_tool_payload_changed"),
        _decided(),
        _started(),
        _artifact_created(),
        _completed(),
        _run_completed(),
    ]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def _event_prefix_payload(canonical_events):
    return [
        {
            "event_id": event.event_id,
            "run_id": event.run_id,
            "event_type": event.event_type,
            "payload": event.payload,
            "created_at": event.created_at,
            "event_envelope_version": event.event_envelope_version,
        }
        for event in canonical_events
    ]


def _expected_event_prefix_digest(canonical_events):
    encoded = json.dumps(
        _event_prefix_payload(canonical_events),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _checkpoint_payload_for_hash(checkpoint):
    payload = copy.deepcopy(checkpoint)
    payload.pop("integrity", None)
    payload.pop("checkpoint_hash", None)
    return payload


def _checkpoint_hash(checkpoint):
    encoded = json.dumps(
        _checkpoint_payload_for_hash(checkpoint),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _refresh_checkpoint_hash(checkpoint):
    checkpoint["integrity"]["checkpoint_hash"] = _checkpoint_hash(checkpoint)
    return checkpoint


def _legacy_checkpoint_without_event_prefix_digest(checkpoint):
    checkpoint = copy.deepcopy(checkpoint)
    for key in (
        "event_digest_algorithm",
        "event_prefix_digest",
        "event_digest_basis_event_id",
        "event_digest_event_count",
    ):
        checkpoint["integrity"].pop(key, None)
    return checkpoint


def test_create_checkpoint_includes_event_prefix_digest_metadata():
    canonical_events = _happy_path_events()

    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events)

    integrity = checkpoint["integrity"]
    assert integrity["event_digest_algorithm"] == "sha256"
    assert integrity["event_prefix_digest"] == _expected_event_prefix_digest(canonical_events)
    assert integrity["event_digest_basis_event_id"] == checkpoint["basis_event_id"]
    assert integrity["event_digest_event_count"] == len(canonical_events)


def test_event_prefix_digest_is_stable_for_same_event_prefix(monkeypatch):
    class FrozenDateTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 4, 28, 0, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(projector, "datetime", FrozenDateTime)

    first = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())
    second = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert first["integrity"]["event_prefix_digest"] == second["integrity"]["event_prefix_digest"]


def test_event_prefix_digest_changes_when_prefix_event_payload_changes():
    original_prefix = _happy_path_events()[:5]
    changed_prefix = _happy_path_events_with_changed_prefix_payload()[:5]

    assert projector.RunProjector().project(original_prefix) == projector.RunProjector().project(changed_prefix)

    original = projector.RunProjector().create_checkpoint("run_001", original_prefix)
    changed = projector.RunProjector().create_checkpoint("run_001", changed_prefix)

    assert original["integrity"]["event_prefix_digest"] != changed["integrity"]["event_prefix_digest"]


def test_event_prefix_digest_mismatch_falls_back_before_using_checkpoint_state(tmp_path, monkeypatch):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    events_store = event_store.FileEventStore(tmp_path)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events()[:5])
    checkpoints.save_checkpoint("run_001", checkpoint)
    _write_events(events_store, _happy_path_events_with_changed_prefix_payload())

    def fail_if_checkpoint_state_is_used(*args, **kwargs):
        raise AssertionError("event prefix digest mismatch checkpoint must not be used")

    project = projector.RunProjector()
    monkeypatch.setattr(project, "_run_state_from_checkpoint", fail_if_checkpoint_state_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_event_prefix_digest_mismatch_cannot_hide_lifecycle_invalid_event_log(tmp_path):
    invalid_events = [
        _run_created(),
        _agent_created(),
        _proposed(action_type="call_tool_payload_changed"),
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
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, invalid_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events()[:5])
    checkpoints.save_checkpoint("run_001", checkpoint)

    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_event_prefix_digest_match_still_validates_checkpoint_state_schema(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:5])
    checkpoint["state"] = {"run_id": "run_001"}
    _refresh_checkpoint_hash(checkpoint)
    checkpoints.save_checkpoint("run_001", checkpoint)

    with pytest.raises(ValueError, match="checkpoint state missing required field"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_legacy_checkpoint_without_event_prefix_digest_still_supported(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:5])
    checkpoints.save_checkpoint("run_001", _legacy_checkpoint_without_event_prefix_digest(checkpoint))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_suffix_events_are_replayed_after_digest_matched_checkpoint(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:5])
    checkpoints.save_checkpoint("run_001", checkpoint)

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)
    assert assisted.status == "completed"
    assert assisted.artifacts[0]["summary"] == "hello artifact"
