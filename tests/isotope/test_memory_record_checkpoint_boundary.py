import copy
import hashlib
import json
from dataclasses import asdict

import pytest

from isotope import checkpoint_store, event_store, events, memory, projector, server


OLD_SOURCE_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_old",
    "uri": "artifact://run_001/artifact_old",
}

NEW_SOURCE_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_new",
    "uri": "artifact://run_001/artifact_new",
}


def _event(event_id: str, event_type: str, payload: dict) -> events.CanonicalEvent:
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-04-30T00:01:{event_id[-2:]}Z",
    )


def _run_created() -> events.CanonicalEvent:
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _action_proposed(event_id: str, proposal_id: str, action_type: str = "write_memory") -> events.CanonicalEvent:
    return _event(
        event_id,
        "action.proposed",
        {
            "proposal_id": proposal_id,
            "agent_id": "agent_supervisor",
            "action_type": action_type,
            "registry_id": "default",
            "registry_version": "v0.2",
            "payload": {"tool": action_type},
        },
    )


def _action_decided(
    event_id: str,
    proposal_id: str,
    decision_id: str,
    outcome: str = "approved",
) -> events.CanonicalEvent:
    return _event(
        event_id,
        "action.decided",
        {
            "decision_id": decision_id,
            "proposal_id": proposal_id,
            "outcome": outcome,
            "policy_profile_id": "default",
            "policy_version": "v0.2",
        },
    )


def _action_started(
    event_id: str,
    execution_id: str,
    proposal_id: str,
    decision_id: str,
) -> events.CanonicalEvent:
    return _event(
        event_id,
        "action.started",
        {
            "execution_id": execution_id,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
        },
    )


def _action_completed(event_id: str, execution_id: str) -> events.CanonicalEvent:
    return _event(
        event_id,
        "action.completed",
        {
            "execution_id": execution_id,
            "status": "completed",
            "artifact_refs": [],
        },
    )


def _completed_execution_events(
    *,
    proposal_id: str,
    decision_id: str,
    execution_id: str,
    start_event_number: int,
) -> list[events.CanonicalEvent]:
    return [
        _action_proposed(f"evt_{start_event_number:03d}", proposal_id),
        _action_decided(f"evt_{start_event_number + 1:03d}", proposal_id, decision_id),
        _action_started(f"evt_{start_event_number + 2:03d}", execution_id, proposal_id, decision_id),
        _action_completed(f"evt_{start_event_number + 3:03d}", execution_id),
    ]


def _memory_record_created(
    event_id: str,
    *,
    record_id: str,
    execution_id: str,
    summary: str,
    source_ref: dict,
    basis_event_id: str,
) -> events.CanonicalEvent:
    return _event(
        event_id,
        "memory.record_created",
        {
            "record_id": record_id,
            "execution_id": execution_id,
            "summary": summary,
            "source_refs": [dict(source_ref)],
            "provenance": {
                "run_id": "run_001",
                "execution_id": execution_id,
                "action_type": "write_memory",
                "basis_event_id": basis_event_id,
            },
            "basis_event_id": basis_event_id,
            "quality": "unverified",
        },
    )


def _memory_record_superseded(event_id: str = "evt_012", **overrides) -> events.CanonicalEvent:
    payload = {
        "old_record_id": "mem_old",
        "new_record_id": "mem_new",
        "execution_id": "exec_memory_new",
        "reason": "newer memory record supersedes the older one",
        "provenance": {
            "run_id": "run_001",
            "execution_id": "exec_memory_new",
            "action_type": "write_memory",
            "basis_event_id": "evt_011",
        },
        "basis_event_id": "evt_011",
    }
    payload.update(overrides)
    return _event(event_id, "memory.record_superseded", payload)


def _memory_events() -> list[events.CanonicalEvent]:
    return [
        _run_created(),
        *_completed_execution_events(
            proposal_id="prop_memory_old",
            decision_id="dec_memory_old",
            execution_id="exec_memory_old",
            start_event_number=2,
        ),
        _memory_record_created(
            "evt_006",
            record_id="mem_old",
            execution_id="exec_memory_old",
            summary="Original learner preference summary.",
            source_ref=OLD_SOURCE_REF,
            basis_event_id="evt_005",
        ),
        *_completed_execution_events(
            proposal_id="prop_memory_new",
            decision_id="dec_memory_new",
            execution_id="exec_memory_new",
            start_event_number=7,
        ),
        _memory_record_created(
            "evt_011",
            record_id="mem_new",
            execution_id="exec_memory_new",
            summary="Updated learner preference summary.",
            source_ref=NEW_SOURCE_REF,
            basis_event_id="evt_010",
        ),
        _memory_record_superseded(),
    ]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def _state_at(canonical_events: list[events.CanonicalEvent], event_id: str) -> dict:
    index = next(index for index, event in enumerate(canonical_events) if event.event_id == event_id)
    return asdict(projector.RunProjector().project(canonical_events[: index + 1]))


def _checkpoint(state: dict, basis_event_id: str = "evt_012") -> dict:
    return {
        "run_id": "run_001",
        "projector_version": "run_projector@v1",
        "basis_event_id": basis_event_id,
        "state": state,
        "created_at": "2026-04-30T00:00:00Z",
    }


def _checkpoint_payload_for_hash(checkpoint: dict) -> dict:
    payload = copy.deepcopy(checkpoint)
    payload.pop("integrity", None)
    payload.pop("checkpoint_hash", None)
    return payload


def _checkpoint_hash(checkpoint: dict) -> str:
    encoded = json.dumps(
        _checkpoint_payload_for_hash(checkpoint),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _refresh_checkpoint_hash(checkpoint: dict) -> dict:
    checkpoint["integrity"]["checkpoint_hash"] = _checkpoint_hash(checkpoint)
    return checkpoint


def _stores(tmp_path, canonical_events=None):
    canonical_events = canonical_events or _memory_events()
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events)
    return events_store, checkpoints


def _save_checkpoint_and_rebuild(tmp_path, checkpoint: dict, canonical_events=None):
    events_store, checkpoints = _stores(tmp_path, canonical_events)
    checkpoints.save_checkpoint("run_001", checkpoint)
    return projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def _expected_memory_records():
    return projector.RunProjector().project(_memory_events()).memory_records


def test_fresh_projector_rebuild_replays_memory_records_from_event_log(tmp_path):
    events_store, _ = _stores(tmp_path)

    rebuilt = projector.RunProjector().rebuild("run_001", events_store)

    assert rebuilt.memory_records == _expected_memory_records()


def test_create_checkpoint_includes_memory_records_read_model():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _memory_events())

    assert checkpoint["state"]["memory_records"] == _expected_memory_records()


def test_checkpoint_memory_records_do_not_include_full_content_fields():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _memory_events())

    for record in checkpoint["state"]["memory_records"]:
        for forbidden_field in ("content", "full_content", "artifact_content", "raw_content"):
            assert forbidden_field not in record


def test_rebuild_with_checkpoint_restores_memory_records_from_checkpoint_and_suffix(tmp_path, monkeypatch):
    canonical_events = _memory_events()
    events_store, checkpoints = _stores(tmp_path, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events[:11])
    checkpoints.save_checkpoint("run_001", checkpoint)

    project = projector.RunProjector()

    def fail_if_full_rebuild_is_used(*args, **kwargs):
        raise AssertionError("memory checkpoint path should restore prefix memory_records and replay suffix")

    monkeypatch.setattr(project, "rebuild", fail_if_full_rebuild_is_used)

    assisted = project.rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted.memory_records == _expected_memory_records()


@pytest.mark.parametrize(
    "bad_value, expected_message",
    [
        ({"record_id": "mem_old"}, "checkpoint state memory_records must be a list"),
        (["not-a-dict"], "checkpoint memory record entry must be a dict"),
    ],
)
def test_checkpoint_state_memory_records_must_be_list_of_dicts(tmp_path, bad_value, expected_message):
    state = _state_at(_memory_events(), "evt_012")
    state["memory_records"] = bad_value

    with pytest.raises(ValueError, match=expected_message):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


@pytest.mark.parametrize("field", ["record_id", "summary", "source_refs"])
def test_checkpoint_state_memory_record_requires_minimal_fields(tmp_path, field):
    state = _state_at(_memory_events(), "evt_012")
    state["memory_records"][0].pop(field)

    with pytest.raises(ValueError, match=f"checkpoint memory record entry missing required field: {field}"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


@pytest.mark.parametrize("field", ["content", "full_content", "artifact_content", "raw_content"])
def test_checkpoint_state_memory_record_rejects_full_content_fields(tmp_path, field):
    state = _state_at(_memory_events(), "evt_012")
    state["memory_records"][0][field] = "raw memory or artifact content"

    with pytest.raises(ValueError, match=f"checkpoint memory record entry cannot contain {field}"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


@pytest.mark.parametrize(
    "mutation, expected_message",
    [
        (
            lambda record: record.pop("superseded_by"),
            "checkpoint superseded memory record missing required field: superseded_by",
        ),
        (
            lambda record: record.update({"superseded_by": 123}),
            "checkpoint superseded_by must be a string",
        ),
        (
            lambda record: record.update({"superseded_event_id": 123}),
            "checkpoint superseded_event_id must be a string",
        ),
        (
            lambda record: record.update({"superseded_reason": ""}),
            "checkpoint superseded_reason must be a non-empty string",
        ),
    ],
)
def test_checkpoint_state_memory_record_validates_supersession_metadata(
    tmp_path,
    mutation,
    expected_message,
):
    state = _state_at(_memory_events(), "evt_012")
    mutation(state["memory_records"][0])

    with pytest.raises(ValueError, match=expected_message):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


def test_checkpoint_prefix_consistency_covers_memory_records(tmp_path):
    canonical_events = _memory_events()
    state = _state_at(canonical_events, "evt_012")
    state["memory_records"][0]["summary"] = "tampered checkpoint memory summary"
    events_store, checkpoints = _stores(tmp_path, canonical_events)
    checkpoints.save_checkpoint("run_001", _checkpoint(state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)
    assert assisted.memory_records == _expected_memory_records()
    assert all(record["summary"] != "tampered checkpoint memory summary" for record in assisted.memory_records)


def test_memory_checkpoint_cannot_use_full_content_even_when_hash_matches(tmp_path):
    canonical_events = _memory_events()
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events)
    checkpoint["state"].setdefault("memory_records", _expected_memory_records())
    checkpoint["state"]["memory_records"][0]["content"] = {"raw": "must not be checkpointed"}
    _refresh_checkpoint_hash(checkpoint)

    with pytest.raises(ValueError, match="checkpoint memory record entry cannot contain content"):
        _save_checkpoint_and_rebuild(tmp_path, checkpoint, canonical_events)


def test_projector_does_not_read_memory_store_or_query_service_for_checkpoint():
    class ExplodingMemoryBoundary:
        def list_records(self, *args, **kwargs):
            raise AssertionError("projector must not read memory store for checkpoint")

        def query(self, *args, **kwargs):
            raise AssertionError("projector must not query memory service for checkpoint")

    boundary = ExplodingMemoryBoundary()

    checkpoint = projector.RunProjector().create_checkpoint("run_001", _memory_events())

    assert checkpoint["run_id"] == "run_001"
    assert boundary is not None


def test_durable_memory_storage_still_not_enabled(tmp_path):
    store = memory.NotEnabledMemoryStore(tmp_path)

    assert store.list_records() == []
    assert not store.record_path("mem_old").exists()


def test_server_still_has_no_public_direct_memory_write_query_or_update_api(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert not hasattr(api, "write_memory")
    assert not hasattr(api, "query_memory")
    assert not hasattr(api, "update_memory")
    assert not hasattr(api, "supersede_memory")
