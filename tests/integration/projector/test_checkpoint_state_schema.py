from dataclasses import asdict

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


def _state_at(canonical_events, event_id):
    index = next(index for index, event in enumerate(canonical_events) if event.event_id == event_id)
    return asdict(projector.RunProjector().project(canonical_events[: index + 1]))


def _checkpoint(state, basis_event_id="evt_005", projector_version="run_projector@v1"):
    return {
        "run_id": "run_001",
        "projector_version": projector_version,
        "basis_event_id": basis_event_id,
        "state": state,
        "created_at": "2026-04-28T00:00:00Z",
    }


def _save_checkpoint_and_rebuild(tmp_path, checkpoint):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, _happy_path_events())
    checkpoints.save_checkpoint("run_001", checkpoint)

    return projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)


def _valid_state(basis_event_id="evt_005"):
    return _state_at(_happy_path_events(), basis_event_id)


def test_checkpoint_state_must_be_dict(tmp_path):
    with pytest.raises(ValueError, match="checkpoint state must be a dict"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint("not-a-dict"))


@pytest.mark.parametrize("field", ["run_id", "status", "current_agent", "actions", "artifacts", "last_event_id"])
def test_checkpoint_state_requires_minimal_fields(tmp_path, field):
    state = _valid_state()
    state.pop(field)

    with pytest.raises(ValueError, match=f"checkpoint state missing required field: {field}"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


def test_checkpoint_state_run_id_must_match_rebuild_run_id(tmp_path):
    state = _valid_state()
    state["run_id"] = "run_002"

    with pytest.raises(ValueError, match="checkpoint state run_id must match rebuild run_id"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


def test_checkpoint_state_last_event_id_must_match_basis_event_id(tmp_path):
    state = _valid_state()
    state["last_event_id"] = "evt_004"

    with pytest.raises(ValueError, match="checkpoint state last_event_id must match basis_event_id"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


def test_checkpoint_state_status_must_be_known(tmp_path):
    state = _valid_state()
    state["status"] = "corrupted"

    with pytest.raises(ValueError, match="checkpoint state status must be known"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


def test_checkpoint_state_actions_must_be_dict(tmp_path):
    state = _valid_state()
    state["actions"] = ["exec_001"]

    with pytest.raises(ValueError, match="checkpoint state actions must be a dict"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


def test_checkpoint_state_artifacts_must_be_list(tmp_path):
    state = _valid_state()
    state["artifacts"] = {"artifact_001": ARTIFACT_REF}

    with pytest.raises(ValueError, match="checkpoint state artifacts must be a list"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state))


def test_checkpoint_state_artifact_entry_rejects_content(tmp_path):
    state = _valid_state("evt_006")
    state["artifacts"][0]["content"] = "raw content"

    with pytest.raises(ValueError, match="checkpoint artifact entry cannot contain content"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state, basis_event_id="evt_006"))


@pytest.mark.parametrize("field", ["ref", "artifact_type", "summary", "provenance"])
def test_checkpoint_state_artifact_entry_requires_minimal_fields(tmp_path, field):
    state = _valid_state("evt_006")
    state["artifacts"][0].pop(field)

    with pytest.raises(ValueError, match=f"checkpoint artifact entry missing required field: {field}"):
        _save_checkpoint_and_rebuild(tmp_path, _checkpoint(state, basis_event_id="evt_006"))


def test_incompatible_projector_version_falls_back_without_validating_malformed_state(tmp_path):
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    canonical_events = _happy_path_events()
    _write_events(events_store, canonical_events)
    checkpoints.save_checkpoint(
        "run_001",
        _checkpoint("not-a-dict", projector_version="old_projector"),
    )

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert assisted == projector.RunProjector().rebuild("run_001", events_store)


def test_valid_checkpoint_state_still_completes_assisted_rebuild(tmp_path):
    assisted = _save_checkpoint_and_rebuild(tmp_path, _checkpoint(_valid_state()))
    full = projector.RunProjector().project(_happy_path_events())

    assert assisted == full
