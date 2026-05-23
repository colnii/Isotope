"""Output formatting helpers for developer demo scenarios."""

from __future__ import annotations

import json
from typing import Any

from .demo_trace_format import _format_trace


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
    if result.get("scenario") == "workbench":
        return _format_workbench_plain_text(result)
    if result.get("scenario") == "workbench-ask":
        return _format_workbench_ask_plain_text(result)
    if result.get("scenario") == "project-workspace":
        return _format_project_workspace_plain_text(result)
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
        f"app_friction_count: {result['app_friction_count']}",
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


def _format_workbench_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"transport: {result['transport']}",
        f"workbench_ok: {str(result['workbench_ok']).lower()}",
        f"project_count: {result['project_count']}",
        f"task_count: {result['task_count']}",
        f"file_count: {result['file_count']}",
        f"search_result_count: {result['search_result_count']}",
        f"search_result_types: {', '.join(result['search_result_types'])}",
        "empty_state: none" if result["empty_state"] is None else "empty_state: present",
        f"updated_at_present: {str(result['updated_at_present']).lower()}",
        f"get_workbench_status_code: {result['get_workbench_status_code']}",
        f"post_workbench_status_code: {result['post_workbench_status_code']}",
        f"content_policy: {result['content_policy']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_workbench_ask_plain_text(result: dict[str, Any]) -> str:
    counts = result["context_counts"]
    lines = [
        f"scenario: {result['scenario']}",
        f"transport: {result['transport']}",
        f"question: {result['question']}",
        f"answer: {result['answer']}",
        f"provider: {result['provider']}/{result['model']}",
        (
            "context: "
            f"projects={counts['projects']} "
            f"tasks={counts['tasks']} "
            f"files={counts['files']} "
            f"search_results={counts['search_results']}"
        ),
        f"provider_call_count: {result['provider_call_count']}",
        f"content_policy: {result['content_policy']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)


def _format_project_workspace_plain_text(result: dict[str, Any]) -> str:
    counts = result["workbench_counts"]
    lines = [
        f"scenario: {result['scenario']}",
        f"transport: {result['transport']}",
        f"workspace_ok: {str(result['workspace_ok']).lower()}",
        f"project_task_count: {result['project_task_count']}",
        f"project_file_count: {result['project_file_count']}",
        (
            "workbench_counts: "
            f"projects={counts['projects']} "
            f"tasks={counts['tasks']} "
            f"files={counts['files']} "
            f"search_results={counts['search_results']}"
        ),
        f"search_result_types: {', '.join(result['search_result_types'])}",
        f"post_workspace_status_code: {result['post_workspace_status_code']}",
        f"content_policy: {result['content_policy']}",
        f"memory_status: {result['memory_status']}",
    ]
    return "\n".join(lines)
