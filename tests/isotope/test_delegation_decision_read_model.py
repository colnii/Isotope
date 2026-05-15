from __future__ import annotations

from dataclasses import asdict

import isotope.platform.state.checkpoint_store as checkpoint_store
import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.platform.state.projector as projector


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-10T00:00:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _supervisor_created():
    return _event(
        "evt_002",
        "agent.created",
        {
            "agent_id": "agent_supervisor",
            "role": "supervisor",
            "status": "created",
        },
    )


def _delegation_proposed(event_id: str, delegation_id: str, requested_role: str = "worker"):
    return _event(
        event_id,
        "delegation.proposed",
        {
            "delegation_id": delegation_id,
            "run_id": "run_001",
            "parent_agent_id": "agent_supervisor",
            "requested_worker_role": requested_role,
            "requested_capabilities": {
                "tools": ["write_artifact_tool"],
                "workspace": {"mode": "shared_ro"},
                "budget": {"seconds": 30},
            },
        },
    )


def _delegation_decided(
    event_id: str,
    delegation_id: str,
    decision_id: str,
    outcome: str,
    reason_codes: list[str],
):
    return _event(
        event_id,
        "delegation.decided",
        {
            "delegation_id": delegation_id,
            "decision_id": decision_id,
            "outcome": outcome,
            "grants": {
                "tools": ["write_artifact_tool"],
                "workspace": {"mode": "shared_ro"},
                "budget": {"seconds": 15 if outcome == "modified" else 30},
            },
            "reason_codes": reason_codes,
            "policy_basis": {
                "policy_profile_id": "policy_profile_default",
                "policy_version": "v1",
            },
        },
    )


def _worker_created(event_id: str, delegation_id: str, decision_id: str, worker_id: str):
    return _event(
        event_id,
        "worker.created",
        {
            "worker_id": worker_id,
            "agent_id": f"agent_{worker_id}",
            "run_id": "run_001",
            "parent_agent_id": "agent_supervisor",
            "delegation_id": delegation_id,
            "decision_id": decision_id,
            "role": "worker",
            "status": "created",
            "workspace": {"mode": "shared_ro"},
        },
    )


def _approved_and_modified_delegation_events():
    return [
        _run_created(),
        _supervisor_created(),
        _delegation_proposed("evt_003", "deleg_approved"),
        _delegation_decided("evt_004", "deleg_approved", "dec_approved", "approved", []),
        _worker_created("evt_005", "deleg_approved", "dec_approved", "worker_approved"),
        _delegation_proposed("evt_006", "deleg_modified"),
        _delegation_decided(
            "evt_007",
            "deleg_modified",
            "dec_modified",
            "modified",
            ["budget_reduced"],
        ),
        _worker_created("evt_008", "deleg_modified", "dec_modified", "worker_modified"),
    ]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def _checkpoint(run_id: str, basis_event_id: str, state: projector.RunState):
    return {
        "run_id": run_id,
        "projector_version": projector.RunProjector.PROJECTOR_VERSION,
        "basis_event_id": basis_event_id,
        "state": asdict(state),
        "created_at": "2026-05-10T00:00:00Z",
    }


def test_delegation_decision_read_model_projects_approved_and_modified_decisions():
    state = projector.RunProjector().project(_approved_and_modified_delegation_events())

    approved = state.delegations["deleg_approved"]
    assert approved["delegation_id"] == "deleg_approved"
    assert approved["decision_id"] == "dec_approved"
    assert approved["outcome"] == "approved"
    assert approved["reason_codes"] == []
    assert approved["grants"]["workspace"] == {"mode": "shared_ro"}
    assert approved["policy_basis"]["policy_profile_id"] == "policy_profile_default"
    assert approved["worker_id"] == "worker_approved"

    modified = state.delegations["deleg_modified"]
    assert modified["decision_id"] == "dec_modified"
    assert modified["outcome"] == "modified"
    assert modified["reason_codes"] == ["budget_reduced"]
    assert modified["grants"]["budget"] == {"seconds": 15}
    assert modified["policy_basis"]["policy_version"] == "v1"
    assert modified["worker_id"] == "worker_modified"


def test_delegation_decision_read_model_replay_matches_direct_projection(tmp_path):
    canonical_events = _approved_and_modified_delegation_events()
    store = event_store.FileEventStore(tmp_path)
    _write_events(store, canonical_events)

    direct = projector.RunProjector().project(canonical_events)
    replayed = projector.RunProjector().rebuild("run_001", store)

    assert replayed.delegations == direct.delegations


def test_delegation_decision_read_model_checkpoint_rebuild_matches_full_rebuild(tmp_path):
    canonical_events = _approved_and_modified_delegation_events()
    events_store = event_store.FileEventStore(tmp_path / "events")
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    _write_events(events_store, canonical_events)
    basis_state = projector.RunProjector().project(canonical_events[:5])
    checkpoints.save_checkpoint("run_001", _checkpoint("run_001", "evt_005", basis_state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)
    full = projector.RunProjector().rebuild("run_001", events_store)

    assert assisted.delegations == full.delegations
