import copy
import hashlib
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


def _lifecycle_invalid_events():
    return [
        _run_created(),
        _agent_created(),
        _proposed(),
        _decided(),
        _event(
            "evt_005",
            "action.completed",
            {
                "execution_id": "exec_001",
                "status": "completed",
                "artifact_refs": [ARTIFACT_REF],
            },
        ),
    ]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


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


def _checkpoint_for_prefix(projector_version="run_projector@v1"):
    return projector.RunProjector().create_checkpoint(
        "run_001",
        _happy_path_events()[:5],
        projector_version=projector_version,
    )


def _poison_state(checkpoint):
    checkpoint["state"] = {
        "run_id": "run_001",
        "status": "completed",
        "current_agent": "poisoned_agent",
        "actions": {"poisoned": {"status": "completed"}},
        "artifacts": [],
        "last_event_id": checkpoint["basis_event_id"],
    }
    return checkpoint


def _save_checkpoint_with_events(tmp_path, checkpoint, canonical_events=None):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events or _happy_path_events())
    checkpoints.save_checkpoint("run_001", checkpoint)
    return events_store, checkpoints


def _fail_if_checkpoint_state_is_used(*args, **kwargs):
    raise AssertionError("incompatible checkpoint version must not read checkpoint state")


@pytest.mark.parametrize("malformed_version", [123, None])
def test_non_string_projector_version_falls_back_without_using_checkpoint_state(
    tmp_path,
    monkeypatch,
    malformed_version,
):
    checkpoint = _poison_state(_checkpoint_for_prefix())
    checkpoint["projector_version"] = malformed_version
    _refresh_checkpoint_hash(checkpoint)
    events_store, checkpoints = _save_checkpoint_with_events(tmp_path, checkpoint)
    project = projector.RunProjector()
    monkeypatch.setattr(project, "_run_state_from_checkpoint", _fail_if_checkpoint_state_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_empty_projector_version_falls_back_without_using_checkpoint_state(tmp_path, monkeypatch):
    checkpoint = _poison_state(_checkpoint_for_prefix())
    checkpoint["projector_version"] = ""
    _refresh_checkpoint_hash(checkpoint)
    events_store, checkpoints = _save_checkpoint_with_events(tmp_path, checkpoint)
    project = projector.RunProjector()
    monkeypatch.setattr(project, "_run_state_from_checkpoint", _fail_if_checkpoint_state_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_malformed_projector_version_override_still_falls_back_without_using_checkpoint_state(
    tmp_path,
    monkeypatch,
):
    checkpoint = _poison_state(_checkpoint_for_prefix())
    checkpoint["projector_version"] = 123
    _refresh_checkpoint_hash(checkpoint)
    events_store, checkpoints = _save_checkpoint_with_events(tmp_path, checkpoint)
    project = projector.RunProjector()
    monkeypatch.setattr(project, "_run_state_from_checkpoint", _fail_if_checkpoint_state_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints, projector_version=123)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_incompatible_projector_version_fallback_still_validates_event_log(tmp_path):
    checkpoint = _checkpoint_for_prefix(projector_version="run_projector@old")
    events_store, checkpoints = _save_checkpoint_with_events(tmp_path, checkpoint, _lifecycle_invalid_events())

    with pytest.raises(ValueError, match="action.completed before action.started"):
        projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def test_projector_version_override_argument_controls_compatibility(tmp_path):
    checkpoint = _checkpoint_for_prefix(projector_version="run_projector@future")
    events_store, checkpoints = _save_checkpoint_with_events(tmp_path, checkpoint)

    assisted = projector.RunProjector().rebuild_with_checkpoint(
        "run_001",
        events_store,
        checkpoints,
        projector_version="run_projector@future",
    )

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_future_schema_version_fields_do_not_override_projector_version(tmp_path, monkeypatch):
    checkpoint = _poison_state(_checkpoint_for_prefix(projector_version="run_projector@old"))
    checkpoint["checkpoint_schema_version"] = "checkpoint@future"
    checkpoint["event_envelope_version"] = "event_envelope@future"
    checkpoint["state_schema_version"] = "run_state@future"
    _refresh_checkpoint_hash(checkpoint)
    events_store, checkpoints = _save_checkpoint_with_events(tmp_path, checkpoint)
    project = projector.RunProjector()
    monkeypatch.setattr(project, "_run_state_from_checkpoint", _fail_if_checkpoint_state_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_future_schema_version_fields_do_not_break_compatible_legacy_path(tmp_path):
    checkpoint = _checkpoint_for_prefix()
    checkpoint["checkpoint_schema_version"] = "checkpoint@future"
    checkpoint["event_envelope_version"] = "event_envelope@future"
    checkpoint["state_schema_version"] = "run_state@future"
    _refresh_checkpoint_hash(checkpoint)
    events_store, checkpoints = _save_checkpoint_with_events(tmp_path, checkpoint)

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)
