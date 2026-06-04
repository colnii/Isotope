import pytest

import isotope.platform.state.checkpoint_store as checkpoint_store
import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.platform.state.projector as projector
import isotope.workspace as workspace


RUN_ID = "run_001"
WORKSPACE_ID = "workspace_shared_ro"
ISOLATED_WORKSPACE_ID = "workspace_native_coding_slice_3"


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=RUN_ID,
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-03T00:04:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": RUN_ID})


def _agent_created():
    return _event(
        "evt_002",
        "agent.created",
        {
            "agent_id": "agent_supervisor",
            "run_id": RUN_ID,
            "role": "supervisor",
            "status": "created",
        },
    )


def _lease_created(**overrides):
    payload = {
        "workspace_id": WORKSPACE_ID,
        "run_id": RUN_ID,
        "mode": "shared_ro",
        "lease_status": "created",
        "bound_to": {"type": "agent", "agent_id": "agent_supervisor"},
        "granted_by": {"decision_id": "dec_workspace_001"},
        "created_by": {
            "proposal_id": "prop_workspace_001",
            "execution_id": "exec_workspace_001",
        },
        "provenance": {
            "decision_id": "dec_workspace_001",
            "proposal_id": "prop_workspace_001",
            "execution_id": "exec_workspace_001",
            "grant_basis": {"workspace": {"mode": "shared_ro"}},
        },
    }
    payload.update(overrides)
    return _event("evt_003", "workspace.lease_created", payload)


def _workspace_bound(**overrides):
    payload = {
        "workspace_id": WORKSPACE_ID,
        "run_id": RUN_ID,
        "mode": "shared_ro",
        "bound_to": {"agent_id": "agent_supervisor"},
        "lease_status": "active",
        "granted_by": {"decision_id": "dec_workspace_001"},
        "created_by": {
            "proposal_id": "prop_workspace_001",
            "execution_id": "exec_workspace_001",
        },
        "provenance": {
            "decision_id": "dec_workspace_001",
            "proposal_id": "prop_workspace_001",
            "execution_id": "exec_workspace_001",
            "grant_basis": {"workspace": {"mode": "shared_ro"}},
        },
    }
    payload.update(overrides)
    return _event("evt_004", "workspace.bound", payload)


def _workspace_released(**overrides):
    payload = {
        "workspace_id": WORKSPACE_ID,
        "run_id": RUN_ID,
        "lease_status": "released",
        "released_by": {"type": "agent", "agent_id": "agent_supervisor"},
        "released_at": "2026-05-03T00:05:00Z",
        "reason": "run finished with deterministic workspace boundary",
        "basis_event_id": "evt_004",
    }
    payload.update(overrides)
    return _event("evt_005", "workspace.released", payload)


def _isolated_rw_lease_created(**overrides):
    payload = {
        "workspace_id": ISOLATED_WORKSPACE_ID,
        "run_id": RUN_ID,
        "mode": "isolated_rw",
        "lease_status": "created",
        "bound_to": {"type": "agent", "agent_id": "agent_supervisor"},
        "granted_by": {"decision_id": "dec_workspace_isolated_001"},
        "created_by": {
            "proposal_id": "prop_workspace_isolated_001",
            "execution_id": "exec_workspace_isolated_001",
        },
        "provenance": {
            "decision_id": "dec_workspace_isolated_001",
            "proposal_id": "prop_workspace_isolated_001",
            "execution_id": "exec_workspace_isolated_001",
            "grant_basis": {"workspace": {"mode": "isolated_rw"}},
            "path_policy": {
                "relative_paths_only": True,
                "parent_traversal_allowed": False,
                "absolute_paths_allowed": False,
            },
        },
    }
    payload.update(overrides)
    return _event("evt_006", "workspace.lease_created", payload)


def _events(*tail):
    return [_run_created(), _agent_created(), *tail]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def test_workspace_lease_created_projects_lifecycle_read_model():
    state = projector.RunProjector().project(_events(_lease_created()))

    lease = state.workspaces[WORKSPACE_ID]
    assert lease["workspace_id"] == WORKSPACE_ID
    assert lease["run_id"] == RUN_ID
    assert lease["mode"] == "shared_ro"
    assert lease["lease_status"] == "created"
    assert lease["bound_to"] == {"type": "agent", "agent_id": "agent_supervisor"}
    assert lease["granted_by"] == {"decision_id": "dec_workspace_001"}
    assert lease["created_by"] == {
        "proposal_id": "prop_workspace_001",
        "execution_id": "exec_workspace_001",
    }
    assert lease["released_by"] is None
    assert lease["released_at"] is None
    assert lease["last_event_id"] == "evt_003"
    assert lease["provenance"]["decision_id"] == "dec_workspace_001"


def test_isolated_rw_workspace_lease_projects_lifecycle_read_model():
    state = projector.RunProjector().project(_events(_isolated_rw_lease_created()))

    lease = state.workspaces[ISOLATED_WORKSPACE_ID]
    assert lease["workspace_id"] == ISOLATED_WORKSPACE_ID
    assert lease["mode"] == "isolated_rw"
    assert lease["lease_status"] == "created"
    assert lease["granted_by"] == {"decision_id": "dec_workspace_isolated_001"}
    assert lease["created_by"]["execution_id"] == "exec_workspace_isolated_001"
    assert lease["provenance"]["grant_basis"]["workspace"] == {"mode": "isolated_rw"}
    assert lease["provenance"]["path_policy"] == {
        "relative_paths_only": True,
        "parent_traversal_allowed": False,
        "absolute_paths_allowed": False,
    }


def test_isolated_rw_workspace_lease_checkpoint_assisted_rebuild(tmp_path):
    canonical_events = _events(_isolated_rw_lease_created())
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint(RUN_ID, canonical_events)
    checkpoints.save_checkpoint(RUN_ID, checkpoint)

    restored = projector.RunProjector().rebuild_with_checkpoint(
        RUN_ID,
        events_store,
        checkpoints,
    )

    assert restored.workspaces[ISOLATED_WORKSPACE_ID]["mode"] == "isolated_rw"
    assert restored.workspaces[ISOLATED_WORKSPACE_ID]["lease_status"] == "created"


def test_workspace_bound_lifecycle_entry_preserves_policy_and_creator_basis():
    state = projector.RunProjector().project(_events(_lease_created(), _workspace_bound()))

    binding = state.workspaces[WORKSPACE_ID]
    assert binding["lease_status"] == "active"
    assert binding["granted_by"] == {"decision_id": "dec_workspace_001"}
    assert binding["created_by"]["execution_id"] == "exec_workspace_001"
    assert binding["last_event_id"] == "evt_004"
    assert binding["provenance"]["grant_basis"]["workspace"]["mode"] == "shared_ro"


def test_workspace_released_updates_lease_without_deleting_history():
    state = projector.RunProjector().project(
        _events(_lease_created(), _workspace_bound(), _workspace_released())
    )

    lease = state.workspaces[WORKSPACE_ID]
    assert lease["lease_status"] == "released"
    assert lease["released_by"] == {"type": "agent", "agent_id": "agent_supervisor"}
    assert lease["released_at"] == "2026-05-03T00:05:00Z"
    assert lease["last_event_id"] == "evt_005"
    assert lease["created_by"]["proposal_id"] == "prop_workspace_001"
    assert lease["granted_by"]["decision_id"] == "dec_workspace_001"


def test_workspace_lease_replay_matches_direct_projection(tmp_path):
    canonical_events = _events(_lease_created(), _workspace_bound(), _workspace_released())
    store = event_store.FileEventStore(tmp_path)
    _write_events(store, canonical_events)

    direct = projector.RunProjector().project(canonical_events)
    replayed = projector.RunProjector().rebuild(RUN_ID, store)

    assert replayed.workspaces == direct.workspaces
    assert replayed.workspaces[WORKSPACE_ID]["lease_status"] == "released"


def test_workspace_lease_checkpoint_assisted_rebuild_restores_lifecycle(tmp_path):
    prefix_events = _events(_lease_created(), _workspace_bound())
    canonical_events = [*prefix_events, _workspace_released()]
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint(RUN_ID, prefix_events)
    checkpoints.save_checkpoint(RUN_ID, checkpoint)

    direct = projector.RunProjector().rebuild(RUN_ID, events_store)
    restored = projector.RunProjector().rebuild_with_checkpoint(RUN_ID, events_store, checkpoints)

    assert restored.workspaces == direct.workspaces
    assert restored.workspaces[WORKSPACE_ID]["lease_status"] == "released"
    assert restored.workspaces[WORKSPACE_ID]["last_event_id"] == "evt_005"


@pytest.mark.parametrize(
    "bad_event",
    [
        _lease_created(workspace_id=""),
        _lease_created(run_id="other_run"),
        _lease_created(mode="write"),
        _lease_created(granted_by={}),
        _lease_created(created_by="not-a-dict"),
        _lease_created(provenance={"decision_id": "dec_workspace_001"}),
    ],
)
def test_malformed_workspace_lease_created_fails_fast(bad_event):
    with pytest.raises((PermissionError, TypeError, ValueError), match="workspace|lease|grant|mode"):
        projector.RunProjector().project(_events(bad_event))


@pytest.mark.parametrize(
    "bad_event",
    [
        _workspace_released(workspace_id=""),
        _workspace_released(run_id="other_run"),
        _workspace_released(released_by="not-a-dict"),
        _workspace_released(released_at=""),
        _workspace_released(basis_event_id="not-the-binding-event"),
    ],
)
def test_malformed_workspace_released_fails_fast(bad_event):
    with pytest.raises((TypeError, ValueError), match="workspace|release|basis"):
        projector.RunProjector().project(_events(_lease_created(), _workspace_bound(), bad_event))


def test_workspace_release_unknown_workspace_fails_fast():
    with pytest.raises(ValueError, match="workspace|unknown|release"):
        projector.RunProjector().project(_events(_workspace_released()))


def test_workspace_release_already_released_workspace_fails_fast():
    with pytest.raises(ValueError, match="workspace|already released|release"):
        projector.RunProjector().project(
            _events(
                _lease_created(),
                _workspace_bound(),
                _workspace_released(),
                _workspace_released(reason="duplicate release"),
            )
        )


def test_agent_identity_alone_cannot_create_workspace_lease():
    with pytest.raises((PermissionError, ValueError), match="workspace|grant|decision"):
        projector.RunProjector().project(
            _events(
                _lease_created(
                    granted_by={},
                    provenance={
                        "proposal_id": "prop_workspace_001",
                        "execution_id": "exec_workspace_001",
                    },
                )
            )
        )


def test_unsupported_workspace_modes_remain_rejected():
    manager = workspace.WorkspaceManager()

    for mode in ("write", "shared_rw", "isolated_ro", "isolated_rw", "ephemeral"):
        with pytest.raises(PermissionError, match="workspace mode is not supported"):
            manager.get_binding({"workspace": {"mode": mode}})
