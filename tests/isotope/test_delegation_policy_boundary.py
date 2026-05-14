import pytest

from isotope import events, models, policy, projector, workspace


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-02T00:01:{event_id[-2:]}Z",
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


def _delegation_proposed(requested_workspace_mode: str = "isolated_rw"):
    return _event(
        "evt_003",
        "delegation.proposed",
        {
            "delegation_id": "deleg_001",
            "run_id": "run_001",
            "parent_agent_id": "agent_supervisor",
            "requested_worker_role": "worker",
            "requested_capabilities": {
                "tools": ["write_artifact_tool", "unrequested_extra_tool"],
                "workspace": {"mode": requested_workspace_mode},
                "budget": {"seconds": 999},
            },
        },
    )


def _delegation_decided(
    outcome: str,
    *,
    grants: dict | None = None,
    event_id: str = "evt_004",
):
    if grants is None:
        grants = {
            "tools": ["write_artifact_tool"] if outcome != "denied" else [],
            "workspace": {"mode": "shared_ro" if outcome != "denied" else "none"},
            "budget": {"seconds": 30 if outcome != "denied" else 0},
        }
    return _event(
        event_id,
        "delegation.decided",
        {
            "delegation_id": "deleg_001",
            "decision_id": "dec_deleg_001",
            "outcome": outcome,
            "grants": grants,
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


def _worker_action_proposed(event_id: str = "evt_006"):
    return _event(
        event_id,
        "action.proposed",
        {
            "proposal_id": "prop_worker_001",
            "agent_id": "agent_worker_001",
            "action_type": "call_tool",
            "registry_id": "default",
            "registry_version": "v0.2",
        },
    )


def _worker_action_decided(event_id: str = "evt_007"):
    return _event(
        event_id,
        "action.decided",
        {
            "proposal_id": "prop_worker_001",
            "decision_id": "dec_worker_001",
            "outcome": "approved",
            "policy_profile_id": "default",
            "policy_version": "v0.2",
            "grants": {
                "tools": ["write_artifact_tool"],
                "workspace": {"mode": "shared_ro"},
                "budget": {"seconds": 30},
            },
        },
    )


def _worker_action_decided_without_grants(event_id: str = "evt_007"):
    return _event(
        event_id,
        "action.decided",
        {
            "proposal_id": "prop_worker_001",
            "decision_id": "dec_worker_001",
            "outcome": "approved",
            "policy_profile_id": "default",
            "policy_version": "v0.2",
        },
    )


def _worker_action_started(event_id: str = "evt_008"):
    return _event(
        event_id,
        "action.started",
        {
            "execution_id": "exec_worker_001",
            "proposal_id": "prop_worker_001",
            "decision_id": "dec_worker_001",
        },
    )


def _approved_delegation_events(*tail):
    return [
        _run_created(),
        _supervisor_created(),
        _delegation_proposed(),
        _delegation_decided("modified"),
        _worker_created(),
        *tail,
    ]


def test_delegation_requires_canonical_proposal_before_worker_creation():
    with pytest.raises(ValueError, match="delegation.proposed"):
        projector.RunProjector().project([_run_created(), _supervisor_created(), _worker_created("evt_003")])


def test_delegation_proposal_must_be_followed_by_policy_decision_before_worker_creation():
    with pytest.raises(ValueError, match="delegation.decided"):
        projector.RunProjector().project(
            [_run_created(), _supervisor_created(), _delegation_proposed(), _worker_created("evt_004")]
        )


def test_denied_delegation_does_not_create_worker():
    with pytest.raises(ValueError, match="denied delegation"):
        projector.RunProjector().project(
            [
                _run_created(),
                _supervisor_created(),
                _delegation_proposed(),
                _delegation_decided("denied"),
                _worker_created(),
            ]
        )


def test_approved_or_modified_delegation_creates_worker_read_model():
    state = projector.RunProjector().project(_approved_delegation_events())

    assert state.workers["worker_001"]["status"] == "created"
    assert state.workers["worker_001"]["delegation_id"] == "deleg_001"


def test_delegation_boundary_uses_policy_decision_grants_not_requested_capabilities():
    state = projector.RunProjector().project(_approved_delegation_events())

    worker = state.workers["worker_001"]
    assert worker["requested_capabilities"]["workspace"]["mode"] == "isolated_rw"
    assert worker["grants"]["workspace"]["mode"] == "shared_ro"
    assert worker["workspace"]["mode"] == "shared_ro"


def test_worker_workspace_binding_comes_from_grants():
    state = projector.RunProjector().project(_approved_delegation_events())
    binding = workspace.WorkspaceManager().get_binding(state.workers["worker_001"]["grants"])

    assert binding.mode == "shared_ro"
    assert binding.workspace_id == "workspace_shared_ro"


def test_worker_cannot_execute_action_without_policy_grants():
    with pytest.raises(ValueError, match="worker action requires policy grants"):
        projector.RunProjector().project(
            _approved_delegation_events(
                _worker_action_proposed(),
                _worker_action_decided_without_grants(),
                _worker_action_started(),
            )
        )


def test_worker_created_action_still_uses_action_chain():
    state = projector.RunProjector().project(
        _approved_delegation_events(
            _worker_action_proposed(),
            _worker_action_decided(),
            _worker_action_started(),
        )
    )

    assert state.actions["exec_worker_001"]["agent_id"] == "agent_worker_001"
    assert state.actions["exec_worker_001"]["decision_id"] == "dec_worker_001"


def test_delegation_events_replay_to_same_read_model(tmp_path):
    from isotope import event_store

    canonical_events = _approved_delegation_events()
    store = event_store.FileEventStore(tmp_path)
    for event in canonical_events:
        store.append(event)

    direct = projector.RunProjector().project(canonical_events)
    replayed = projector.RunProjector().rebuild("run_001", store)

    assert replayed.workers == direct.workers


def test_no_model_driven_planning_loop_or_real_concurrency_is_exposed_in_first_slice():
    assert not hasattr(models, "ModelPlanningLoop")
    assert not hasattr(models, "WorkerProcess")
    assert not hasattr(policy.PolicyEngine(), "spawn_worker")
