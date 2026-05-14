import json

import pytest

from isotope import checkpoint_store, event_store, events, projector


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-02T00:02:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _agent_created():
    return _event(
        "evt_002",
        "agent.created",
        {
            "agent_id": "agent_supervisor",
            "role": "supervisor",
            "status": "created",
        },
    )


def _workspace_bound(**overrides):
    payload = {
        "workspace_id": "workspace_shared_ro",
        "run_id": "run_001",
        "mode": "shared_ro",
        "bound_to": {"agent_id": "agent_supervisor"},
        "lease_status": "active",
        "provenance": {
            "decision_id": "dec_workspace_001",
            "grant_basis": {"workspace": {"mode": "shared_ro"}},
        },
    }
    payload.update(overrides)
    return _event("evt_003", "workspace.bound", payload)


def _events(*tail):
    return [_run_created(), _agent_created(), *tail]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def test_workspace_binding_is_first_class_run_state_read_model():
    state = projector.RunProjector().project(_events(_workspace_bound()))

    assert hasattr(state, "workspaces")
    assert "workspace_shared_ro" in state.workspaces
    binding = state.workspaces["workspace_shared_ro"]
    assert binding["workspace_id"] == "workspace_shared_ro"
    assert binding["run_id"] == "run_001"
    assert binding["mode"] == "shared_ro"
    assert binding["bound_to"] == {"agent_id": "agent_supervisor"}
    assert binding["lease_status"] == "active"
    assert binding["provenance"]["decision_id"] == "dec_workspace_001"
    assert binding["basis_event_id"] == "evt_003"


def test_workspace_binding_is_projected_only_from_canonical_event():
    state = projector.RunProjector().project(_events())

    assert hasattr(state, "workspaces")
    assert state.workspaces == {}


def test_workspace_binding_replay_matches_direct_projection(tmp_path):
    canonical_events = _events(_workspace_bound())
    store = event_store.FileEventStore(tmp_path)
    _write_events(store, canonical_events)

    direct = projector.RunProjector().project(canonical_events)
    replayed = projector.RunProjector().rebuild("run_001", store)

    assert replayed.workspaces == direct.workspaces


def test_workspace_binding_checkpoint_assisted_rebuild_matches_full_rebuild(tmp_path):
    canonical_events = _events(_workspace_bound())
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint("run_001", canonical_events)
    checkpoints.save_checkpoint("run_001", checkpoint)

    direct = projector.RunProjector().rebuild("run_001", events_store)
    restored = projector.RunProjector().rebuild_with_checkpoint("run_001", events_store, checkpoints)

    assert restored.workspaces == direct.workspaces
    assert restored.workspaces["workspace_shared_ro"]["lease_status"] == "active"


def test_workspace_binding_checkpoint_state_contains_workspace_read_model():
    checkpoint = projector.RunProjector().create_checkpoint("run_001", _events(_workspace_bound()))

    assert "workspaces" in checkpoint["state"]
    assert checkpoint["state"]["workspaces"]["workspace_shared_ro"]["basis_event_id"] == "evt_003"


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"run_id": "run_001", "mode": "shared_ro", "bound_to": {"agent_id": "agent_supervisor"}},
        {"workspace_id": "workspace_shared_ro", "run_id": "run_001", "bound_to": {"agent_id": "agent_supervisor"}},
        {"workspace_id": "workspace_shared_ro", "run_id": "run_001", "mode": "shared_ro"},
        {
            "workspace_id": "workspace_shared_ro",
            "run_id": "run_001",
            "mode": "shared_ro",
            "bound_to": {"agent_id": "agent_supervisor"},
            "lease_status": "active",
            "provenance": "not-a-dict",
        },
    ],
)
def test_malformed_workspace_binding_event_fails_fast(bad_payload):
    with pytest.raises((TypeError, ValueError), match="workspace.bound|workspace"):
        projector.RunProjector().project(_events(_event("evt_003", "workspace.bound", bad_payload)))


def test_workspace_binding_projection_does_not_read_filesystem(tmp_path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    secret_file = workspace_root / "secret.txt"
    secret_file.write_text("secret workspace content", encoding="utf-8")

    state = projector.RunProjector().project(
        _events(
            _workspace_bound(
                workspace_root=str(workspace_root),
                path_hint=str(secret_file),
            )
        )
    )

    serialized = json.dumps(state.workspaces, sort_keys=True)
    assert "secret workspace content" not in serialized
    assert "workspace_shared_ro" in state.workspaces


def test_workspace_binding_does_not_modify_native_run_or_action_status():
    state = projector.RunProjector().project(
        _events(
            _workspace_bound(
                status="completed",
                action_status="completed",
            )
        )
    )

    assert state.status == "running"
    assert state.actions == {}
