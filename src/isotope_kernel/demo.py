"""Developer demo entrypoint for the Isotope kernel slices."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .checkpoint_store import FileCheckpointStore
from .http_api import create_http_app
from .projector import RunProjector
from .server import InProcessServer


def run_demo(root_path: Path | str | None = None, scenario: str = "v0.1") -> dict[str, Any]:
    """Run a deterministic developer demo and return summary metadata."""

    if root_path is None:
        with tempfile.TemporaryDirectory(prefix="isotope-demo-") as temp_root:
            return _run_scenario(Path(temp_root), scenario=scenario)
    return _run_scenario(Path(root_path), scenario=scenario)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an Isotope developer demo.")
    parser.add_argument(
        "--scenario",
        choices=("v0.1", "v0.2", "approval-tool-runner"),
        default="v0.1",
        help="demo scenario to run",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    result = run_demo(scenario=args.scenario)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(_format_plain_text(result))
    return 0


def _run_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root)
    api = InProcessServer(root, checkpoint_store=checkpoint_store)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="demo deterministic artifact path")
    run_id = run["run_id"]
    api.submit_input(run_id, "hello")

    events = api.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(run_id, api.event_store, checkpoint_store)
    artifacts = api.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1]

    artifact_ref = artifact.ref.to_dict()
    checkpoint_artifact_ref = (
        checkpoint_state.artifacts[0]["ref"] if checkpoint_state.artifacts else {}
    )
    replay_ok = asdict(replay_state) == asdict(api.get_run_state(run_id))
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)

    return {
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "action_outcome": _latest_action_status(replay_state.actions),
        "artifact_ref": artifact_ref,
        "artifact_summary": artifact.summary,
        "event_count": len(events),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_run_status": replay_state.status,
        "checkpoint_run_status": checkpoint_state.status,
        "checkpoint_artifact_ref": checkpoint_artifact_ref,
        "memory_status": "boundary_only",
    }


def _run_scenario(root: Path, *, scenario: str) -> dict[str, Any]:
    if scenario == "v0.1":
        return _run_demo(root)
    if scenario == "v0.2":
        return _run_v0_2_demo(root)
    if scenario == "approval-tool-runner":
        return _run_approval_tool_runner_spike(root)
    raise ValueError(f"unsupported scenario: {scenario}")


def _run_v0_2_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)

    session_response = app.request("POST", "/sessions", {})
    session_id = session_response.body["session_id"]  # type: ignore[index]
    run_response = app.request(
        "POST",
        f"/sessions/{session_id}/runs",
        {"goal": "demo v0.2 HTTP facade path"},
    )
    run_id = run_response.body["run_id"]  # type: ignore[index]
    input_response = app.request("POST", f"/runs/{run_id}/input", {"text": "hello"})
    state_response = app.request("GET", f"/runs/{run_id}")
    events_response = app.request("GET", f"/runs/{run_id}/events")
    artifact_ref = input_response.body["artifact_ref"]  # type: ignore[index]
    artifact_id = artifact_ref["artifact_id"]
    artifact_summary_response = app.request("GET", f"/artifacts/{artifact_id}/summary")

    checkpoint_store = FileCheckpointStore(root)
    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )

    http_full_content_response = app.request("GET", f"/artifacts/{artifact_id}/content")
    artifact_policy_ok = _artifact_content_policy_ok(app, artifact_ref)
    approval_ok = _approval_flow_ok(root, app)
    http_api_ok = (
        session_response.status_code == 201
        and run_response.status_code == 201
        and input_response.status_code == 200
        and state_response.status_code == 200
        and events_response.status_code == 200
        and artifact_summary_response.status_code == 200
        and replay_state.status == "completed"
    )

    return {
        "scenario": "v0.2",
        "session_id": session_id,
        "run_id": run_id,
        "run_status": replay_state.status,
        "http_api_ok": http_api_ok,
        "approval_ok": approval_ok,
        "artifact_content_policy_ok": artifact_policy_ok,
        "checkpoint_ok": asdict(checkpoint_state) == asdict(replay_state),
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(events_response.body),  # type: ignore[arg-type]
        "http_full_content_route_status": _deferred_status(http_full_content_response),
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "memory_storage_status": "not_enabled",
    }


def _artifact_content_policy_ok(app: Any, artifact_ref: dict[str, Any]) -> bool:
    ref = app.server.artifact_store.list_artifacts(artifact_ref["run_id"])[-1].ref
    summary = app.server.retrieval.get_artifact_summary(
        ref,
        {"artifact": {"read": "summary"}},
    )
    content = app.server.retrieval.get_artifact_content(
        ref,
        grants={"artifact": {"read": "full"}},
        caller_context={"caller": "demo"},
        purpose="developer_demo",
    )
    return (
        "content" not in summary
        and summary["ref"] == ref.to_dict()
        and content["status"] == "ok"
        and content["view"] == "full"
        and isinstance(content.get("content"), str)
    )


def _approval_flow_ok(root: Path, app: Any) -> bool:
    session = app.server.create_session()
    approval_run = app.server.create_run(session["session_id"], goal="demo approval path")
    approval_run_id = approval_run["run_id"]
    pending = app.server.submit_tool_request(
        approval_run_id,
        tool="write_artifact_tool",
        text="approved artifact",
        requires_approval=True,
    )
    pending_approvals = app.server.get_pending_approvals(approval_run_id)
    approval_id = pending_approvals[0]["approval_id"] if pending_approvals else ""
    if pending["status"] != "pending_user_approval" or not approval_id:
        return False

    response = app.request(
        "POST",
        f"/runs/{approval_run_id}/approvals/{approval_id}/resolve",
        {
            "resolution": "approved",
            "reason": "demo approval",
            "resolver": "demo",
        },
    )
    if response.status_code != 200:
        return False
    event_types = [event.event_type for event in app.server.get_events(approval_run_id)]
    approved_state = app.server.get_run_state(approval_run_id)
    checkpoint_store = FileCheckpointStore(root / "approval-checkpoints")
    RunProjector().save_checkpoint(approval_run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        approval_run_id,
        app.server.event_store,
        checkpoint_store,
    )
    return (
        "approval.requested" in event_types
        and "approval.resolved" in event_types
        and event_types.index("approval.resolved") < event_types.index("action.started")
        and approved_state.status == "completed"
        and asdict(checkpoint_state) == asdict(approved_state)
    )


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

    pending = app.server.submit_tool_request(
        run_id,
        tool="write_artifact_tool",
        text="approval-gated tool output",
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
        "http_full_content_route_status": _deferred_status(http_full_content_response),
        "filesystem_mutation_status": "not_used",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "api_friction": [
            "approval-gated input currently uses server.submit_tool_request because POST /runs/{run_id}/input has no approval flag",
        ],
    }


def _append_workspace_binding_event(
    server: Any,
    *,
    run_id: str,
    decision: Any,
) -> None:
    workspace_grant = decision.grants.get("workspace", {})
    server._append(
        run_id,
        "workspace.bound",
        {
            "workspace_id": "workspace_shared_ro",
            "run_id": run_id,
            "mode": workspace_grant.get("mode", "shared_ro"),
            "bound_to": {"agent_id": "agent_supervisor"},
            "lease_status": "active",
            "provenance": {
                "decision_id": decision.decision_id,
                "grant_basis": {
                    "workspace": dict(workspace_grant),
                },
            },
        },
    )


def _latest_approval_id(events: list[Any]) -> str:
    for event in reversed(events):
        if event.event_type == "approval.requested":
            approval_id = event.payload.get("approval_id")
            if isinstance(approval_id, str):
                return approval_id
    return ""


def _deferred_status(response: Any) -> str:
    if response.status_code == 501:
        return "not_enabled"
    return "deferred"


def _latest_action_status(actions: dict[str, dict[str, Any]]) -> str:
    for action in reversed(list(actions.values())):
        status = action.get("status")
        if isinstance(status, str) and status:
            return status
    return "unknown"


def _format_plain_text(result: dict[str, Any]) -> str:
    if result.get("scenario") == "approval-tool-runner":
        return _format_approval_tool_runner_plain_text(result)
    if result.get("scenario") == "v0.2":
        return _format_v0_2_plain_text(result)
    lines = [
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"action_outcome: {result['action_outcome']}",
        f"artifact_ref: {json.dumps(result['artifact_ref'], sort_keys=True)}",
        f"artifact_summary: {result['artifact_summary']}",
        f"event_count: {result['event_count']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_v0_2_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"http_api_ok: {str(result['http_api_ok']).lower()}",
        f"approval_ok: {str(result['approval_ok']).lower()}",
        f"artifact_content_policy_ok: {str(result['artifact_content_policy_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"http_full_content_route_status: {result['http_full_content_route_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_approval_tool_runner_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"approval_tool_runner_ok: {str(result['approval_tool_runner_ok']).lower()}",
        f"approval_pending_before_resume: {str(result['approval_pending_before_resume']).lower()}",
        f"approval_ok: {str(result['approval_ok']).lower()}",
        f"workspace_binding_ok: {str(result['workspace_binding_ok']).lower()}",
        f"artifact_handoff_ok: {str(result['artifact_handoff_ok']).lower()}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"http_full_content_route_status: {result['http_full_content_route_status']}",
        f"filesystem_mutation_status: {result['filesystem_mutation_status']}",
        f"model_status: {result['model_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
