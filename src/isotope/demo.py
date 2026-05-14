"""Developer demo entrypoint for the Isotope kernel slices."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import codex_server
from .checkpoint_store import FileCheckpointStore
from .interfaces.http import (
    HttpApiApp,
    create_codex_cli_http_app,
    create_http_app,
    create_llm_product_chat_http_app,
    create_llm_provider_http_app,
)
from .features.chat.product_chat import submit_llm_product_chat_user_message_with_preflight
from .llm_provider import (
    LLMFinalAnswerResponse,
    LLMToolCall,
    LLMToolCallResponse,
    build_llm_tool_result_message,
    submit_llm_tool_result_followup,
)
from .model_tool_bridge import submit_model_tool_call
from .models import ImportedSnapshot
from .projector import RunProjector
from .refs import make_artifact_ref
from .server import InProcessServer


_ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


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
            "agent-loop-planner-friction",
            "agent-loop-planner-matrix",
            "agent-loop-planner-restart-pause",
            "agent-loop-planner-io-validator",
            "agent-loop-planner-validated-runner",
            "terminal-exec",
            "model-tool-bridge",
            "llm-provider-route",
            "llm-tool-result-loop",
            "llm-product-chat-app-entry",
            "llm-terminal-tool-loop",
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
    if scenario == "agent-loop-planner-friction":
        return _run_agent_loop_planner_adapter_spike(root)
    if scenario == "agent-loop-planner-matrix":
        return _run_agent_loop_planner_matrix_spike(root)
    if scenario == "agent-loop-planner-restart-pause":
        return _run_agent_loop_planner_restart_pause_spike(root)
    if scenario == "agent-loop-planner-io-validator":
        return _run_agent_loop_planner_io_validator_spike(root)
    if scenario == "agent-loop-planner-validated-runner":
        return _run_agent_loop_planner_validated_runner_spike(root)
    if scenario == "terminal-exec":
        return _run_terminal_exec_demo(root)
    if scenario == "model-tool-bridge":
        return _run_model_tool_bridge_demo(root)
    if scenario == "llm-provider-route":
        return _run_llm_provider_route_demo(root)
    if scenario == "llm-tool-result-loop":
        return _run_llm_tool_result_loop_demo(root)
    if scenario == "llm-product-chat-app-entry":
        return _run_llm_product_chat_app_entry_demo(root)
    if scenario == "llm-terminal-tool-loop":
        return _run_llm_terminal_tool_loop_demo(root)
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


def _run_agent_loop_planner_adapter_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    api = InProcessServer(root)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="deterministic planner adapter friction review")
    run_id = run["run_id"]
    planner_input_summary = {
        "run_id": run_id,
        "run_status": api.get_run_state(run_id).status,
        "available_public_helpers": [
            "create_source_artifact",
            "submit_worker_handoff",
            "submit_action",
            "bind_workspace",
            "resolve_approval",
        ],
    }
    planner_decisions = _deterministic_planner_decisions(planner_input_summary)

    source_setup: dict[str, Any] | None = None
    handoff: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None
    workspace_binding: dict[str, Any] = {}
    resolution: dict[str, Any] | None = None

    for decision in planner_decisions:
        action = decision["action"]
        if action == "create_source_artifact":
            source_setup = api.create_source_artifact(
                run_id,
                summary="planner adapter source summary",
                content="deterministic planner adapter input",
            )
        elif action == "submit_worker_handoff":
            if source_setup is None:
                raise RuntimeError("planner selected worker handoff before source artifact")
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
                summary="deterministic planner adapter worker result handoff",
            )
        elif action == "submit_approval_gated_action":
            pending = api.submit_action(
                run_id,
                {
                    "action": "call_tool",
                    "tool": "write_artifact_tool",
                    "text": "deterministic planner adapter final artifact",
                },
                requires_approval=True,
            )
        elif action == "bind_workspace":
            if pending is None:
                raise RuntimeError("planner selected workspace binding before approval action")
            workspace_binding = api.bind_workspace(run_id=run_id, decision=pending["decision"])
        elif action == "resolve_approval":
            pending_approvals = api.get_pending_approvals(run_id)
            approval_id = pending_approvals[0]["approval_id"] if pending_approvals else ""
            if not approval_id:
                raise RuntimeError("planner adapter spike did not request approval")
            resolution = api.resolve_approval(
                approval_id,
                {
                    "resolution": "approved",
                    "reason": "planner adapter friction review",
                    "resolver": "developer_demo",
                },
            )
        elif action == "verify_replay_checkpoint":
            continue
        else:
            raise ValueError(f"unsupported planner action: {action}")

    if source_setup is None or handoff is None or pending is None or resolution is None:
        raise RuntimeError("planner adapter did not complete the deterministic loop")

    events = api.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint_store = FileCheckpointStore(root / "agent-loop-planner-friction-checkpoints")
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
        "scenario": "agent-loop-planner-friction",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "planner_adapter_friction_ok": agent_loop_friction_ok,
        "planner_adapter_status": "deterministic_fixture",
        "planner_input_summary": planner_input_summary,
        "planner_decisions": planner_decisions,
        "planner_decision_count": len(planner_decisions),
        "agent_loop_friction_ok": agent_loop_friction_ok,
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
            "Introduce a fixture-backed planner fixture matrix with one intentionally blocked path; "
            "only reopen kernel mainline if that matrix produces non-empty kernel_friction."
        ),
    }


def _deterministic_planner_decisions(planner_input_summary: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = str(planner_input_summary["run_id"])
    return [
        {
            "step": 1,
            "action": "create_source_artifact",
            "target_run_id": run_id,
            "reason": "materialize deterministic planning input as a structured artifact ref",
        },
        {
            "step": 2,
            "action": "submit_worker_handoff",
            "target_run_id": run_id,
            "reason": "exercise delegated worker result handoff through a public helper",
        },
        {
            "step": 3,
            "action": "submit_approval_gated_action",
            "target_run_id": run_id,
            "reason": "force the loop through the approval pause boundary",
        },
        {
            "step": 4,
            "action": "bind_workspace",
            "target_run_id": run_id,
            "reason": "bind shared_ro workspace from existing policy grants before resume",
        },
        {
            "step": 5,
            "action": "resolve_approval",
            "target_run_id": run_id,
            "reason": "resume the pending action through the approval boundary",
        },
        {
            "step": 6,
            "action": "verify_replay_checkpoint",
            "target_run_id": run_id,
            "reason": "confirm the planner-driven loop remains canonical-event replayable",
        },
    ]


def _run_agent_loop_planner_matrix_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    happy = _run_agent_loop_planner_adapter_spike(root / "happy-path")
    blocked = _run_planner_blocked_deferred_fixture()
    malformed = _run_planner_malformed_action_fixture(root / "malformed-action")
    fixtures = [happy, blocked, malformed]
    app_deferred_friction = list(blocked["app_deferred_friction"])
    kernel_friction: list[dict[str, Any]] = []
    planner_matrix_ok = (
        happy["planner_adapter_friction_ok"] is True
        and blocked["status"] == "blocked_deferred"
        and malformed["status"] == "failed_closed"
        and malformed["partial_events_appended"] is False
        and kernel_friction == []
    )

    return {
        "scenario": "agent-loop-planner-matrix",
        "transport": "in_process",
        "planner_matrix_ok": planner_matrix_ok,
        "fixture_count": len(fixtures),
        "fixtures": [
            _planner_happy_fixture_summary(happy),
            blocked,
            malformed,
        ],
        "happy_path_ok": happy["planner_adapter_friction_ok"],
        "blocked_deferred_ok": blocked["status"] == "blocked_deferred",
        "malformed_fail_closed_ok": malformed["partial_events_appended"] is False,
        "kernel_friction": kernel_friction,
        "kernel_friction_count": len(kernel_friction),
        "app_deferred_friction": app_deferred_friction,
        "model_status": "not_used",
        "scheduler_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "filesystem_mutation_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "next_development_step": (
            "Add a branch-local fixture-backed planner runner API boundary only if the next app spike "
            "needs to reuse this matrix outside the demo entrypoint."
        ),
    }


def _run_agent_loop_planner_restart_pause_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "agent-loop-planner-restart-pause-checkpoints")
    api = InProcessServer(root, checkpoint_store=checkpoint_store)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="planner restart pause fixture")
    run_id = run["run_id"]
    planner_decisions_before_restart = [
        "create_source_artifact",
        "submit_worker_handoff",
        "submit_approval_gated_action",
    ]

    source_setup = api.create_source_artifact(
        run_id,
        summary="planner restart pause source summary",
        content="deterministic planner restart pause input",
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
        summary="deterministic planner restart pause worker result handoff",
    )
    pending = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "deterministic planner restart pause final artifact",
        },
        requires_approval=True,
    )
    pending_approvals = api.get_pending_approvals(run_id)
    approval_id = pending_approvals[0]["approval_id"] if pending_approvals else ""
    if not approval_id:
        raise RuntimeError("planner restart pause spike did not request approval")

    saved_before_restart = api.save_checkpoint_for_run(run_id)
    restarted = InProcessServer(root, checkpoint_store=checkpoint_store)
    state_after_restart = restarted.get_run_state(run_id)
    pending_after_restart = restarted.get_pending_approvals(run_id)
    planner_decisions_after_restart = [
        "get_pending_approvals",
        "resolve_approval",
        "verify_replay_checkpoint",
    ]
    resolution = restarted.resolve_approval(
        approval_id,
        {
            "resolution": "approved",
            "reason": "planner restart pause fixture",
            "resolver": "developer_demo",
        },
    )

    events = restarted.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, restarted.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, restarted.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        restarted.event_store,
        checkpoint_store,
    )
    final_state = restarted.get_run_state(run_id)
    event_types = [event.event_type for event in events]
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    private_append_required = handoff["private_append_required"] is not False
    approval_pending_before_restart = (
        pending["status"] == "pending_user_approval"
        and state_after_restart.status == "pending_user_approval"
        and bool(pending_after_restart)
    )
    restart_resume_ok = resolution["status"] == "completed" and replay_state.status == "completed"
    planner_restart_pause_ok = (
        source_setup["status"] == "completed"
        and handoff["status"] == "completed"
        and approval_pending_before_restart
        and restart_resume_ok
        and replay_ok
        and checkpoint_ok
        and private_append_required is False
    )

    return {
        "scenario": "agent-loop-planner-restart-pause",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "planner_restart_pause_ok": planner_restart_pause_ok,
        "planner_adapter_status": "deterministic_fixture",
        "planner_decisions_before_restart": planner_decisions_before_restart,
        "planner_decisions_after_restart": planner_decisions_after_restart,
        "approval_id": approval_id,
        "approval_pending_before_restart": approval_pending_before_restart,
        "restart_resume_ok": restart_resume_ok,
        "kernel_friction": [],
        "kernel_friction_count": 0,
        "private_append_required": private_append_required,
        "worker_handoff_ok": handoff["status"] == "completed",
        "approval_resume_ok": resolution["status"] == "completed",
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_before_restart_basis_event_id": saved_before_restart["basis_event_id"],
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
            "Pause branch-local agent-loop expansion unless a real app spike exposes a new gap."
        ),
    }


def _run_agent_loop_planner_io_validator_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="planner io validator fixture")
    run_id = run["run_id"]
    planner_input = _planner_io_validator_input(run_id)
    events_before = len(api.get_events(run_id))
    artifacts_before = len(api.artifact_store.list_artifacts(run_id))

    valid_result = _validate_planner_io_output(
        {
            "planner_run_id": "planner_run_001",
            "basis": {"run_id": run_id, "input_digest": "input_summary_hash"},
            "decisions": [
                {
                    "step": 1,
                    "action": "submit_approval_gated_action",
                    "requested_capability": "submit_approval_gated_action",
                    "reason": "need approval before writing final result",
                    "intent": {
                        "action": "call_tool",
                        "tool": "write_artifact_tool",
                        "text_summary": "write final review artifact",
                    },
                }
            ],
        },
        planner_input,
    )
    fixtures = [
        _planner_io_fixture(
            "malformed_output",
            ["not", "a", "planner", "object"],
            planner_input,
        ),
        _planner_io_fixture(
            "unknown_action",
            {
                "planner_run_id": "planner_run_002",
                "basis": {"run_id": run_id, "input_digest": "input_summary_hash"},
                "decisions": [
                    {
                        "step": 1,
                        "action": "unknown_symbolic_action",
                        "reason": "invalid action name",
                    }
                ],
            },
            planner_input,
        ),
        _planner_io_fixture(
            "overpowered_capability",
            {
                "planner_run_id": "planner_run_003",
                "basis": {"run_id": run_id, "input_digest": "input_summary_hash"},
                "decisions": [
                    {
                        "step": 1,
                        "action": "submit_approval_gated_action",
                        "requested_capability": "real_llm_plan",
                        "reason": "try to use a disabled capability",
                    }
                ],
            },
            planner_input,
        ),
        _planner_io_fixture(
            "full_content_without_grant",
            {
                "planner_run_id": "planner_run_004",
                "basis": {"run_id": run_id, "input_digest": "input_summary_hash"},
                "decisions": [
                    {
                        "step": 1,
                        "action": "create_source_artifact",
                        "requested_capability": "create_source_artifact",
                        "reason": "try to read more than the summary view",
                        "intent": {
                            "read_artifact_full_text": True,
                            "artifact_ref": {
                                "ref_type": "artifact",
                                "run_id": run_id,
                                "artifact_id": "artifact_999",
                                "scope": "run",
                            },
                        },
                    }
                ],
            },
            planner_input,
        ),
    ]
    events_after = len(api.get_events(run_id))
    artifacts_after = len(api.artifact_store.list_artifacts(run_id))
    rejected_fixture_count = sum(1 for fixture in fixtures if fixture["status"] == "rejected")
    planner_io_validator_ok = (
        valid_result["status"] == "accepted"
        and rejected_fixture_count == len(fixtures)
        and events_after == events_before
        and artifacts_after == artifacts_before
    )

    return {
        "scenario": "agent-loop-planner-io-validator",
        "session_id": session["session_id"],
        "run_id": run_id,
        "transport": "in_process",
        "planner_io_validator_ok": planner_io_validator_ok,
        "valid_output_accepted": valid_result["status"] == "accepted",
        "valid_decision_count": valid_result["decision_count"],
        "fixtures": fixtures,
        "rejected_fixture_count": rejected_fixture_count,
        "malformed_rejected": _fixture_rejected(fixtures, "malformed_output"),
        "unknown_action_rejected": _fixture_rejected(fixtures, "unknown_action"),
        "overpowered_rejected": _fixture_rejected(fixtures, "overpowered_capability"),
        "full_content_rejected": _fixture_rejected(fixtures, "full_content_without_grant"),
        "events_before_validation": events_before,
        "events_after_validation": events_after,
        "artifact_count_before_validation": artifacts_before,
        "artifact_count_after_validation": artifacts_after,
        "partial_events_appended": events_after != events_before,
        "artifact_created_during_validation": artifacts_after != artifacts_before,
        "kernel_friction": [],
        "kernel_friction_count": 0,
        "model_status": "not_used",
        "scheduler_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "filesystem_mutation_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "next_development_step": (
            "Wire this validator to a tiny demo-local runner before connecting a model provider."
        ),
    }


def _run_agent_loop_planner_validated_runner_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="planner validated runner fixture")
    run_id = run["run_id"]
    planner_input = _planner_io_validator_input(run_id)
    valid_output = _planner_validated_runner_output(run_id)
    validation = _validate_planner_io_output(valid_output, planner_input)
    if validation["status"] != "accepted":
        raise RuntimeError(f"valid planner fixture rejected: {validation['error_code']}")
    runner = _execute_validated_planner_decisions(api, run_id, valid_output["decisions"], root)

    invalid_api = InProcessServer(root / "invalid-plan")
    invalid_session = invalid_api.create_session()
    invalid_run = invalid_api.create_run(
        invalid_session["session_id"],
        goal="invalid planner validated runner fixture",
    )
    invalid_run_id = invalid_run["run_id"]
    invalid_input = _planner_io_validator_input(invalid_run_id)
    invalid_output = _planner_invalid_validated_runner_output(invalid_run_id)
    invalid_events_before = len(invalid_api.get_events(invalid_run_id))
    invalid_artifacts_before = len(invalid_api.artifact_store.list_artifacts(invalid_run_id))
    invalid_validation = _validate_planner_io_output(invalid_output, invalid_input)
    invalid_events_after = len(invalid_api.get_events(invalid_run_id))
    invalid_artifacts_after = len(invalid_api.artifact_store.list_artifacts(invalid_run_id))

    invalid_plan_blocked = invalid_validation["status"] == "rejected"
    invalid_plan_partial_events_appended = invalid_events_after != invalid_events_before
    invalid_plan_artifact_created = invalid_artifacts_after != invalid_artifacts_before
    planner_validated_runner_ok = (
        validation["status"] == "accepted"
        and runner["agent_loop_friction_ok"] is True
        and invalid_plan_blocked
        and invalid_plan_partial_events_appended is False
        and invalid_plan_artifact_created is False
    )

    return {
        "scenario": "agent-loop-planner-validated-runner",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": runner["run_status"],
        "transport": "in_process",
        "planner_validated_runner_ok": planner_validated_runner_ok,
        "validator_gate_passed": validation["status"] == "accepted",
        "valid_plan_executed": runner["agent_loop_friction_ok"],
        "valid_decision_count": validation["decision_count"],
        "planner_decisions": _planner_decision_summaries(valid_output["decisions"]),
        "invalid_plan_blocked": invalid_plan_blocked,
        "invalid_plan_error_code": invalid_validation["error_code"],
        "invalid_plan_events_before": invalid_events_before,
        "invalid_plan_events_after": invalid_events_after,
        "invalid_plan_artifacts_before": invalid_artifacts_before,
        "invalid_plan_artifacts_after": invalid_artifacts_after,
        "invalid_plan_partial_events_appended": invalid_plan_partial_events_appended,
        "invalid_plan_artifact_created": invalid_plan_artifact_created,
        "agent_loop_friction_ok": runner["agent_loop_friction_ok"],
        "kernel_friction": [],
        "kernel_friction_count": 0,
        "private_append_required": runner["private_append_required"],
        "worker_handoff_ok": runner["worker_handoff_ok"],
        "approval_pending_before_resume": runner["approval_pending_before_resume"],
        "approval_resume_ok": runner["approval_resume_ok"],
        "workspace_binding_ok": runner["workspace_binding_ok"],
        "replay_ok": runner["replay_ok"],
        "checkpoint_ok": runner["checkpoint_ok"],
        "checkpoint_basis_event_id": runner["checkpoint_basis_event_id"],
        "event_count": runner["event_count"],
        "event_types": runner["event_types"],
        "source_artifact_ref": runner["source_artifact_ref"],
        "worker_result_ref": runner["worker_result_ref"],
        "final_artifact_ref": runner["final_artifact_ref"],
        "model_status": "not_used",
        "scheduler_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "filesystem_mutation_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "next_development_step": (
            "Pause this artificial branch-local expansion and wait for real app-layer friction "
            "before connecting any model provider."
        ),
    }


def _planner_validated_runner_output(run_id: str) -> dict[str, Any]:
    decisions = _deterministic_planner_decisions(
        {
            "run_id": run_id,
            "run_status": "running",
            "available_public_helpers": [
                "create_source_artifact",
                "submit_worker_handoff",
                "submit_approval_gated_action",
                "bind_workspace",
                "resolve_approval",
                "verify_replay_checkpoint",
            ],
        }
    )
    return {
        "planner_run_id": "planner_run_validated_001",
        "basis": {"run_id": run_id, "input_digest": "input_summary_hash"},
        "decisions": [
            {
                **decision,
                "requested_capability": decision["action"],
            }
            for decision in decisions
        ],
    }


def _planner_invalid_validated_runner_output(run_id: str) -> dict[str, Any]:
    return {
        "planner_run_id": "planner_run_validated_bad_001",
        "basis": {"run_id": run_id, "input_digest": "input_summary_hash"},
        "decisions": [
            {
                "step": 1,
                "action": "submit_approval_gated_action",
                "requested_capability": "real_llm_plan",
                "reason": "try to bypass the validator before runner execution",
            }
        ],
    }


def _execute_validated_planner_decisions(
    api: InProcessServer,
    run_id: str,
    decisions: list[dict[str, Any]],
    root: Path,
) -> dict[str, Any]:
    source_setup: dict[str, Any] | None = None
    handoff: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None
    workspace_binding: dict[str, Any] = {}
    resolution: dict[str, Any] | None = None

    for decision in decisions:
        action = decision["action"]
        if action == "create_source_artifact":
            source_setup = api.create_source_artifact(
                run_id,
                summary="validated planner runner source summary",
                content="deterministic validated planner runner input",
            )
        elif action == "submit_worker_handoff":
            if source_setup is None:
                raise RuntimeError("validated runner selected handoff before source artifact")
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
                summary="deterministic validated planner runner worker result handoff",
            )
        elif action == "submit_approval_gated_action":
            pending = api.submit_action(
                run_id,
                {
                    "action": "call_tool",
                    "tool": "write_artifact_tool",
                    "text": "deterministic validated planner runner final artifact",
                },
                requires_approval=True,
            )
        elif action == "bind_workspace":
            if pending is None:
                raise RuntimeError("validated runner selected workspace binding before approval")
            workspace_binding = api.bind_workspace(run_id=run_id, decision=pending["decision"])
        elif action == "resolve_approval":
            pending_approvals = api.get_pending_approvals(run_id)
            approval_id = pending_approvals[0]["approval_id"] if pending_approvals else ""
            if not approval_id:
                raise RuntimeError("validated runner did not request approval")
            resolution = api.resolve_approval(
                approval_id,
                {
                    "resolution": "approved",
                    "reason": "planner validated runner fixture",
                    "resolver": "developer_demo",
                },
            )
        elif action == "verify_replay_checkpoint":
            continue
        else:
            raise ValueError(f"unsupported validated planner action: {action}")

    if source_setup is None or handoff is None or pending is None or resolution is None:
        raise RuntimeError("validated planner runner did not complete the deterministic loop")

    events = api.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint_store = FileCheckpointStore(root / "agent-loop-planner-validated-runner-checkpoints")
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
        "run_status": replay_state.status,
        "agent_loop_friction_ok": agent_loop_friction_ok,
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
    }


def _run_terminal_exec_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "terminal-exec-checkpoints")
    api = InProcessServer(root, checkpoint_store=checkpoint_store)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="controlled terminal execution demo")
    run_id = run["run_id"]
    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "terminal_exec",
            "argv": ["printf", "terminal-demo-output"],
        },
    )

    artifacts = api.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1]
    artifact_ref = artifact.ref.to_dict()
    terminal_output = json.loads(api.artifact_store.get_content(artifact.ref))
    events = api.get_events(run_id)
    event_types = [event.event_type for event in events]
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(run_id, api.event_store, checkpoint_store)
    final_state = api.get_run_state(run_id)
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    terminal_output_verified = (
        terminal_output.get("argv") == ["printf", "terminal-demo-output"]
        and terminal_output.get("exit_code") == 0
        and terminal_output.get("stdout") == "terminal-demo-output"
        and terminal_output.get("stderr") == ""
        and terminal_output.get("shell") is False
    )
    terminal_exec_ok = (
        result["status"] == "completed"
        and artifact.artifact_type == "terminal_output"
        and "action.started" in event_types
        and "artifact.created" in event_types
        and "action.completed" in event_types
        and replay_state.status == "completed"
        and terminal_output_verified
        and replay_ok
        and checkpoint_ok
    )

    return {
        "scenario": "terminal-exec",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "terminal_exec_ok": terminal_exec_ok,
        "terminal_command": "printf",
        "terminal_output_artifact_ref": artifact_ref,
        "terminal_artifact_summary": artifact.summary,
        "terminal_artifact_type": artifact.artifact_type,
        "terminal_output_verified": terminal_output_verified,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "interactive_shell_status": "not_used",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


class _DemoCompletedProcess:
    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _RecordingProcessRunner:
    def __init__(self, result: _DemoCompletedProcess) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> _DemoCompletedProcess:
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return self.result


class _DemoToolCallProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, responses: list[LLMToolCallResponse] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses) if responses is not None else [_demo_tool_call_response()]

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "max_tokens": max_tokens,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return _demo_tool_call_response()


class _DemoProductChatProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(
        self,
        responses: list[LLMToolCallResponse | LLMFinalAnswerResponse] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses) if responses is not None else [
            _demo_final_answer_response()
        ]

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse | LLMFinalAnswerResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "max_tokens": max_tokens,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return _demo_final_answer_response()


def _demo_tool_call_response(
    call_id: str = "call_demo_provider_route",
    prompt: str = "LLM_PROVIDER_DEMO_PROMPT_SHOULD_NOT_LEAK",
    summary: str = "provider-selected Codex demo",
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider=_DemoToolCallProvider.provider,
        model=_DemoToolCallProvider.model,
        finish_reason="tool_calls",
        usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={
                "prompt": prompt,
                "summary": summary,
            },
        ),
    )


def _demo_terminal_tool_call_response() -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="tool_calls",
        usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        tool_call=LLMToolCall(
            call_id="call_demo_terminal_tool",
            tool_name="terminal_exec",
            arguments={
                "argv": ["printf", "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK"],
                "summary": "provider-selected terminal command",
            },
        ),
    )


def _demo_final_answer_response() -> LLMFinalAnswerResponse:
    return LLMFinalAnswerResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="stop",
        usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        content="APP_ENTRY_DEMO_FINAL_ANSWER_SHOULD_NOT_LEAK",
    )


def _demo_terminal_final_answer_response() -> LLMFinalAnswerResponse:
    return LLMFinalAnswerResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="stop",
        usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        content="TERMINAL_TOOL_LOOP_FINAL_ANSWER_SHOULD_NOT_LEAK",
    )


def _demo_product_chat_ready_preflight() -> dict[str, Any]:
    return {
        "ready": True,
        "gate": "passed",
        "category": "ready",
        "status": "completed",
        "reason_code": "llm_product_chat_live_smoke_completed",
        "summary": "product-chat smoke completed direct answer, approval pause, and resume final answer",
        "next_step": "use this as a dev-only preflight before product-chat app entry",
    }


def _demo_product_chat_blocked_preflight() -> dict[str, Any]:
    return {
        "ready": False,
        "gate": "blocked",
        "category": "missing_configuration",
        "status": "missing_configuration",
        "reason_code": "llm_provider_not_configured",
        "summary": "LLM provider is not configured",
        "next_step": "configure provider credentials before product-chat app entry",
    }


def _run_model_tool_bridge_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "model-tool-bridge-checkpoints")
    runner = _RecordingProcessRunner(
        _DemoCompletedProcess(
            stdout='{"event":"task_complete","message":"MODEL_BRIDGE_OUTPUT_SHOULD_NOT_LEAK"}\n'
        )
    )
    app = create_codex_cli_http_app(
        root,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(root / "model-tool-workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=23,
            max_output_bytes=4096,
        ),
        checkpoint_store=checkpoint_store,
        process_runner=runner,
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="model tool bridge demo")
    run_id = run["run_id"]
    catalog = app.server.get_model_tool_catalog()
    catalog_tool_names = [
        tool["name"]
        for tool in catalog.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]

    pending = submit_model_tool_call(
        app,
        run_id,
        {
            "tool_name": "codex_task",
            "arguments": {
                "prompt": "MODEL_BRIDGE_PROMPT_SHOULD_NOT_LEAK",
                "summary": "model-selected Codex demo",
            },
        },
    )
    pending_event_types = [event.event_type for event in app.server.get_events(run_id)]
    approval_id = pending["approval_id"]
    approval_pending_before_execution = (
        pending["status"] == "pending_user_approval"
        and "approval.requested" in pending_event_types
        and not _ACTION_EXECUTION_EVENTS.intersection(pending_event_types)
        and runner.calls == []
    )

    resolve_response = app.request(
        "POST",
        f"/runs/{run_id}/approvals/{approval_id}/resolve",
        {
            "resolution": "approved",
            "reason": "model tool bridge demo",
            "resolver": "developer_demo",
        },
    )
    final_state = app.server.get_run_state(run_id)
    events = app.server.get_events(run_id)
    event_types = [event.event_type for event in events]
    artifacts = app.server.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1]
    transcript = json.loads(app.server.artifact_store.get_content(artifact.ref))

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    approval_ok = (
        resolve_response.status_code == 200
        and "approval.resolved" in event_types
        and event_types.index("approval.requested") < event_types.index("approval.resolved")
    )
    codex_started_after_approval = (
        len(runner.calls) == 1
        and "action.started" in event_types
        and event_types.index("approval.resolved") < event_types.index("action.started")
        and runner.calls[0]["kwargs"].get("shell") is False
    )
    codex_output_verified = (
        transcript.get("stdout")
        == '{"event":"task_complete","message":"MODEL_BRIDGE_OUTPUT_SHOULD_NOT_LEAK"}\n'
        and transcript.get("exit_code") == 0
        and transcript.get("shell") is False
    )
    model_tool_bridge_ok = (
        "codex_task" in catalog_tool_names
        and pending["tool_name"] == "codex_task"
        and approval_pending_before_execution
        and approval_ok
        and codex_started_after_approval
        and artifact.artifact_type == "codex_task_transcript"
        and codex_output_verified
        and replay_ok
        and checkpoint_ok
        and replay_state.status == "completed"
    )

    return {
        "scenario": "model-tool-bridge",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "model_tool_bridge_ok": model_tool_bridge_ok,
        "model_tool_name": "codex_task",
        "model_tool_result_status": pending["status"],
        "catalog_contains_codex_task": "codex_task" in catalog_tool_names,
        "catalog_tool_names": catalog_tool_names,
        "approval_pending_before_execution": approval_pending_before_execution,
        "approval_ok": approval_ok,
        "codex_started_after_approval": codex_started_after_approval,
        "codex_call_count": len(runner.calls),
        "codex_artifact_ref": artifact.ref.to_dict(),
        "codex_artifact_summary": artifact.summary,
        "codex_artifact_type": artifact.artifact_type,
        "codex_output_verified": codex_output_verified,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "model_status": "deterministic_decision_only",
        "real_llm_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _run_llm_provider_route_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "llm-provider-route-checkpoints")
    provider = _DemoToolCallProvider()
    runner = _RecordingProcessRunner(
        _DemoCompletedProcess(
            stdout='{"event":"task_complete","message":"LLM_PROVIDER_DEMO_OUTPUT_SHOULD_NOT_LEAK"}\n'
        )
    )
    app = create_llm_provider_http_app(
        root,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(root / "llm-provider-workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=23,
            max_output_bytes=4096,
        ),
        checkpoint_store=checkpoint_store,
        provider=provider,
        process_runner=runner,
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="llm provider route demo")
    run_id = run["run_id"]
    route = f"/runs/{run_id}/llm/tool-calls"
    request_body = {
        "messages": [
            {"role": "system", "content": "Select exactly one provided Isotope tool."},
            {
                "role": "user",
                "content": "Turn this request into a controlled Codex task. "
                "LLM_PROVIDER_DEMO_MESSAGE_SHOULD_NOT_LEAK",
            },
        ],
        "max_tokens": 96,
        "idempotency_key": "llm-provider-route-demo",
    }

    first_response = app.request("POST", route, request_body)
    second_response = app.request("POST", route, request_body)
    route_body = first_response.body if isinstance(first_response.body, dict) else {}
    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    provider_tools = [
        tool["name"]
        for call in provider.calls[:1]
        for tool in call.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    action_execution_started = bool(_ACTION_EXECUTION_EVENTS.intersection(event_types))
    approval_pending_before_execution = (
        first_response.status_code == 202
        and route_body.get("status") == "pending_user_approval"
        and "approval.requested" in event_types
        and not action_execution_started
        and runner.calls == []
    )
    idempotency_replay_ok = (
        second_response.status_code == first_response.status_code
        and second_response.body == first_response.body
        and len(provider.calls) == 1
        and event_types.count("approval.requested") == 1
    )
    provider_route_ok = (
        "codex_task" in provider_tools
        and route_body.get("tool_name") == "codex_task"
        and approval_pending_before_execution
        and idempotency_replay_ok
        and replay_ok
        and checkpoint_ok
    )

    return {
        "scenario": "llm-provider-route",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "provider_route_ok": provider_route_ok,
        "provider_name": provider.provider,
        "provider_model": provider.model,
        "provider_tool_name": route_body.get("tool_name"),
        "provider_call_count": len(provider.calls),
        "provider_seen_tool_names": provider_tools,
        "route_status_code": first_response.status_code,
        "route_result_status": route_body.get("status"),
        "provider_tool_call_id": route_body.get("provider_tool_call_id"),
        "approval_pending_before_execution": approval_pending_before_execution,
        "codex_started_before_approval": len(runner.calls) > 0,
        "codex_call_count": len(runner.calls),
        "idempotency_replay_ok": idempotency_replay_ok,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "real_llm_status": "fake_provider",
        "provider_status": "fake_tool_call",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _run_llm_tool_result_loop_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "llm-tool-result-loop-checkpoints")
    provider = _DemoToolCallProvider(
        [
            _demo_tool_call_response(),
            _demo_tool_call_response(
                "call_demo_followup_route",
                "LLM_TOOL_RESULT_FOLLOWUP_PROMPT_SHOULD_NOT_LEAK",
                "provider-selected follow-up Codex demo",
            ),
        ]
    )
    runner = _RecordingProcessRunner(
        _DemoCompletedProcess(
            stdout='{"event":"task_complete","message":"LLM_TOOL_RESULT_DEMO_OUTPUT_SHOULD_NOT_LEAK"}\n'
        )
    )
    app = create_llm_provider_http_app(
        root,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(root / "llm-tool-result-workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=23,
            max_output_bytes=4096,
        ),
        checkpoint_store=checkpoint_store,
        provider=provider,
        process_runner=runner,
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="llm tool result loop demo")
    run_id = run["run_id"]
    route = f"/runs/{run_id}/llm/tool-calls"
    request_body = {
        "messages": [
            {"role": "system", "content": "Select exactly one provided Isotope tool."},
            {
                "role": "user",
                "content": "Turn this request into a controlled Codex task. "
                "LLM_TOOL_RESULT_DEMO_MESSAGE_SHOULD_NOT_LEAK",
            },
        ],
        "max_tokens": 96,
        "idempotency_key": "llm-tool-result-loop-demo",
        "complete_run": False,
    }

    route_response = app.request("POST", route, request_body)
    route_body = route_response.body if isinstance(route_response.body, dict) else {}
    approval_id = route_body.get("approval_id")
    if isinstance(approval_id, str) and approval_id:
        approval_response = app.request(
            "POST",
            f"/runs/{run_id}/approvals/{approval_id}/resolve",
            {
                "resolution": "approved",
                "reason": "approve provider-selected Codex task for tool result demo",
                "resolver": "reviewer",
            },
        )
    else:
        approval_response = app.request("POST", f"/runs/{run_id}/approvals/missing/resolve", {})
    approval_body = approval_response.body if isinstance(approval_response.body, dict) else {}
    tool_result_message = build_llm_tool_result_message(route_body, approval_body)
    tool_result_content = json.loads(tool_result_message["content"])
    event_types_before_followup = [event.event_type for event in app.server.get_events(run_id)]
    first_run_status_after_approval = ""
    if isinstance(approval_body.get("run_state"), dict):
        first_run_status_after_approval = str(approval_body["run_state"].get("status", ""))
    followup = submit_llm_tool_result_followup(
        app,
        run_id,
        provider,
        request_body["messages"],
        route_body,
        approval_body,
        max_tokens=96,
    )
    event_types_after_followup = [event.event_type for event in app.server.get_events(run_id)]
    followup_action_submitted = event_types_after_followup != event_types_before_followup
    followup_tool_result = followup.get("tool_result") if isinstance(followup.get("tool_result"), dict) else {}
    followup_approval_id = followup_tool_result.get("approval_id")
    if isinstance(followup_approval_id, str) and followup_approval_id:
        second_approval_response = app.request(
            "POST",
            f"/runs/{run_id}/approvals/{followup_approval_id}/resolve",
            {
                "resolution": "approved",
                "reason": "approve follow-up provider-selected Codex task",
                "resolver": "reviewer",
            },
        )
    else:
        second_approval_response = app.request(
            "POST",
            f"/runs/{run_id}/approvals/missing-followup/resolve",
            {},
        )
    second_approval_body = (
        second_approval_response.body if isinstance(second_approval_response.body, dict) else {}
    )

    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    artifacts = app.server.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1] if artifacts else None
    transcripts = [
        json.loads(app.server.artifact_store.get_content(stored_artifact.ref))
        for stored_artifact in artifacts
    ]
    provider_tools = [
        tool["name"]
        for call in provider.calls[:1]
        for tool in call.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    approval_ok = (
        approval_response.status_code == 200
        and approval_body.get("tool_execution_status") == "completed"
        and first_run_status_after_approval == "running"
        and "approval.resolved" in event_types_before_followup
        and "run.completed" not in event_types_before_followup
    )
    codex_started_after_approval = (
        len(runner.calls) >= 1
        and "approval.resolved" in event_types_before_followup
        and "action.started" in event_types_before_followup
        and event_types_before_followup.index("approval.resolved")
        < event_types_before_followup.index("action.started")
    )
    artifact_ref = tool_result_content.get("artifact_ref")
    tool_result_message_ready = (
        tool_result_message.get("role") == "tool"
        and tool_result_message.get("tool_call_id") == route_body.get("provider_tool_call_id")
        and tool_result_message.get("name") == route_body.get("tool_name")
        and tool_result_content.get("status") == "completed"
        and artifact_ref == approval_body.get("artifact_ref")
        and "LLM_TOOL_RESULT_DEMO_OUTPUT_SHOULD_NOT_LEAK" not in repr(tool_result_message)
    )
    codex_output_verified = (
        len(transcripts) == 2
        and all(
            transcript.get("stdout")
            == '{"event":"task_complete","message":"LLM_TOOL_RESULT_DEMO_OUTPUT_SHOULD_NOT_LEAK"}\n'
            and transcript.get("exit_code") == 0
            for transcript in transcripts
        )
    )
    second_approval_ok = (
        second_approval_response.status_code == 200
        and second_approval_body.get("status") == "completed"
        and second_approval_body.get("tool_execution_status") == "completed"
        and isinstance(second_approval_body.get("artifact_ref"), dict)
    )
    second_codex_started_after_approval = (
        len(runner.calls) == 2
        and event_types_after_followup.count("action.started") == 1
        and event_types.count("action.started") == 2
        and event_types.count("approval.resolved") == 2
    )
    followup_submission_ok = (
        followup.get("status") == "pending_user_approval"
        and followup.get("provider_tool_call_id") == "call_demo_followup_route"
        and followup.get("tool_name") == "codex_task"
        and followup.get("submission_status") == "pending_user_approval"
        and followup.get("tool_result_status") == "completed"
        and followup.get("tool_result_artifact_ref") == artifact_ref
        and len(provider.calls) == 2
        and followup_action_submitted
        and event_types_after_followup.count("approval.requested") == 2
        and event_types_after_followup.count("action.started") == 1
        and "run.completed" not in event_types_after_followup
        and "LLM_TOOL_RESULT_FOLLOWUP_PROMPT_SHOULD_NOT_LEAK" not in repr(followup)
    )
    tool_result_loop_ok = (
        "codex_task" in provider_tools
        and route_body.get("tool_name") == "codex_task"
        and route_body.get("status") == "pending_user_approval"
        and approval_ok
        and codex_started_after_approval
        and codex_output_verified
        and tool_result_message_ready
        and followup_submission_ok
        and second_approval_ok
        and second_codex_started_after_approval
        and replay_ok
        and checkpoint_ok
        and replay_state.status == "completed"
        and event_types.count("run.completed") == 1
    )

    return {
        "scenario": "llm-tool-result-loop",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "tool_result_loop_ok": tool_result_loop_ok,
        "provider_name": provider.provider,
        "provider_model": provider.model,
        "provider_tool_name": route_body.get("tool_name"),
        "provider_call_count": len(provider.calls),
        "provider_seen_tool_names": provider_tools,
        "route_status_code": route_response.status_code,
        "route_result_status": route_body.get("status"),
        "provider_tool_call_id": route_body.get("provider_tool_call_id"),
        "approval_pending_before_execution": route_body.get("status") == "pending_user_approval",
        "approval_ok": approval_ok,
        "codex_started_after_approval": codex_started_after_approval,
        "codex_call_count": len(runner.calls),
        "codex_artifact_type": artifact.artifact_type if artifact is not None else "",
        "codex_output_verified": codex_output_verified,
        "tool_result_message_ready": tool_result_message_ready,
        "tool_result_message_role": tool_result_message.get("role"),
        "tool_result_message_tool_call_id": tool_result_message.get("tool_call_id"),
        "tool_result_content_status": tool_result_content.get("status"),
        "tool_result_artifact_ref": artifact_ref,
        "tool_result_artifact_ref_present": isinstance(artifact_ref, dict),
        "followup_provider_call_count": len(provider.calls),
        "followup_result_status": followup.get("status"),
        "followup_provider_tool_call_id": followup.get("provider_tool_call_id"),
        "followup_tool_name": followup.get("tool_name"),
        "followup_submission_status": followup.get("submission_status"),
        "followup_action_submitted": followup_action_submitted,
        "first_run_status_after_approval": first_run_status_after_approval,
        "second_approval_ok": second_approval_ok,
        "second_codex_started_after_approval": second_codex_started_after_approval,
        "tool_result_loop_status": "two_tool_actions_completed",
        "multi_tool_loop_status": "two_step_demo_only",
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "real_llm_status": "fake_provider",
        "provider_status": "fake_tool_call",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _run_llm_product_chat_app_entry_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "llm-product-chat-app-entry-checkpoints")
    provider = _DemoProductChatProvider()
    runner = _RecordingProcessRunner(
        _DemoCompletedProcess(
            stdout='{"event":"task_complete","message":"APP_ENTRY_DEMO_STDOUT_SHOULD_NOT_LEAK"}\n'
        )
    )
    app = create_llm_product_chat_http_app(
        root,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(root / "llm-product-chat-app-entry-workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=23,
            max_output_bytes=4096,
        ),
        checkpoint_store=checkpoint_store,
        provider=provider,
        process_runner=runner,
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="llm product chat app entry demo")
    run_id = run["run_id"]
    before_blocked_events = [event.event_type for event in app.server.get_events(run_id)]

    blocked_response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_demo_product_chat_blocked_preflight(),
        system_message="Use the product-chat app entry.",
        user_message="APP_ENTRY_DEMO_BLOCKED_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=64,
    )
    after_blocked_events = [event.event_type for event in app.server.get_events(run_id)]
    blocked_body = blocked_response.body if isinstance(blocked_response.body, dict) else {}
    blocked_no_side_effects = (
        blocked_response.status_code == 412
        and blocked_body.get("status") == "blocked_by_preflight"
        and provider.calls == []
        and runner.calls == []
        and after_blocked_events == before_blocked_events
    )

    ready_preflight = _demo_product_chat_ready_preflight()
    ready_response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=ready_preflight,
        system_message="Use the product-chat app entry.",
        user_message="APP_ENTRY_DEMO_READY_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=72,
    )
    ready_body = ready_response.body if isinstance(ready_response.body, dict) else {}

    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    provider_tools = [
        tool["name"]
        for call in provider.calls[:1]
        for tool in call.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]
    ready_forwarded_to_route = (
        ready_response.status_code == 200
        and ready_body.get("status") == "completed"
        and ready_body.get("provider_status") == "final_answer"
        and len(provider.calls) == 1
        and provider.calls[0].get("max_tokens") == 72
        and "codex_task" in provider_tools
        and runner.calls == []
        and "artifact.created" in event_types
        and "run.completed" in event_types
    )
    app_entry_preflight_ok = (
        blocked_no_side_effects
        and ready_preflight.get("ready") is True
        and ready_forwarded_to_route
        and replay_ok
        and checkpoint_ok
    )
    user_message_entry_ok = (
        ready_forwarded_to_route
        and len(provider.calls) == 1
        and provider.calls[0].get("messages")
        == [
            {"role": "system", "content": "Use the product-chat app entry."},
            {"role": "user", "content": "APP_ENTRY_DEMO_READY_MESSAGE_SHOULD_NOT_LEAK"},
        ]
    )

    return {
        "scenario": "llm-product-chat-app-entry",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "app_entry_preflight_ok": app_entry_preflight_ok,
        "user_message_entry_ok": user_message_entry_ok,
        "blocked_status_code": blocked_response.status_code,
        "blocked_result_status": blocked_body.get("status"),
        "blocked_no_side_effects": blocked_no_side_effects,
        "blocked_preflight_category": blocked_body.get("preflight", {}).get("category"),
        "ready_preflight_ready": ready_preflight.get("ready") is True,
        "ready_status_code": ready_response.status_code,
        "ready_result_status": ready_body.get("status"),
        "ready_provider_status": ready_body.get("provider_status"),
        "ready_forwarded_to_route": ready_forwarded_to_route,
        "assistant_message_present": isinstance(ready_body.get("assistant_message"), dict),
        "artifact_ref_present": isinstance(ready_body.get("artifact_ref"), dict),
        "provider_name": provider.provider,
        "provider_model": provider.model,
        "provider_seen_tool_names": provider_tools,
        "provider_call_count": len(provider.calls),
        "codex_call_count": len(runner.calls),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "real_llm_status": "fake_provider",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _run_llm_terminal_tool_loop_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "llm-terminal-tool-loop-checkpoints")
    server = InProcessServer(root, checkpoint_store=checkpoint_store)
    provider = _DemoProductChatProvider(
        [_demo_terminal_tool_call_response(), _demo_terminal_final_answer_response()]
    )
    app = HttpApiApp(
        root,
        server=server,
        enable_llm_product_chat_route=True,
        llm_tool_call_provider=provider,
        llm_tool_names=("terminal_exec",),
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="llm terminal tool loop demo")
    run_id = run["run_id"]
    route = f"/runs/{run_id}/llm/chat-turns"
    messages = [
        {"role": "system", "content": "Use the terminal tool when needed."},
        {
            "role": "user",
            "content": "Run the safe terminal check. TERMINAL_TOOL_LOOP_MESSAGE_SHOULD_NOT_LEAK",
        },
    ]

    first_response = app.request(
        "POST",
        route,
        {
            "messages": messages,
            "max_tokens": 96,
            "complete_run": False,
        },
    )
    first_body = first_response.body if isinstance(first_response.body, dict) else {}
    tool_result_message = build_llm_tool_result_message(first_body, first_body)
    tool_result_content = json.loads(tool_result_message["content"])
    first_artifacts = app.server.artifact_store.list_artifacts(run_id)
    terminal_artifact = first_artifacts[-1] if first_artifacts else None
    terminal_content = (
        json.loads(app.server.artifact_store.get_content(terminal_artifact.ref))
        if terminal_artifact is not None
        else {}
    )

    second_response = app.request(
        "POST",
        route,
        {
            "messages": messages,
            "llm_result": first_body,
            "tool_execution_result": first_body,
            "max_tokens": 96,
        },
    )
    second_body = second_response.body if isinstance(second_response.body, dict) else {}
    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    provider_tools = [
        tool["name"]
        for call in provider.calls[:1]
        for tool in call.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]
    artifact_ref = tool_result_content.get("artifact_ref")
    terminal_output_verified = (
        terminal_content.get("stdout") == "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK"
        and terminal_content.get("shell") is False
        and terminal_content.get("exit_code") == 0
    )
    tool_result_message_ready = (
        tool_result_message.get("role") == "tool"
        and tool_result_message.get("tool_call_id") == first_body.get("provider_tool_call_id")
        and tool_result_message.get("name") == "terminal_exec"
        and tool_result_content.get("status") == "completed"
        and isinstance(artifact_ref, dict)
        and "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK" not in repr(tool_result_message)
    )
    terminal_tool_loop_ok = (
        first_response.status_code == 200
        and first_body.get("status") == "running"
        and first_body.get("tool_name") == "terminal_exec"
        and first_body.get("tool_execution_status") == "completed"
        and second_response.status_code == 200
        and second_body.get("status") == "completed"
        and second_body.get("provider_status") == "final_answer"
        and provider_tools == ["terminal_exec"]
        and len(provider.calls) == 2
        and terminal_output_verified
        and tool_result_message_ready
        and event_types.count("approval.requested") == 0
        and event_types.count("action.started") == 2
        and event_types.count("run.completed") == 1
        and replay_ok
        and checkpoint_ok
    )

    return {
        "scenario": "llm-terminal-tool-loop",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "terminal_tool_loop_ok": terminal_tool_loop_ok,
        "provider_name": provider.provider,
        "provider_model": provider.model,
        "provider_tool_name": first_body.get("tool_name"),
        "provider_seen_tool_names": provider_tools,
        "provider_call_count": len(provider.calls),
        "terminal_command": "printf",
        "terminal_action_status": first_body.get("tool_execution_status"),
        "terminal_output_verified": terminal_output_verified,
        "tool_result_message_ready": tool_result_message_ready,
        "tool_result_message_role": tool_result_message.get("role"),
        "tool_result_message_tool_call_id": tool_result_message.get("tool_call_id"),
        "tool_result_content_status": tool_result_content.get("status"),
        "tool_result_artifact_ref": artifact_ref,
        "tool_result_artifact_ref_present": isinstance(artifact_ref, dict),
        "final_answer_status": second_body.get("status"),
        "final_answer_artifact_ref_present": isinstance(second_body.get("artifact_ref"), dict),
        "codex_call_count": 0,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "real_llm_status": "fake_provider",
        "provider_status": "fake_tool_call",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _planner_decision_summaries(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "step": decision["step"],
            "action": decision["action"],
            "requested_capability": decision.get("requested_capability", decision["action"]),
            "reason": decision["reason"],
        }
        for decision in decisions
    ]


def _planner_io_validator_input(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "input_digest": "input_summary_hash",
        "available_capabilities": [
            "create_source_artifact",
            "submit_worker_handoff",
            "submit_approval_gated_action",
            "get_pending_approvals",
            "resolve_approval",
            "bind_workspace",
            "verify_replay_checkpoint",
        ],
        "deferred_capabilities": [
            "real_llm_plan",
            "scheduler",
            "provider_adapter",
            "filesystem_mutation",
            "memory_query",
        ],
        "retrieval_grants": {"artifact_summary": True, "artifact_full_text": False},
    }


def _planner_io_fixture(
    fixture_id: str,
    planner_output: object,
    planner_input: dict[str, Any],
) -> dict[str, Any]:
    result = _validate_planner_io_output(planner_output, planner_input)
    return {
        "fixture_id": fixture_id,
        "status": result["status"],
        "error_code": result["error_code"],
        "decision_count": result["decision_count"],
    }


def _fixture_rejected(fixtures: list[dict[str, Any]], fixture_id: str) -> bool:
    return any(
        fixture["fixture_id"] == fixture_id and fixture["status"] == "rejected"
        for fixture in fixtures
    )


def _validate_planner_io_output(
    planner_output: object,
    planner_input: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(planner_output, dict):
        return _planner_rejection("planner_output_malformed")
    if not _non_empty_string(planner_output.get("planner_run_id")):
        return _planner_rejection("planner_output_malformed")
    basis = planner_output.get("basis")
    if not isinstance(basis, dict):
        return _planner_rejection("planner_output_malformed")
    if basis.get("run_id") != planner_input.get("run_id"):
        return _planner_rejection("planner_basis_mismatch")
    if basis.get("input_digest") != planner_input.get("input_digest"):
        return _planner_rejection("planner_basis_mismatch")
    decisions = planner_output.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return _planner_rejection("planner_output_malformed")

    available_capabilities = set(planner_input.get("available_capabilities", []))
    allowed_actions = set(planner_input.get("available_capabilities", []))
    for decision in decisions:
        if not isinstance(decision, dict):
            return _planner_rejection("planner_output_malformed")
        if not isinstance(decision.get("step"), int):
            return _planner_rejection("planner_output_malformed")
        action = decision.get("action")
        if not _non_empty_string(action):
            return _planner_rejection("planner_output_malformed")
        if action not in allowed_actions:
            return _planner_rejection("unknown_planner_action")
        if not _non_empty_string(decision.get("reason")):
            return _planner_rejection("planner_output_malformed")
        intent = decision.get("intent", {})
        if intent is not None and not isinstance(intent, dict):
            return _planner_rejection("planner_output_malformed")
        if isinstance(intent, dict):
            if intent.get("read_artifact_full_text") is True:
                grants = planner_input.get("retrieval_grants", {})
                if not isinstance(grants, dict) or grants.get("artifact_full_text") is not True:
                    return _planner_rejection("artifact_full_content_not_granted")
            if any(
                intent.get(key) is True
                for key in (
                    "direct_append_event",
                    "write_checkpoint",
                    "mutate_artifact_store",
                    "private_server_state",
                )
            ):
                return _planner_rejection("planner_private_state_forbidden")
        requested_capability = decision.get("requested_capability", action)
        if requested_capability not in available_capabilities:
            return _planner_rejection("planner_capability_not_allowed")

    return {
        "status": "accepted",
        "error_code": "",
        "decision_count": len(decisions),
    }


def _planner_rejection(error_code: str) -> dict[str, Any]:
    return {"status": "rejected", "error_code": error_code, "decision_count": 0}


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _planner_happy_fixture_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": "happy_path",
        "status": "ok",
        "session_id": result["session_id"],
        "run_id": result["run_id"],
        "planner_adapter_status": result["planner_adapter_status"],
        "planner_decision_count": result["planner_decision_count"],
        "private_append_required": result["private_append_required"],
        "kernel_friction": list(result["kernel_friction"]),
        "replay_ok": result["replay_ok"],
        "checkpoint_ok": result["checkpoint_ok"],
        "event_count": result["event_count"],
    }


def _run_planner_blocked_deferred_fixture() -> dict[str, Any]:
    return {
        "fixture_id": "blocked_deferred_capability",
        "status": "blocked_deferred",
        "blocked_capability": "real_llm_plan",
        "reason": "real LLM planning is product/app-layer deferred and is not a kernel implementation request",
        "app_deferred_friction": [
            {
                "kind": "deferred_capability",
                "capability": "real_llm_plan",
                "classification": "app_or_product_deferred",
            }
        ],
        "kernel_friction": [],
        "partial_events_appended": False,
    }


def _run_planner_malformed_action_fixture(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="malformed planner action fixture")
    run_id = run["run_id"]
    before_count = len(api.get_events(run_id))
    unknown_action = "unknown_symbolic_action"
    status = "failed_closed"
    error_code = ""
    try:
        _validate_planner_symbolic_action(unknown_action)
    except ValueError as exc:
        error_code = "unknown_symbolic_action"
        error_message = str(exc)
    else:
        status = "unexpected_success"
        error_message = ""
    after_count = len(api.get_events(run_id))

    return {
        "fixture_id": "malformed_symbolic_action",
        "status": status,
        "unknown_action": unknown_action,
        "error_code": error_code,
        "error_summary": error_message,
        "events_before": before_count,
        "events_after": after_count,
        "partial_events_appended": after_count != before_count,
        "kernel_friction": [],
    }


def _validate_planner_symbolic_action(action: str) -> None:
    allowed = {
        "create_source_artifact",
        "submit_worker_handoff",
        "submit_approval_gated_action",
        "bind_workspace",
        "resolve_approval",
        "verify_replay_checkpoint",
    }
    if action not in allowed:
        raise ValueError(f"unknown planner symbolic action: {action}")


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
    if result.get("scenario") == "agent-loop-planner-validated-runner":
        return _format_agent_loop_planner_validated_runner_plain_text(result)
    if result.get("scenario") == "agent-loop-planner-io-validator":
        return _format_agent_loop_planner_io_validator_plain_text(result)
    if result.get("scenario") == "agent-loop-planner-restart-pause":
        return _format_agent_loop_planner_restart_pause_plain_text(result)
    if result.get("scenario") == "agent-loop-planner-matrix":
        return _format_agent_loop_planner_matrix_plain_text(result)
    if result.get("scenario") == "agent-loop-planner-friction":
        return _format_agent_loop_planner_friction_plain_text(result)
    if result.get("scenario") == "agent-loop-friction":
        return _format_agent_loop_friction_plain_text(result)
    if result.get("scenario") == "external-snapshot-review":
        return _format_external_snapshot_review_plain_text(result)
    if result.get("scenario") == "artifact-review":
        return _format_artifact_review_plain_text(result)
    if result.get("scenario") == "approval-tool-runner":
        return _format_approval_tool_runner_plain_text(result)
    if result.get("scenario") == "terminal-exec":
        return _format_terminal_exec_plain_text(result)
    if result.get("scenario") == "model-tool-bridge":
        return _format_model_tool_bridge_plain_text(result)
    if result.get("scenario") == "llm-provider-route":
        return _format_llm_provider_route_plain_text(result)
    if result.get("scenario") == "llm-tool-result-loop":
        return _format_llm_tool_result_loop_plain_text(result)
    if result.get("scenario") == "llm-product-chat-app-entry":
        return _format_llm_product_chat_app_entry_plain_text(result)
    if result.get("scenario") == "llm-terminal-tool-loop":
        return _format_llm_terminal_tool_loop_plain_text(result)
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
    if scenario == "agent-loop-planner-validated-runner":
        return _format_agent_loop_planner_validated_runner_trace(result)
    if scenario == "agent-loop-planner-io-validator":
        return _format_agent_loop_planner_io_validator_trace(result)
    if scenario == "agent-loop-planner-restart-pause":
        return _format_agent_loop_planner_restart_pause_trace(result)
    if scenario == "agent-loop-planner-matrix":
        return _format_agent_loop_planner_matrix_trace(result)
    if scenario == "agent-loop-planner-friction":
        return _format_agent_loop_planner_friction_trace(result)
    if scenario == "agent-loop-friction":
        return _format_agent_loop_friction_trace(result)
    if scenario == "external-snapshot-review":
        return _format_external_snapshot_review_trace(result)
    if scenario == "artifact-review":
        return _format_artifact_review_trace(result)
    if scenario == "approval-tool-runner":
        return _format_approval_tool_runner_trace(result)
    if scenario == "terminal-exec":
        return _format_terminal_exec_trace(result)
    if scenario == "model-tool-bridge":
        return _format_model_tool_bridge_trace(result)
    if scenario == "llm-provider-route":
        return _format_llm_provider_route_trace(result)
    if scenario == "llm-tool-result-loop":
        return _format_llm_tool_result_loop_trace(result)
    if scenario == "llm-product-chat-app-entry":
        return _format_llm_product_chat_app_entry_trace(result)
    if scenario == "llm-terminal-tool-loop":
        return _format_llm_terminal_tool_loop_trace(result)
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


def _format_agent_loop_planner_friction_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        f"planner adapter status: {result['planner_adapter_status']}",
    ]
    steps.extend(
        f"planner selected symbolic step {decision['step']}: {decision['action']}"
        for decision in result["planner_decisions"]
    )
    steps.extend(
        [
            f"policy-gated approval pause/resume verified: {_bool_text(result['approval_resume_ok'])}",
            f"kernel friction count: {result['kernel_friction_count']}",
            f"private append required: {_bool_text(result['private_append_required'])}",
            f"replay verified: {_bool_text(result['replay_ok'])}",
            f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
            f"next development step: {result['next_development_step']}",
        ]
    )
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_matrix_trace(result: dict[str, Any]) -> str:
    fixtures = {fixture["fixture_id"]: fixture for fixture in result["fixtures"]}
    happy = fixtures["happy_path"]
    blocked = fixtures["blocked_deferred_capability"]
    malformed = fixtures["malformed_symbolic_action"]
    steps = [
        f"happy_path session/run: {happy['session_id']} / {happy['run_id']}",
        f"fixture happy_path action/policy/artifact path: {happy['status']}",
        f"happy_path replay verified: {_bool_text(happy['replay_ok'])}",
        f"happy_path checkpoint verified: {_bool_text(happy['checkpoint_ok'])}",
        f"fixture blocked_deferred_capability: {blocked['blocked_capability']}",
        "blocked_deferred_capability classified as app_or_product_deferred",
        f"fixture malformed_symbolic_action: {malformed['status']}",
        f"malformed_symbolic_action partial events appended: {_bool_text(malformed['partial_events_appended'])}",
        f"kernel friction count: {result['kernel_friction_count']}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_restart_pause_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "planner creates source artifact and worker handoff",
        "planner submits policy-gated action and pause at approval",
        f"approval pending before restart: {_bool_text(result['approval_pending_before_restart'])}",
        "restart server with the same event log and checkpoint store",
        "planner reads pending approval after restart",
        f"resume approval action after restart: {_bool_text(result['restart_resume_ok'])}",
        f"final artifact ref created: {_artifact_id(result['final_artifact_ref'])}",
        f"kernel friction count: {result['kernel_friction_count']}",
        f"private append required: {_bool_text(result['private_append_required'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_io_validator_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "policy capability list loaded for planner validation",
        f"accept valid planner output: {_bool_text(result['valid_output_accepted'])}",
    ]
    steps.extend(
        f"reject {fixture['fixture_id']}: {fixture['error_code']}"
        for fixture in result["fixtures"]
    )
    steps.extend(
        [
            f"partial events appended: {_bool_text(result['partial_events_appended'])}",
            "artifact full text request denied without grant",
            "replay state unchanged because validator does not execute actions",
            "checkpoint state unchanged because validator does not write checkpoints",
            f"kernel friction count: {result['kernel_friction_count']}",
            f"model status: {result['model_status']}",
            f"next development step: {result['next_development_step']}",
        ]
    )
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_validated_runner_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "policy capability list loaded before runner execution",
        f"validate planner output: {_bool_text(result['validator_gate_passed'])}",
    ]
    steps.extend(
        f"execute validated step {decision['step']}: {decision['action']}"
        for decision in result["planner_decisions"]
    )
    steps.extend(
        [
            f"valid plan executed: {_bool_text(result['valid_plan_executed'])}",
            f"block invalid planner output: {result['invalid_plan_error_code']}",
            (
                "invalid plan partial events appended: "
                f"{_bool_text(result['invalid_plan_partial_events_appended'])}"
            ),
            f"kernel friction count: {result['kernel_friction_count']}",
            f"private append required: {_bool_text(result['private_append_required'])}",
            f"replay verified: {_bool_text(result['replay_ok'])}",
            f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
            f"model status: {result['model_status']}",
            f"next development step: {result['next_development_step']}",
        ]
    )
    return _format_trace_steps(result["scenario"], steps)


def _format_terminal_exec_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        f"propose action terminal_exec argv-only command: {result['terminal_command']}",
        "policy grants terminal_exec with shell=false command profile",
        f"execute command and capture terminal_output artifact: {_artifact_id(result['terminal_output_artifact_ref'])}",
        f"terminal output verified internally: {_bool_text(result['terminal_output_verified'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"interactive shell remains: {result['interactive_shell_status']}",
        f"memory query remains: {result['memory_query_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_model_tool_bridge_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        f"读取 model-facing tool catalog: codex_task={_bool_text(result['catalog_contains_codex_task'])}",
        f"固定 model selected codex_task action: {result['model_tool_result_status']}",
        f"bridge 提交 pending approval: {_bool_text(result['approval_pending_before_execution'])}",
        "policy 让 Codex 保持暂停，直到 approval",
        f"approval resolved as approved: {_bool_text(result['approval_ok'])}",
        f"Codex CLI backend called after approval: {_bool_text(result['codex_started_after_approval'])}",
        f"记录 artifact: {_artifact_id(result['codex_artifact_ref'])}",
        f"replay 验证: {_bool_text(result['replay_ok'])}",
        f"checkpoint 验证: {_bool_text(result['checkpoint_ok'])}",
        f"real LLM 仍然是: {result['real_llm_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_llm_provider_route_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        "application sends user request through provider route",
        f"provider route exposes codex_task only: {result['provider_seen_tool_names']}",
        f"fake provider selected codex_task: {result['route_result_status']}",
        f"policy returns pending approval: {_bool_text(result['approval_pending_before_execution'])}",
        f"action execution / Codex remains paused before approval: {_bool_text(not result['codex_started_before_approval'])}",
        "no artifact before approval",
        f"idempotency replay verified: {_bool_text(result['idempotency_replay_ok'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"network listener remains: {result['network_listener_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_llm_tool_result_loop_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        "application sends user request through provider route",
        f"provider route exposes codex_task only: {result['provider_seen_tool_names']}",
        f"fake provider selected codex_task: {result['route_result_status']}",
        "policy returns pending approval before action execution",
        f"approval resolved as approved: {_bool_text(result['approval_ok'])}",
        f"Codex CLI backend called after approval: {_bool_text(result['codex_started_after_approval'])}",
        f"artifact ref recorded for model handoff: {_artifact_id(result['tool_result_artifact_ref'])}",
        f"tool result message prepared: {_bool_text(result['tool_result_message_ready'])}",
        f"first approval left run open: {result['first_run_status_after_approval']}",
        f"follow-up model choice submitted for approval: {result['followup_provider_tool_call_id']}",
        f"second approval completed run: {_bool_text(result['second_approval_ok'])}",
        "artifact ref only; no transcript or terminal stdout is included",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"two-step demo status: {result['multi_tool_loop_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_llm_product_chat_app_entry_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        "preflight blocked before product-chat route",
        f"blocked response without action side effects: {_bool_text(result['blocked_no_side_effects'])}",
        "no provider call, no Codex call, no artifact while blocked",
        "preflight ready after developer smoke gate",
        f"user message accepted by app entry: {_bool_text(result['user_message_entry_ok'])}",
        f"forwarded to product-chat route: {_bool_text(result['ready_forwarded_to_route'])}",
        "policy accepted final-answer write through existing action chain",
        f"final answer artifact recorded: {_bool_text(result['artifact_ref_present'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"no real network listener: {result['network_listener_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_llm_terminal_tool_loop_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        f"provider sees terminal_exec only: {result['provider_seen_tool_names']}",
        f"fake provider selected terminal_exec: {result['provider_tool_name']}",
        "policy validates terminal command allowlist before execution",
        f"terminal_exec runs through submit_action: {result['terminal_action_status']}",
        f"terminal output captured as artifact ref: {_artifact_id(result['tool_result_artifact_ref'])}",
        f"safe tool-result message prepared: {_bool_text(result['tool_result_message_ready'])}",
        "provider receives status / execution id / artifact ref only",
        f"final answer artifact recorded: {_bool_text(result['final_answer_artifact_ref_present'])}",
        f"codex_call_count remains 0: {result['codex_call_count']}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
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


def _format_agent_loop_planner_friction_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"planner_adapter_friction_ok: {str(result['planner_adapter_friction_ok']).lower()}",
        f"planner_adapter_status: {result['planner_adapter_status']}",
        f"planner_decision_count: {result['planner_decision_count']}",
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


def _format_agent_loop_planner_matrix_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"transport: {result['transport']}",
        f"planner_matrix_ok: {str(result['planner_matrix_ok']).lower()}",
        f"fixture_count: {result['fixture_count']}",
        f"happy_path_ok: {str(result['happy_path_ok']).lower()}",
        f"blocked_deferred_ok: {str(result['blocked_deferred_ok']).lower()}",
        f"malformed_fail_closed_ok: {str(result['malformed_fail_closed_ok']).lower()}",
        f"kernel_friction_count: {result['kernel_friction_count']}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)


def _format_agent_loop_planner_restart_pause_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"planner_restart_pause_ok: {str(result['planner_restart_pause_ok']).lower()}",
        f"approval_pending_before_restart: {str(result['approval_pending_before_restart']).lower()}",
        f"restart_resume_ok: {str(result['restart_resume_ok']).lower()}",
        f"private_append_required: {str(result['private_append_required']).lower()}",
        f"kernel_friction_count: {result['kernel_friction_count']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)


def _format_agent_loop_planner_io_validator_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"transport: {result['transport']}",
        f"planner_io_validator_ok: {str(result['planner_io_validator_ok']).lower()}",
        f"valid_output_accepted: {str(result['valid_output_accepted']).lower()}",
        f"malformed_rejected: {str(result['malformed_rejected']).lower()}",
        f"unknown_action_rejected: {str(result['unknown_action_rejected']).lower()}",
        f"overpowered_rejected: {str(result['overpowered_rejected']).lower()}",
        f"full_content_rejected: {str(result['full_content_rejected']).lower()}",
        f"partial_events_appended: {str(result['partial_events_appended']).lower()}",
        f"kernel_friction_count: {result['kernel_friction_count']}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)


def _format_agent_loop_planner_validated_runner_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"planner_validated_runner_ok: {str(result['planner_validated_runner_ok']).lower()}",
        f"validator_gate_passed: {str(result['validator_gate_passed']).lower()}",
        f"valid_plan_executed: {str(result['valid_plan_executed']).lower()}",
        f"invalid_plan_blocked: {str(result['invalid_plan_blocked']).lower()}",
        (
            "invalid_plan_partial_events_appended: "
            f"{str(result['invalid_plan_partial_events_appended']).lower()}"
        ),
        f"agent_loop_friction_ok: {str(result['agent_loop_friction_ok']).lower()}",
        f"private_append_required: {str(result['private_append_required']).lower()}",
        f"kernel_friction_count: {result['kernel_friction_count']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)


def _format_terminal_exec_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"terminal_exec_ok: {str(result['terminal_exec_ok']).lower()}",
        f"terminal_command: {result['terminal_command']}",
        f"terminal_artifact_type: {result['terminal_artifact_type']}",
        f"terminal_output_verified: {str(result['terminal_output_verified']).lower()}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"interactive_shell_status: {result['interactive_shell_status']}",
        f"network_listener_status: {result['network_listener_status']}",
        f"model_status: {result['model_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_model_tool_bridge_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"model_tool_bridge_ok: {str(result['model_tool_bridge_ok']).lower()}",
        f"model_tool_name: {result['model_tool_name']}",
        f"model_tool_result_status: {result['model_tool_result_status']}",
        f"approval_pending_before_execution: {str(result['approval_pending_before_execution']).lower()}",
        f"approval_ok: {str(result['approval_ok']).lower()}",
        f"codex_started_after_approval: {str(result['codex_started_after_approval']).lower()}",
        f"codex_call_count: {result['codex_call_count']}",
        f"codex_artifact_type: {result['codex_artifact_type']}",
        f"codex_output_verified: {str(result['codex_output_verified']).lower()}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"real_llm_status: {result['real_llm_status']}",
        f"provider_status: {result['provider_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_llm_provider_route_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"provider_route_ok: {str(result['provider_route_ok']).lower()}",
        f"provider_name: {result['provider_name']}",
        f"provider_model: {result['provider_model']}",
        f"provider_tool_name: {result['provider_tool_name']}",
        f"provider_call_count: {result['provider_call_count']}",
        f"route_result_status: {result['route_result_status']}",
        f"approval_pending_before_execution: {str(result['approval_pending_before_execution']).lower()}",
        f"codex_started_before_approval: {str(result['codex_started_before_approval']).lower()}",
        f"codex_call_count: {result['codex_call_count']}",
        f"idempotency_replay_ok: {str(result['idempotency_replay_ok']).lower()}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"real_llm_status: {result['real_llm_status']}",
        f"provider_status: {result['provider_status']}",
        f"network_listener_status: {result['network_listener_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_llm_tool_result_loop_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"tool_result_loop_ok: {str(result['tool_result_loop_ok']).lower()}",
        f"provider_name: {result['provider_name']}",
        f"provider_model: {result['provider_model']}",
        f"provider_tool_name: {result['provider_tool_name']}",
        f"provider_call_count: {result['provider_call_count']}",
        f"route_result_status: {result['route_result_status']}",
        f"approval_ok: {str(result['approval_ok']).lower()}",
        f"codex_started_after_approval: {str(result['codex_started_after_approval']).lower()}",
        f"codex_call_count: {result['codex_call_count']}",
        f"tool_result_message_ready: {str(result['tool_result_message_ready']).lower()}",
        f"tool_result_message_role: {result['tool_result_message_role']}",
        f"tool_result_message_tool_call_id: {result['tool_result_message_tool_call_id']}",
        f"tool_result_content_status: {result['tool_result_content_status']}",
        f"tool_result_artifact_ref_present: {str(result['tool_result_artifact_ref_present']).lower()}",
        f"followup_provider_call_count: {result['followup_provider_call_count']}",
        f"followup_result_status: {result['followup_result_status']}",
        f"followup_provider_tool_call_id: {result['followup_provider_tool_call_id']}",
        f"followup_tool_name: {result['followup_tool_name']}",
        f"followup_submission_status: {result['followup_submission_status']}",
        f"followup_action_submitted: {str(result['followup_action_submitted']).lower()}",
        f"first_run_status_after_approval: {result['first_run_status_after_approval']}",
        f"second_approval_ok: {str(result['second_approval_ok']).lower()}",
        f"second_codex_started_after_approval: {str(result['second_codex_started_after_approval']).lower()}",
        f"tool_result_loop_status: {result['tool_result_loop_status']}",
        f"multi_tool_loop_status: {result['multi_tool_loop_status']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"real_llm_status: {result['real_llm_status']}",
        f"provider_status: {result['provider_status']}",
        f"network_listener_status: {result['network_listener_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_llm_product_chat_app_entry_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"app_entry_preflight_ok: {str(result['app_entry_preflight_ok']).lower()}",
        f"user_message_entry_ok: {str(result['user_message_entry_ok']).lower()}",
        f"blocked_status_code: {result['blocked_status_code']}",
        f"blocked_result_status: {result['blocked_result_status']}",
        f"blocked_no_side_effects: {str(result['blocked_no_side_effects']).lower()}",
        f"ready_preflight_ready: {str(result['ready_preflight_ready']).lower()}",
        f"ready_status_code: {result['ready_status_code']}",
        f"ready_result_status: {result['ready_result_status']}",
        f"ready_forwarded_to_route: {str(result['ready_forwarded_to_route']).lower()}",
        f"assistant_message_present: {str(result['assistant_message_present']).lower()}",
        f"artifact_ref_present: {str(result['artifact_ref_present']).lower()}",
        f"provider_name: {result['provider_name']}",
        f"provider_model: {result['provider_model']}",
        f"provider_call_count: {result['provider_call_count']}",
        f"codex_call_count: {result['codex_call_count']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"real_llm_status: {result['real_llm_status']}",
        f"network_listener_status: {result['network_listener_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_llm_terminal_tool_loop_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"terminal_tool_loop_ok: {str(result['terminal_tool_loop_ok']).lower()}",
        f"provider_name: {result['provider_name']}",
        f"provider_model: {result['provider_model']}",
        f"provider_tool_name: {result['provider_tool_name']}",
        f"provider_call_count: {result['provider_call_count']}",
        f"terminal_command: {result['terminal_command']}",
        f"terminal_action_status: {result['terminal_action_status']}",
        f"terminal_output_verified: {str(result['terminal_output_verified']).lower()}",
        f"tool_result_message_ready: {str(result['tool_result_message_ready']).lower()}",
        f"tool_result_message_role: {result['tool_result_message_role']}",
        f"tool_result_message_tool_call_id: {result['tool_result_message_tool_call_id']}",
        f"tool_result_content_status: {result['tool_result_content_status']}",
        f"tool_result_artifact_ref_present: {str(result['tool_result_artifact_ref_present']).lower()}",
        f"final_answer_status: {result['final_answer_status']}",
        f"final_answer_artifact_ref_present: {str(result['final_answer_artifact_ref_present']).lower()}",
        f"codex_call_count: {result['codex_call_count']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"real_llm_status: {result['real_llm_status']}",
        f"provider_status: {result['provider_status']}",
        f"network_listener_status: {result['network_listener_status']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
