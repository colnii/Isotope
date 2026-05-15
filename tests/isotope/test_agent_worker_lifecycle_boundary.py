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
    "artifact_id": "artifact_worker_result_001",
}


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-02T00:00:{event_id[-2:]}Z",
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


def _delegation_proposed():
    return _event(
        "evt_003",
        "delegation.proposed",
        {
            "delegation_id": "deleg_001",
            "run_id": "run_001",
            "parent_agent_id": "agent_supervisor",
            "requested_worker_role": "worker",
            "requested_capabilities": {
                "tools": ["write_artifact_tool"],
                "workspace": {"mode": "shared_ro"},
                "budget": {"seconds": 30},
            },
        },
    )


def _delegation_decided(outcome: str = "approved"):
    return _event(
        "evt_004",
        "delegation.decided",
        {
            "delegation_id": "deleg_001",
            "decision_id": "dec_deleg_001",
            "outcome": outcome,
            "grants": {
                "tools": ["write_artifact_tool"] if outcome != "denied" else [],
                "workspace": {"mode": "shared_ro" if outcome != "denied" else "none"},
                "budget": {"seconds": 30 if outcome != "denied" else 0},
            },
        },
    )


def _worker_created(event_id: str = "evt_005"):
    return _event(
        event_id,
        "worker.created",
        {
            "worker_id": "worker_001",
            "agent_id": "agent_worker_001",
            "run_id": "run_001",
            "parent_agent_id": "agent_supervisor",
            "delegation_id": "deleg_001",
            "decision_id": "dec_deleg_001",
            "role": "worker",
            "status": "created",
            "workspace": {"mode": "shared_ro"},
        },
    )


def _worker_started(event_id: str = "evt_006"):
    return _event(
        event_id,
        "worker.started",
        {
            "worker_id": "worker_001",
            "delegation_id": "deleg_001",
            "status": "running",
        },
    )


def _worker_completed(event_id: str = "evt_007"):
    return _event(
        event_id,
        "worker.completed",
        {
            "worker_id": "worker_001",
            "delegation_id": "deleg_001",
            "status": "completed",
        },
    )


def _worker_failed(event_id: str = "evt_007"):
    return _event(
        event_id,
        "worker.failed",
        {
            "worker_id": "worker_001",
            "delegation_id": "deleg_001",
            "status": "failed",
            "error": "worker failed deterministically",
        },
    )


def _worker_cancelled(event_id: str = "evt_007"):
    return _event(
        event_id,
        "worker.cancelled",
        {
            "worker_id": "worker_001",
            "delegation_id": "deleg_001",
            "status": "cancelled",
            "reason": "user_cancelled",
        },
    )


def _worker_result_handoff(event_id: str = "evt_008"):
    return _event(
        event_id,
        "worker.result_handed_off",
        {
            "worker_id": "worker_001",
            "delegation_id": "deleg_001",
            "artifact_ref": ARTIFACT_REF,
            "summary": "worker produced a result artifact",
        },
    )


def _worker_events(*tail):
    return [
        _run_created(),
        _supervisor_created(),
        _delegation_proposed(),
        _delegation_decided(),
        _worker_created(),
        *tail,
    ]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def _checkpoint(run_id, basis_event_id, state):
    return {
        "run_id": run_id,
        "projector_version": projector.RunProjector.PROJECTOR_VERSION,
        "basis_event_id": basis_event_id,
        "state": asdict(state),
        "created_at": "2026-05-02T00:00:00Z",
    }


def test_supervisor_agent_instance_is_first_class_read_model():
    state = projector.RunProjector().project([_run_created(), _supervisor_created()])

    assert "agent_supervisor" in state.agents
    assert state.agents["agent_supervisor"]["role"] == "supervisor"
    assert state.agents["agent_supervisor"]["status"] == "created"


def test_worker_cannot_be_created_without_delegation_event():
    events_without_delegation = [
        _run_created(),
        _supervisor_created(),
        _worker_created("evt_003"),
    ]

    with pytest.raises(ValueError, match="worker.created requires approved delegation"):
        projector.RunProjector().project(events_without_delegation)


@pytest.mark.parametrize(
    ("terminal_event", "expected_status"),
    [
        (_worker_started, "running"),
        (_worker_completed, "completed"),
        (_worker_failed, "failed"),
        (_worker_cancelled, "cancelled"),
    ],
)
def test_worker_lifecycle_status_is_projected_from_events(terminal_event, expected_status):
    state = projector.RunProjector().project(_worker_events(terminal_event()))

    worker = state.workers["worker_001"]
    assert worker["status"] == expected_status
    assert worker["agent_id"] == "agent_worker_001"
    assert worker["delegation_id"] == "deleg_001"
    assert worker["parent_agent_id"] == "agent_supervisor"


def test_worker_lifecycle_replay_matches_direct_projection(tmp_path):
    canonical_events = _worker_events(_worker_started(), _worker_completed())
    store = event_store.FileEventStore(tmp_path)
    _write_events(store, canonical_events)

    direct = projector.RunProjector().project(canonical_events)
    replayed = projector.RunProjector().rebuild("run_001", store)

    assert replayed.workers == direct.workers
    assert replayed.agents == direct.agents


def test_worker_lifecycle_checkpoint_assisted_rebuild_matches_full_rebuild(tmp_path):
    canonical_events = _worker_events(_worker_started(), _worker_completed())
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events)
    basis_state = projector.RunProjector().project(canonical_events[:6])
    checkpoints.save_checkpoint("run_001", _checkpoint("run_001", "evt_006", basis_state))

    assisted = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)
    full = projector.RunProjector().rebuild("run_001", events_store)

    assert assisted.workers == full.workers
    assert assisted.agents == full.agents


def test_worker_result_handoff_uses_artifact_ref_without_direct_state_mutation():
    state = projector.RunProjector().project(
        _worker_events(_worker_started(), _worker_result_handoff(), _worker_completed("evt_009"))
    )

    worker = state.workers["worker_001"]
    assert worker["result_refs"] == [ARTIFACT_REF]
    assert "result" not in worker
    assert "content" not in worker
    assert state.status != "completed"


def test_malformed_worker_lifecycle_event_fails_fast():
    malformed = _event(
        "evt_005",
        "worker.created",
        {
            "agent_id": "agent_worker_001",
            "delegation_id": "deleg_001",
            "status": "created",
        },
    )

    with pytest.raises(ValueError, match="worker.created missing required field: worker_id"):
        projector.RunProjector().project(
            [_run_created(), _supervisor_created(), _delegation_proposed(), _delegation_decided(), malformed]
        )


def test_worker_slice_does_not_spawn_real_threads_or_processes(monkeypatch):
    spawned = []

    def record_spawn(*args, **kwargs):
        spawned.append((args, kwargs))
        raise AssertionError("worker boundary must not spawn real concurrency in this slice")

    monkeypatch.setattr("threading.Thread", record_spawn)
    monkeypatch.setattr("multiprocessing.Process", record_spawn)

    projector.RunProjector().project(_worker_events(_worker_started()))

    assert spawned == []
