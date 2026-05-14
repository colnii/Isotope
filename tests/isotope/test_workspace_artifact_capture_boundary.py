import json

import pytest

from isotope import checkpoint_store, event_store, events, http_api, projector, workspace


RUN_ID = "run_001"
WORKSPACE_ID = "workspace_shared_ro"
ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": RUN_ID,
    "artifact_id": "artifact_workspace_capture_001",
}


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=RUN_ID,
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-03T00:05:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": RUN_ID})


def _agent_created():
    return _event("evt_002", "agent.created", {"agent_id": "agent_supervisor"})


def _workspace_bound(**overrides):
    payload = {
        "workspace_id": WORKSPACE_ID,
        "run_id": RUN_ID,
        "mode": "shared_ro",
        "bound_to": {"agent_id": "agent_supervisor"},
        "lease_status": "active",
        "provenance": {
            "decision_id": "dec_workspace_001",
            "proposal_id": "prop_workspace_001",
            "execution_id": "exec_workspace_001",
            "grant_basis": {"workspace": {"mode": "shared_ro"}},
        },
    }
    payload.update(overrides)
    return _event("evt_003", "workspace.bound", payload)


def _action_proposed():
    return _event(
        "evt_004",
        "action.proposed",
        {
            "proposal_id": "prop_capture_001",
            "agent_id": "agent_supervisor",
            "action_type": "capture_workspace_artifact",
            "registry_id": "default",
            "registry_version": "v0.2",
        },
    )


def _action_decided():
    return _event(
        "evt_005",
        "action.decided",
        {
            "proposal_id": "prop_capture_001",
            "decision_id": "dec_capture_001",
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


def _action_started():
    return _event(
        "evt_006",
        "action.started",
        {
            "execution_id": "exec_capture_001",
            "proposal_id": "prop_capture_001",
            "decision_id": "dec_capture_001",
        },
    )


def _artifact_created(**overrides):
    artifact = {
        "ref": dict(ARTIFACT_REF),
        "artifact_type": "text",
        "summary": "captured workspace summary",
        "provenance": {
            "execution_id": "exec_capture_001",
            "proposal_id": "prop_capture_001",
            "decision_id": "dec_capture_001",
            "workspace_id": WORKSPACE_ID,
        },
    }
    artifact.update(overrides)
    return _event("evt_007", "artifact.created", {"artifact": artifact})


def _workspace_artifact_captured(**overrides):
    payload = {
        "workspace_id": WORKSPACE_ID,
        "run_id": RUN_ID,
        "artifact_ref": dict(ARTIFACT_REF),
        "captured_by": {"execution_id": "exec_capture_001"},
        "provenance": {
            "artifact_event_id": "evt_007",
            "decision_id": "dec_capture_001",
            "basis_event_id": "evt_007",
        },
    }
    payload.update(overrides)
    return _event("evt_008", "workspace.artifact_captured", payload)


def _action_completed():
    return _event(
        "evt_009",
        "action.completed",
        {
            "execution_id": "exec_capture_001",
            "status": "completed",
            "artifact_refs": [dict(ARTIFACT_REF)],
        },
    )


def _events(*tail):
    return [_run_created(), _agent_created(), *tail]


def _capture_events(*extra_capture_events):
    return _events(
        _workspace_bound(),
        _action_proposed(),
        _action_decided(),
        _action_started(),
        _artifact_created(),
        *extra_capture_events,
        _action_completed(),
    )


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def test_workspace_artifact_capture_links_resource_ref_without_content():
    state = projector.RunProjector().project(_capture_events(_workspace_artifact_captured()))

    workspace_entry = state.workspaces[WORKSPACE_ID]
    assert workspace_entry["artifact_refs"] == [ARTIFACT_REF]
    assert workspace_entry["last_event_id"] == "evt_008"
    serialized = json.dumps(workspace_entry, sort_keys=True)
    assert "content" not in serialized
    assert "full_content" not in serialized
    assert "workspace file body" not in serialized


def test_workspace_artifact_capture_requires_prior_artifact_event():
    with pytest.raises(ValueError, match="artifact|workspace.artifact_captured|capture"):
        projector.RunProjector().project(
            _events(
                _workspace_bound(),
                _action_proposed(),
                _action_decided(),
                _action_started(),
                _workspace_artifact_captured(),
                _action_completed(),
            )
        )


def test_workspace_artifact_capture_rejects_unstructured_artifact_ref():
    with pytest.raises((TypeError, ValueError), match="ResourceRef|artifact_ref|workspace.artifact_captured"):
        projector.RunProjector().project(
            _capture_events(
                _workspace_artifact_captured(
                    artifact_ref="artifact://run_001/artifact_workspace_capture_001"
                )
            )
        )


def test_workspace_artifact_capture_rejects_full_content_payload():
    with pytest.raises(ValueError, match="content|full_content|workspace.artifact_captured"):
        projector.RunProjector().project(
            _capture_events(
                _workspace_artifact_captured(
                    content="workspace file body must stay outside RunState"
                )
            )
        )


def test_workspace_artifact_capture_replay_and_checkpoint_restore_links(tmp_path):
    canonical_events = _capture_events(_workspace_artifact_captured())
    events_store = event_store.FileEventStore(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    _write_events(events_store, canonical_events)
    checkpoint = projector.RunProjector().create_checkpoint(RUN_ID, canonical_events[:8])
    checkpoints.save_checkpoint(RUN_ID, checkpoint)

    direct = projector.RunProjector().rebuild(RUN_ID, events_store)
    restored = projector.RunProjector().rebuild_with_checkpoint(RUN_ID, events_store, checkpoints)

    assert restored.workspaces == direct.workspaces
    assert restored.workspaces[WORKSPACE_ID]["artifact_refs"] == [ARTIFACT_REF]
    assert restored.workspaces[WORKSPACE_ID]["last_event_id"] == "evt_008"


def test_projector_does_not_read_workspace_filesystem_for_artifact_capture(tmp_path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    workspace_file = workspace_root / "output.txt"
    workspace_file.write_text("secret workspace file content", encoding="utf-8")

    state = projector.RunProjector().project(
        _capture_events(
            _workspace_artifact_captured(
                workspace_path=str(workspace_file),
                path_hint=str(workspace_file),
            )
        )
    )

    serialized = json.dumps(
        {
            "workspaces": state.workspaces,
            "artifacts": state.artifacts,
            "actions": state.actions,
        },
        sort_keys=True,
    )
    assert "secret workspace file content" not in serialized


def test_workspace_artifact_capture_does_not_mutate_native_run_status():
    state = projector.RunProjector().project(_capture_events(_workspace_artifact_captured()))

    assert state.status == "running"
    assert state.actions["exec_capture_001"]["status"] == "completed"


def test_http_workspace_file_content_product_api_is_not_present(tmp_path):
    app = http_api.HttpApiApp(tmp_path)

    response = app.request("GET", f"/workspaces/{WORKSPACE_ID}/files/output.txt")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_no_container_git_worktree_remote_executor_or_binary_streaming_surface():
    assert not hasattr(workspace, "ContainerWorkspaceManager")
    assert not hasattr(workspace, "GitWorktreeWorkspaceManager")
    assert not hasattr(workspace, "RemoteWorkspaceExecutor")
    assert not hasattr(workspace.WorkspaceManager(), "mutate_filesystem")
    assert not hasattr(workspace.WorkspaceManager(), "stream_binary_artifact")
