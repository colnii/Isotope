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
from .models import ImportedSnapshot
from .projector import RunProjector
from .refs import make_artifact_ref
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
        choices=(
            "v0.1",
            "v0.2",
            "approval-tool-runner",
            "artifact-review",
            "external-snapshot-review",
            "agent-loop-friction",
        ),
        default="v0.1",
        help="demo scenario to run",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--trace", action="store_true", help="print human-readable execution trace")
    args = parser.parse_args(argv)

    result = run_demo(scenario=args.scenario)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif args.trace:
        print(_format_trace(result))
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
    if scenario == "artifact-review":
        return _run_artifact_review_spike(root)
    if scenario == "external-snapshot-review":
        return _run_external_snapshot_review_spike(root)
    if scenario == "agent-loop-friction":
        return _run_agent_loop_friction_spike(root)
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
        "http_full_content_route_status": _deferred_status(http_full_content_response),
        "filesystem_mutation_status": "not_used",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "api_friction": [
            "approval-gated input now uses server.submit_action; HTTP /runs/{run_id}/input still has no approval flag",
        ],
    }


def _run_artifact_review_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)

    session_response = app.request("POST", "/sessions", {})
    session_id = session_response.body["session_id"]  # type: ignore[index]
    run_response = app.request(
        "POST",
        f"/sessions/{session_id}/runs",
        {"goal": "artifact review flow spike"},
    )
    run_id = run_response.body["run_id"]  # type: ignore[index]

    source_setup = app.server.create_source_artifact(
        run_id,
        summary="source artifact summary",
        content="source artifact durable content",
    )
    source_artifact_ref = source_setup["artifact_ref"]
    source_record = app.server.get_artifact_record(source_artifact_ref)

    source_summary = app.server.retrieval.get_artifact_summary(
        source_artifact_ref,
        {"artifact": {"read": "summary"}},
    )
    controlled_retrieval = app.server.retrieval.get_artifact_content(
        source_artifact_ref,
        grants={"artifact": {"read": "full"}},
        caller_context={
            "caller": "artifact_review_demo",
            "run_id": run_id,
            "source_artifact_id": source_record["artifact_id"],
        },
        purpose="artifact_review_flow",
    )
    summary_only_ok = "content" not in source_summary and source_summary["ref"] == source_artifact_ref.to_dict()
    controlled_retrieval_ok = (
        controlled_retrieval.get("status") == "ok"
        and controlled_retrieval.get("view") == "full"
        and isinstance(controlled_retrieval.get("content"), str)
    )

    review_result = app.server.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "review artifact durable content: accepted source artifact",
        },
    )
    review_artifact_ref = review_result["artifact_ref"].to_dict()
    review_artifact = app.server.artifact_store.list_artifacts(run_id)[-1]

    state_response = app.request("GET", f"/runs/{run_id}")
    events_response = app.request("GET", f"/runs/{run_id}/events")
    source_summary_response = app.request(
        "GET",
        f"/artifacts/{source_record['artifact_id']}/summary",
    )
    review_summary_response = app.request(
        "GET",
        f"/artifacts/{review_artifact.artifact_id}/summary",
    )
    http_full_content_response = app.request(
        "GET",
        f"/artifacts/{source_record['artifact_id']}/content",
    )

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint_store = FileCheckpointStore(root / "artifact-review-checkpoints")
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    replay_artifacts = list(replay_state.artifacts)
    checkpoint_artifacts = list(checkpoint_state.artifacts)
    replay_artifact_refs = [artifact["ref"] for artifact in replay_artifacts]
    checkpoint_artifact_refs = [artifact["ref"] for artifact in checkpoint_artifacts]
    replay_artifact_summaries = [artifact["summary"] for artifact in replay_artifacts]
    checkpoint_artifact_summaries = [artifact["summary"] for artifact in checkpoint_artifacts]
    review_artifact_state = next(
        artifact for artifact in replay_artifacts if artifact["ref"] == review_artifact_ref
    )
    review_decision = {
        "status": "accepted",
        "source_ref": source_artifact_ref.to_dict(),
        "basis_summary": source_summary["summary"],
        "review_artifact_ref": review_artifact_ref,
        "provenance": {
            "source_ref": source_artifact_ref.to_dict(),
            "source_basis_event_id": source_record["basis_event_id"],
            "review_artifact_ref": review_artifact_ref,
            "review_execution_id": review_result["execution_id"],
        },
    }
    review_action_chain_ok = (
        event_types.count("action.proposed") >= 1
        and event_types.count("action.decided") >= 1
        and event_types.count("action.started") >= 1
        and event_types.count("action.completed") >= 1
        and event_types.count("artifact.created") >= 2
        and review_artifact_ref in replay_artifact_refs
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    content_policy_ok = (
        summary_only_ok
        and controlled_retrieval_ok
        and _deferred_status(http_full_content_response) == "not_enabled"
    )
    http_api_ok = (
        session_response.status_code == 201
        and run_response.status_code == 201
        and state_response.status_code == 200
        and events_response.status_code == 200
        and source_summary_response.status_code == 200
        and review_summary_response.status_code == 200
    )

    return {
        "scenario": "artifact-review",
        "session_id": session_id,
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "http_api_ok": http_api_ok,
        "review_ok": (
            review_action_chain_ok
            and content_policy_ok
            and replay_ok
            and checkpoint_ok
            and replay_state.status == "completed"
        ),
        "artifact_ref": source_artifact_ref.to_dict(),
        "review_artifact_ref": review_artifact_ref,
        "source_summary": source_summary,
        "source_artifact_record": source_record,
        "source_setup": {
            "status": source_setup["status"],
            "proposal_id": source_setup["proposal_id"],
            "decision_id": source_setup["decision_id"],
            "execution_id": source_setup["execution_id"],
            "artifact_ref": source_setup["artifact_ref"].to_dict(),
            "artifact_summary": source_setup["artifact_summary"],
            "artifact_type": source_setup["artifact_type"],
            "provenance": dict(source_setup["provenance"]),
        },
        "review_summary": review_artifact.summary,
        "review_decision": review_decision,
        "review_artifact_provenance": dict(review_artifact_state["provenance"]),
        "review_action_chain_ok": review_action_chain_ok,
        "summary_only_ok": summary_only_ok,
        "content_policy_ok": content_policy_ok,
        "controlled_retrieval_ok": controlled_retrieval_ok,
        "controlled_retrieval_view": controlled_retrieval.get("view"),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_artifacts": replay_artifacts,
        "checkpoint_artifacts": checkpoint_artifacts,
        "replay_artifact_refs": replay_artifact_refs,
        "checkpoint_artifact_refs": checkpoint_artifact_refs,
        "replay_artifact_summaries": replay_artifact_summaries,
        "checkpoint_artifact_summaries": checkpoint_artifact_summaries,
        "event_count": len(event_types),
        "event_types": event_types,
        "http_full_content_route_status": _deferred_status(http_full_content_response),
        "filesystem_mutation_status": "not_used",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "semantic_retrieval_status": "not_used",
        "ranking_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
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
        {"text": "native kernel state remains canonical"},
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
        json={"source_system": "example_provider"},
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
        "http_external_ingestion_route_status": _deferred_status(http_external_ingestion_response),
        "provider_status": "boundary_only",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "filesystem_mutation_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "memory_storage_status": "not_enabled",
        "projector_raw_content_read_status": "not_used",
    }


def _run_agent_loop_friction_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    api = InProcessServer(root)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="deterministic agent loop friction review")
    run_id = run["run_id"]

    source_setup = api.create_source_artifact(
        run_id,
        summary="agent loop planning summary",
        content="deterministic app-layer planning input",
    )
    handoff = api.submit_worker_handoff(
        run_id,
        delegation_intent={
            "parent_agent_id": "agent_supervisor",
            "requested_worker_role": "worker",
            "requested_capabilities": {
                "tools": ["write_artifact_tool"],
                "workspace": {"mode": "shared_ro"},
                "budget": {"seconds": 30},
            },
        },
        artifact_ref=source_setup["artifact_ref"],
        summary="deterministic worker result handoff for agent loop review",
    )
    pending = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "deterministic agent loop final artifact",
        },
        requires_approval=True,
    )
    pending_approvals = api.get_pending_approvals(run_id)
    approval_id = pending_approvals[0]["approval_id"] if pending_approvals else ""
    if not approval_id:
        raise RuntimeError("agent loop friction spike did not request approval")
    workspace_binding = api.bind_workspace(run_id=run_id, decision=pending["decision"])
    resolution = api.resolve_approval(
        approval_id,
        {
            "resolution": "approved",
            "reason": "agent loop friction review",
            "resolver": "developer_demo",
        },
    )

    events = api.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint_store = FileCheckpointStore(root / "agent-loop-friction-checkpoints")
    checkpoint = RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        api.event_store,
        checkpoint_store,
    )
    final_state = api.get_run_state(run_id)
    event_types = [event.event_type for event in events]
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    loop_steps = [
        "observe run context",
        "plan deterministic next action",
        "create source artifact through public helper",
        "handoff worker result through public helper",
        "pause on approval-gated action",
        "resume approved action",
        "review kernel friction report",
    ]
    resolved_kernel_surfaces = [
        "create_source_artifact",
        "submit_worker_handoff",
        "submit_action",
        "get_pending_approvals",
        "bind_workspace",
        "resolve_approval",
        "replay",
        "checkpoint",
    ]
    private_append_required = handoff["private_append_required"] is not False
    agent_loop_friction_ok = (
        source_setup["status"] == "completed"
        and handoff["status"] == "completed"
        and pending["status"] == "pending_user_approval"
        and resolution["status"] == "completed"
        and replay_state.status == "completed"
        and replay_ok
        and checkpoint_ok
        and workspace_binding.get("mode") == "shared_ro"
        and private_append_required is False
    )

    return {
        "scenario": "agent-loop-friction",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "agent_loop_friction_ok": agent_loop_friction_ok,
        "loop_steps": loop_steps,
        "resolved_kernel_surfaces": resolved_kernel_surfaces,
        "kernel_friction": [],
        "kernel_friction_count": 0,
        "private_append_required": private_append_required,
        "worker_handoff_ok": handoff["status"] == "completed",
        "approval_pending_before_resume": pending["status"] == "pending_user_approval",
        "approval_resume_ok": resolution["status"] == "completed",
        "workspace_binding_ok": workspace_binding.get("mode") == "shared_ro",
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "source_artifact_ref": source_setup["artifact_ref"].to_dict(),
        "worker_result_ref": handoff["result_ref"],
        "final_artifact_ref": resolution["artifact_ref"].to_dict(),
        "model_status": "not_used",
        "scheduler_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "filesystem_mutation_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "next_development_step": (
            "Run the same friction review behind a real app-layer planner adapter; "
            "only reopen kernel mainline if that produces non-empty kernel_friction."
        ),
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
    if result.get("scenario") == "agent-loop-friction":
        return _format_agent_loop_friction_plain_text(result)
    if result.get("scenario") == "external-snapshot-review":
        return _format_external_snapshot_review_plain_text(result)
    if result.get("scenario") == "artifact-review":
        return _format_artifact_review_plain_text(result)
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


def _format_trace(result: dict[str, Any]) -> str:
    scenario = result.get("scenario", "v0.1")
    if scenario == "agent-loop-friction":
        return _format_agent_loop_friction_trace(result)
    if scenario == "external-snapshot-review":
        return _format_external_snapshot_review_trace(result)
    if scenario == "artifact-review":
        return _format_artifact_review_trace(result)
    if scenario == "approval-tool-runner":
        return _format_approval_tool_runner_trace(result)
    if scenario == "v0.2":
        return _format_v0_2_trace(result)
    return _format_v0_1_trace(result)


def _format_v0_1_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "submit input through in-process server",
        f"policy approved action: {result['action_outcome']}",
        f"create artifact summary/ref: {_artifact_id(result.get('artifact_ref', {}))}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
    ]
    return _format_trace_steps("v0.1", steps)


def _format_v0_2_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session through HTTP facade: {result['session_id']}",
        f"create run through HTTP facade: {result['run_id']}",
        "submit input through HTTP facade",
        f"policy approved action: {_bool_text(result['http_api_ok'])}",
        f"create artifact summary/ref: event_count={result['event_count']}",
        f"controlled retrieval allowed: {_bool_text(result['artifact_content_policy_ok'])}",
        f"approval flow verified: {_bool_text(result['approval_ok'])}",
        f"replay verified: {_bool_text(result['http_api_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"HTTP full-content route remains: {result['http_full_content_route_status']}",
        f"memory query remains: {result['memory_query_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_approval_tool_runner_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "propose approval-gated tool action",
        f"policy requested approval: {_bool_text(result['approval_pending_before_resume'])}",
        f"bind shared_ro workspace: {_bool_text(result['workspace_binding_ok'])}",
        f"approval resolved as approved: {_bool_text(result['approval_ok'])}",
        f"action completed and artifact ref created: {_artifact_id(result['artifact_ref'])}",
        f"artifact handoff verified: {_bool_text(result['artifact_handoff_ok'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"HTTP full-content route remains: {result['http_full_content_route_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_artifact_review_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "create source action and policy decision: approved",
        f"create source artifact summary/ref: {_artifact_id(result['artifact_ref'])}",
        f"read source artifact summary only: {_bool_text(result['summary_only_ok'])}",
        f"policy approved controlled retrieval: {_bool_text(result['controlled_retrieval_ok'])}",
        "propose review action through action chain",
        f"create review artifact summary/ref: {_artifact_id(result['review_artifact_ref'])}",
        f"action completed: {_bool_text(result['review_action_chain_ok'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"HTTP full-content route remains: {result['http_full_content_route_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_external_snapshot_review_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "create native action/artifact before importing external observations",
        f"append deterministic snapshot.imported events: {result['external_observation_count']}",
        f"conflict diagnostics recorded: {result['conflict_diagnostics_count']}",
        f"native state preserved: {_bool_text(result['native_state_preserved'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"external ingestion HTTP route remains: {result['http_external_ingestion_route_status']}",
        f"provider status: {result['provider_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_friction_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "observe run context",
        "plan deterministic next action",
        f"source artifact summary/ref created: {_artifact_id(result['source_artifact_ref'])}",
        f"handoff worker result: {_bool_text(result['worker_handoff_ok'])}",
        f"policy-gated approval pause/resume verified: {_bool_text(result['approval_resume_ok'])}",
        f"kernel friction count: {result['kernel_friction_count']}",
        f"private append required: {_bool_text(result['private_append_required'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_trace_steps(scenario: str, steps: list[str]) -> str:
    lines = [f"scenario: {scenario}"]
    lines.extend(f"[{index}] {step}" for index, step in enumerate(steps, start=1))
    return "\n".join(lines)


def _artifact_id(ref: dict[str, Any]) -> str:
    artifact_id = ref.get("artifact_id")
    if isinstance(artifact_id, str) and artifact_id:
        return artifact_id
    return "available"


def _bool_text(value: Any) -> str:
    return str(bool(value)).lower()


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


def _format_artifact_review_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"review_ok: {str(result['review_ok']).lower()}",
        f"content_policy_ok: {str(result['content_policy_ok']).lower()}",
        f"controlled_retrieval_ok: {str(result['controlled_retrieval_ok']).lower()}",
        f"review_action_chain_ok: {str(result['review_action_chain_ok']).lower()}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"http_full_content_route_status: {result['http_full_content_route_status']}",
        f"filesystem_mutation_status: {result['filesystem_mutation_status']}",
        f"model_status: {result['model_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_external_snapshot_review_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"snapshot_imported_ok: {str(result['snapshot_imported_ok']).lower()}",
        f"external_observation_count: {result['external_observation_count']}",
        f"conflict_diagnostics_count: {result['conflict_diagnostics_count']}",
        f"native_state_preserved: {str(result['native_state_preserved']).lower()}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"http_external_ingestion_route_status: {result['http_external_ingestion_route_status']}",
        f"provider_status: {result['provider_status']}",
        f"model_status: {result['model_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_agent_loop_friction_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"agent_loop_friction_ok: {str(result['agent_loop_friction_ok']).lower()}",
        f"private_append_required: {str(result['private_append_required']).lower()}",
        f"kernel_friction_count: {result['kernel_friction_count']}",
        f"worker_handoff_ok: {str(result['worker_handoff_ok']).lower()}",
        f"approval_resume_ok: {str(result['approval_resume_ok']).lower()}",
        f"workspace_binding_ok: {str(result['workspace_binding_ok']).lower()}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
