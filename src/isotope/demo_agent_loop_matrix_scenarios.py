"""Agent-loop planner matrix and restart demo scenarios."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .demo_agent_loop_scenarios import _run_agent_loop_planner_adapter_spike
from .demo_planner_helpers import (
    _planner_happy_fixture_summary,
    _run_planner_blocked_deferred_fixture,
    _run_planner_malformed_action_fixture,
)
from .platform.state.checkpoint_store import FileCheckpointStore
from .platform.state.projector import RunProjector
from .runtime.in_process import InProcessServer


def _run_agent_loop_planner_matrix_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    happy = _run_agent_loop_planner_adapter_spike(root / "happy-path")
    blocked = _run_planner_blocked_deferred_fixture()
    malformed = _run_planner_malformed_action_fixture(root / "malformed-action")
    fixtures = [happy, blocked, malformed]
    app_deferred_friction = list(blocked["app_deferred_friction"])
    app_friction: list[dict[str, Any]] = []
    planner_matrix_ok = (
        happy["planner_adapter_friction_ok"] is True
        and blocked["status"] == "blocked_deferred"
        and malformed["status"] == "failed_closed"
        and malformed["partial_events_appended"] is False
        and app_friction == []
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
        "app_friction": app_friction,
        "app_friction_count": len(app_friction),
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
        "app_friction": [],
        "app_friction_count": 0,
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
