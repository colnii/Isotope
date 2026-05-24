"""Plain text formatters for core developer demo scenarios."""

from __future__ import annotations

import json
from typing import Any


def _format_default_plain_text(result: dict[str, Any]) -> str:
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


def _format_memory_query_smoke_plain_text(result: dict[str, Any]) -> str:
    lines = [
        f"scenario: {result['scenario']}",
        f"transport: {result['transport']}",
        f"memory_write_status: {result['memory_write_status']}",
        f"memory_query_status: {result['memory_query_status']}",
        f"memory_query_smoke_ok: {str(result['memory_query_smoke_ok']).lower()}",
        f"query: {result['query']}",
        f"query_result_count: {result['query_result_count']}",
        f"recalled_record_id: {result['recalled_record_id']}",
        f"content_policy: {result['content_policy']}",
        f"model_status: {result['model_status']}",
        f"provider_status: {result['provider_status']}",
        f"network_listener_status: {result['network_listener_status']}",
        f"next_development_step: {result['next_development_step']}",
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
