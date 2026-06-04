"""Review and approval developer demo scenarios."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .demo_common import _route_status
from ..interfaces.http import create_http_app
from ..platform.schemas.refs import make_artifact_ref
from ..platform.schemas.snapshots import ImportedSnapshot
from ..platform.state.checkpoint_store import FileCheckpointStore
from ..platform.state.projector import RunProjector


def _run_approval_tool_runner_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)

    session_response = app.request("POST", "/sessions", {})
    session_id = session_response.body["session_id"]  # type: ignore[index]
    run_response = app.request(
        "POST",
        f"/sessions/{session_id}/runs",
        {"goal": "approval-gated tool runner spike"},
    )
    run_id = run_response.body["run_id"]  # type: ignore[index]

    pending = app.server.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "approval-gated tool output",
        },
        requires_approval=True,
    )
    pending_state = app.server.get_run_state(run_id)
    pending_approvals = app.server.get_pending_approvals(run_id)
    approval_id = pending_approvals[0]["approval_id"] if pending_approvals else ""
    if not approval_id:
        raise RuntimeError("approval-gated tool runner spike did not request approval")

    app.server.bind_workspace(
        run_id=run_id,
        decision=pending["decision"],
    )

    pending_http_state_response = app.request("GET", f"/runs/{run_id}")
    resolve_response = app.request(
        "POST",
        f"/runs/{run_id}/approvals/{approval_id}/resolve",
        {
            "resolution": "approved",
            "reason": "approval-gated spike",
            "resolver": "developer_demo",
        },
    )
    state_response = app.request("GET", f"/runs/{run_id}")
    events_response = app.request("GET", f"/runs/{run_id}/events")

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint_store = FileCheckpointStore(root / "approval-tool-runner-checkpoints")
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )

    artifact = app.server.artifact_store.list_artifacts(run_id)[-1]
    artifact_ref = artifact.ref.to_dict()
    artifact_summary_response = app.request(
        "GET",
        f"/artifacts/{artifact.artifact_id}/summary",
    )
    http_full_content_response = app.request("GET", f"/artifacts/{artifact.artifact_id}/content")

    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    workspace_binding = replay_state.workspaces.get("workspace_shared_ro", {})
    replay_workspaces = dict(replay_state.workspaces)
    checkpoint_workspaces = dict(checkpoint_state.workspaces)
    pending_before_resume = (
        pending["status"] == "pending_user_approval"
        and pending_state.status == "pending_user_approval"
    )
    approval_ok = (
        "approval.requested" in event_types
        and "approval.resolved" in event_types
        and event_types.index("approval.requested") < event_types.index("approval.resolved")
        and event_types.index("approval.resolved") < event_types.index("action.started")
        and resolve_response.status_code == 200
    )
    workspace_binding_ok = (
        "workspace.bound" in event_types
        and workspace_binding.get("workspace_id") == "workspace_shared_ro"
        and workspace_binding.get("mode") == "shared_ro"
        and workspace_binding.get("lease_status") == "active"
        and event_types.index("workspace.bound") < event_types.index("action.started")
    )
    artifact_handoff_ok = (
        artifact_summary_response.status_code == 200
        and artifact_ref.get("ref_type") == "artifact"
        and artifact_ref.get("scope") == "run"
        and artifact_ref.get("run_id") == run_id
        and "artifact.created" in event_types
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    http_api_ok = (
        session_response.status_code == 201
        and run_response.status_code == 201
        and pending_http_state_response.status_code == 200
        and state_response.status_code == 200
        and events_response.status_code == 200
    )

    return {
        "scenario": "approval-tool-runner",
        "session_id": session_id,
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "http_api_ok": http_api_ok,
        "approval_tool_runner_ok": (
            pending_before_resume
            and approval_ok
            and workspace_binding_ok
            and artifact_handoff_ok
            and replay_ok
            and checkpoint_ok
        ),
        "approval_pending_before_resume": pending_before_resume,
        "approval_ok": approval_ok,
        "workspace_binding_ok": workspace_binding_ok,
        "artifact_handoff_ok": artifact_handoff_ok,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_workspaces_ok": replay_workspaces == final_state.workspaces,
        "checkpoint_workspaces_ok": checkpoint_workspaces == replay_workspaces,
        "workspace_binding": dict(workspace_binding),
        "replay_workspaces": replay_workspaces,
        "checkpoint_workspaces": checkpoint_workspaces,
        "artifact_ref": artifact_ref,
        "artifact_summary": artifact.summary,
        "event_count": len(event_types),
        "event_types": event_types,
        "http_full_content_route_status": _route_status(http_full_content_response),
        "filesystem_mutation_status": "not_used",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "memory_status": "active",
        "memory_query_status": "unavailable",
        "api_friction": [
            "approval-gated input now uses server.submit_action; HTTP /runs/{run_id}/input still has no approval flag",
        ],
    }

def _run_external_snapshot_review_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)

    session_response = app.request("POST", "/sessions", {})
    session_id = session_response.body["session_id"]  # type: ignore[index]
    run_response = app.request(
        "POST",
        f"/sessions/{session_id}/runs",
        {"goal": "external snapshot review spike"},
    )
    run_id = run_response.body["run_id"]  # type: ignore[index]
    input_response = app.request(
        "POST",
        f"/runs/{run_id}/input",
        {"text": "native application state remains canonical"},
    )
    native_state = app.server.get_run_state(run_id)
    native_actions = {key: dict(value) for key, value in native_state.actions.items()}

    app.server.import_external_snapshot(
        run_id,
        _external_snapshot(
            run_id,
            "snapshot_001",
            claimed_status="completed",
            source_artifact_id="external_raw_snapshot_001",
            confidence=0.76,
        ),
    )
    app.server.import_external_snapshot(
        run_id,
        _external_snapshot(
            run_id,
            "snapshot_002",
            claimed_status="failed",
            source_artifact_id="external_raw_snapshot_002",
            confidence=0.61,
        ),
    )

    events = app.server.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    final_state = app.server.get_run_state(run_id)
    checkpoint_store = FileCheckpointStore(root / "external-snapshot-review-checkpoints")
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )

    http_external_ingestion_response = app.request(
        "POST",
        "/external-ingestion",
        json={
            "run_id": run_id,
            "source_system": "example_provider",
            "captured_at": "2026-05-01T00:05:00Z",
            "body": {"message": "external snapshot review demo"},
        },
    )
    event_types = [event.event_type for event in events]
    external_observations = [dict(observation) for observation in replay_state.external_observations]
    conflict_diagnostics = [
        {
            "snapshot_id": observation["snapshot_id"],
            "snapshot_type": observation["snapshot_type"],
            "status": observation["status"],
            "conflict_status": observation["conflict_status"],
            "native_status": observation.get("native_status"),
            "basis_refs": [dict(ref) for ref in observation["basis_refs"]],
        }
        for observation in external_observations
        if observation.get("conflict_status") == "conflict"
    ]
    native_state_preserved = (
        replay_state.status == native_state.status
        and {key: dict(value) for key, value in replay_state.actions.items()} == native_actions
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    snapshot_imported_ok = (
        event_types.count("snapshot.imported") >= 2
        and len(external_observations) >= 2
        and bool(conflict_diagnostics)
    )
    http_api_ok = (
        session_response.status_code == 201
        and run_response.status_code == 201
        and input_response.status_code == 200
    )

    return {
        "scenario": "external-snapshot-review",
        "session_id": session_id,
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "http_api_ok": http_api_ok,
        "snapshot_imported_ok": snapshot_imported_ok,
        "external_observation_count": len(external_observations),
        "external_observations": external_observations,
        "conflict_diagnostics_count": len(conflict_diagnostics),
        "conflict_diagnostics": conflict_diagnostics,
        "native_state_preserved": native_state_preserved,
        "native_run_status": native_state.status,
        "native_action_statuses": {
            execution_id: action.get("status")
            for execution_id, action in native_actions.items()
        },
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_external_observations": [dict(observation) for observation in replay_state.external_observations],
        "checkpoint_external_observations": [
            dict(observation) for observation in checkpoint_state.external_observations
        ],
        "event_count": len(event_types),
        "event_types": event_types,
        "http_external_ingestion_route_status": _route_status(http_external_ingestion_response),
        "provider_status": "active",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "filesystem_mutation_status": "not_used",
        "memory_status": "active",
        "memory_query_status": "active",
        "memory_storage_status": "active",
        "projector_raw_content_read_status": "not_used",
    }


def _external_snapshot(
    run_id: str,
    snapshot_id: str,
    *,
    claimed_status: str,
    source_artifact_id: str,
    confidence: float,
) -> ImportedSnapshot:
    source_ref = make_artifact_ref(run_id, source_artifact_id)
    return ImportedSnapshot(
        snapshot_id=snapshot_id,
        source_system="example_provider",
        captured_at="2026-05-01T00:03:00Z",
        content_type="run_status",
        source_ref=source_ref,
        summary=f"provider claims run is {claimed_status}",
        observation={
            "subject": {"type": "run", "id": run_id},
            "run_status": claimed_status,
        },
        quality={
            "confidence": confidence,
            "coverage": "partial",
            "freshness": "fresh",
        },
        provenance={
            "provider": "example_provider",
            "capture_id": f"capture_{snapshot_id}",
            "raw_artifact_ref": source_ref.to_dict(),
        },
        basis_refs=[source_ref.to_dict()],
    )
