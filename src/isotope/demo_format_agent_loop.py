"""Plain text formatters for agent-loop demo scenarios."""

from __future__ import annotations

from typing import Any


def _format_agent_loop_friction_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"agent_loop_friction_ok: {str(result['agent_loop_friction_ok']).lower()}",
        f"private_append_required: {str(result['private_append_required']).lower()}",
        f"app_friction_count: {result['app_friction_count']}",
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
        f"app_friction_count: {result['app_friction_count']}",
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
        f"app_friction_count: {result['app_friction_count']}",
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
        f"app_friction_count: {result['app_friction_count']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)


def _format_agent_loop_tick_policy_trace_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"tick_policy_trace_ok: {str(result['tick_policy_trace_ok']).lower()}",
        f"ready_continue_ok: {str(result['ready_continue_ok']).lower()}",
        f"user_pause_stop_reason: {result['user_pause_stop_reason']}",
        f"budget_stop_reason: {result['budget_stop_reason']}",
        f"approval_stop_reason: {result['approval_stop_reason']}",
        f"completed_stop_reason: {result['completed_stop_reason']}",
        f"app_friction_count: {result['app_friction_count']}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)


def _format_agent_loop_tick_driver_trace_plain_text(result: dict[str, Any]) -> str:
    executed = result["executed_tick"]
    stopped = {tick["case_id"]: tick for tick in result["stopped_ticks"]}
    lines = [
        f"scenario: {result['scenario']}",
        f"session_id: {result['session_id']}",
        f"run_id: {result['run_id']}",
        f"run_status: {result['run_status']}",
        f"transport: {result['transport']}",
        f"tick_driver_trace_ok: {str(result['tick_driver_trace_ok']).lower()}",
        f"executed_tick_status: {executed['tick_status']}",
        f"executed_selected_step: {executed['selected_step']}",
        f"executed_before_phase: {executed['before_policy']['phase']}",
        f"executed_after_phase: {executed['after_policy']['phase']}",
        (
            "executed_after_ticks_used: "
            f"{executed['after_policy']['tick_budget']['ticks_used']}"
        ),
        f"budget_stop_reason: {stopped['budget_exhausted']['stop_reason']}",
        f"user_pause_stop_reason: {stopped['user_pause']['stop_reason']}",
        f"app_friction_count: {result['app_friction_count']}",
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
        f"app_friction_count: {result['app_friction_count']}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)


def _format_agent_loop_planner_validated_runner_plain_text(
    result: dict[str, Any],
) -> str:
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
        f"app_friction_count: {result['app_friction_count']}",
        f"replay_ok: {str(result['replay_ok']).lower()}",
        f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}",
        f"model_status: {result['model_status']}",
        f"scheduler_status: {result['scheduler_status']}",
        f"memory_status: {result['memory_status']}",
        f"next_development_step: {result['next_development_step']}",
    ]
    return "\n".join(lines)
