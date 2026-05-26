"""Agent-loop planner validation demo scenarios."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..agent_loop.demo_agent_loop_scenarios import _deterministic_planner_decisions
from ..demo_planner_helpers import (
    _fixture_rejected,
    _planner_decision_summaries,
    _planner_io_fixture,
    _planner_io_validator_input,
    _validate_planner_io_output,
)
from ...platform.state.checkpoint_store import FileCheckpointStore
from ...platform.state.projector import RunProjector
from ...runtime.in_process import InProcessServer


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
        "app_friction": [],
        "app_friction_count": 0,
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
        "app_friction": [],
        "app_friction_count": 0,
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
