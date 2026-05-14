import copy
import json

import pytest

from isotope import checkpoint_store, event_store, events, projector


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


def _checkpoint_without_event_envelope_version_metadata(checkpoint):
    checkpoint = copy.deepcopy(checkpoint)
    checkpoint["integrity"].pop("event_digest_event_envelope_version", None)
    return checkpoint


def test_canonical_event_defaults_to_current_event_envelope_version():
    event = _run_created()

    assert event.event_envelope_version == events.EVENT_ENVELOPE_VERSION
    assert event.event_envelope_version == "canonical_event_slice@v0"


def test_canonical_event_to_dict_includes_event_envelope_version():
    serialized = _run_created().to_dict()

    assert serialized["event_envelope_version"] == events.EVENT_ENVELOPE_VERSION


def test_canonical_event_from_dict_accepts_legacy_event_without_version():
    serialized = _run_created().to_dict()
    serialized.pop("event_envelope_version", None)

    event = events.CanonicalEvent.from_dict(serialized)

    assert event.event_envelope_version == events.EVENT_ENVELOPE_VERSION


def test_canonical_event_from_dict_rejects_empty_event_envelope_version():
    serialized = _run_created().to_dict()
    serialized["event_envelope_version"] = ""

    with pytest.raises(ValueError, match="event_envelope_version"):
        events.CanonicalEvent.from_dict(serialized)


def test_canonical_event_from_dict_rejects_non_string_event_envelope_version():
    serialized = _run_created().to_dict()
    serialized["event_envelope_version"] = 123

    with pytest.raises(ValueError, match="event_envelope_version"):
        events.CanonicalEvent.from_dict(serialized)


def test_canonical_event_from_dict_rejects_unknown_event_envelope_version():
    serialized = _run_created().to_dict()
    serialized["event_envelope_version"] = "canonical_event@future"

    with pytest.raises(ValueError, match="unknown event_envelope_version"):
        events.CanonicalEvent.from_dict(serialized)


def test_file_event_store_replays_event_envelope_version_from_jsonl(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    store.append(_run_created())

    replayed = store.list_events("run_001")

    assert replayed[0].event_envelope_version == events.EVENT_ENVELOPE_VERSION
    raw = json.loads(store.event_path("run_001").read_text(encoding="utf-8").strip())
    assert raw["event_envelope_version"] == events.EVENT_ENVELOPE_VERSION


def test_checkpoint_integrity_records_event_digest_event_envelope_version():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events())

    assert (
        checkpoint["integrity"]["event_digest_event_envelope_version"]
        == events.EVENT_ENVELOPE_VERSION
    )


def test_event_prefix_digest_changes_when_event_envelope_version_changes():
    canonical_events = _happy_path_events()[:5]
    changed_events = copy.deepcopy(canonical_events)
    object.__setattr__(changed_events[2], "event_envelope_version", "canonical_event@experimental")

    original = projector.RunProjector().create_checkpoint("run_001", canonical_events)
    changed = projector.RunProjector().create_checkpoint("run_001", changed_events)

    assert original["integrity"]["event_prefix_digest"] != changed["integrity"]["event_prefix_digest"]


def test_checkpoint_event_envelope_version_mismatch_falls_back_before_using_state(tmp_path, monkeypatch):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    events_store = event_store.FileEventStore(tmp_path)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _happy_path_events()[:5])
    checkpoint["integrity"]["event_digest_event_envelope_version"] = "canonical_event@future"
    checkpoints.save_checkpoint("run_001", checkpoint)
    _write_events(events_store, _happy_path_events())

    def fail_if_checkpoint_state_is_used(*args, **kwargs):
        raise AssertionError("event envelope version mismatch checkpoint must not be used")

    project = projector.RunProjector()
    monkeypatch.setattr(project, "_run_state_from_checkpoint", fail_if_checkpoint_state_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_legacy_checkpoint_without_event_envelope_version_metadata_still_supported(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:5])
    checkpoints.save_checkpoint("run_001", _checkpoint_without_event_envelope_version_metadata(checkpoint))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)
