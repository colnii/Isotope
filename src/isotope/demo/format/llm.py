"""Plain text formatters for terminal and LLM demo scenarios."""

from __future__ import annotations

from typing import Any


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
        f"app_entry_readiness_check_ok: {str(result['app_entry_readiness_check_ok']).lower()}",
        f"user_message_entry_ok: {str(result['user_message_entry_ok']).lower()}",
        f"blocked_status_code: {result['blocked_status_code']}",
        f"blocked_result_status: {result['blocked_result_status']}",
        f"blocked_no_side_effects: {str(result['blocked_no_side_effects']).lower()}",
        f"ready_readiness_check_ready: {str(result['ready_readiness_check_ready']).lower()}",
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
