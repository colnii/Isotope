"""Agent-loop developer demo scenarios."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .platform.state.checkpoint_store import FileCheckpointStore
from .platform.state.projector import RunProjector
from .runtime.in_process import InProcessServer


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
        "review app friction report",
    ]
    resolved_app_surfaces = [
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
        "resolved_app_surfaces": resolved_app_surfaces,
        "app_friction": [],
        "app_friction_count": 0,
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
            "only reopen mainline if that produces non-empty app_friction."
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
        "app_friction": [],
        "app_friction_count": 0,
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
            "only reopen mainline if that matrix produces non-empty app_friction."
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
