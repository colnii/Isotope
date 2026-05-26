"""Output formatting helpers for developer demo scenarios."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .agent_loop import (
    _format_agent_loop_friction_plain_text,
    _format_agent_loop_planner_friction_plain_text,
    _format_agent_loop_planner_io_validator_plain_text,
    _format_agent_loop_planner_matrix_plain_text,
    _format_agent_loop_planner_restart_pause_plain_text,
    _format_agent_loop_planner_validated_runner_plain_text,
    _format_agent_loop_tick_driver_trace_plain_text,
    _format_agent_loop_tick_policy_trace_plain_text,
    _format_supervisor_capacity_dashboard_smoke_plain_text,
    _format_supervisor_capacity_handoff_trace_plain_text,
)
from .core import (
    _format_approval_tool_runner_plain_text,
    _format_artifact_review_plain_text,
    _format_default_plain_text,
    _format_external_snapshot_review_plain_text,
    _format_memory_query_smoke_plain_text,
    _format_project_workspace_plain_text,
    _format_v0_2_plain_text,
    _format_workbench_ask_plain_text,
    _format_workbench_plain_text,
)
from .llm import (
    _format_llm_product_chat_app_entry_plain_text,
    _format_llm_provider_route_plain_text,
    _format_llm_terminal_tool_loop_plain_text,
    _format_llm_tool_result_loop_plain_text,
    _format_model_tool_bridge_plain_text,
    _format_terminal_exec_plain_text,
)
from ..demo_trace_format import _format_trace


_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "agent-loop-planner-validated-runner": (
        _format_agent_loop_planner_validated_runner_plain_text
    ),
    "agent-loop-planner-io-validator": (
        _format_agent_loop_planner_io_validator_plain_text
    ),
    "agent-loop-planner-restart-pause": (
        _format_agent_loop_planner_restart_pause_plain_text
    ),
    "agent-loop-tick-driver-trace": _format_agent_loop_tick_driver_trace_plain_text,
    "supervisor-capacity-handoff-trace": (
        _format_supervisor_capacity_handoff_trace_plain_text
    ),
    "supervisor-capacity-dashboard-smoke": (
        _format_supervisor_capacity_dashboard_smoke_plain_text
    ),
    "agent-loop-tick-policy-trace": _format_agent_loop_tick_policy_trace_plain_text,
    "agent-loop-planner-matrix": _format_agent_loop_planner_matrix_plain_text,
    "agent-loop-planner-friction": _format_agent_loop_planner_friction_plain_text,
    "agent-loop-friction": _format_agent_loop_friction_plain_text,
    "external-snapshot-review": _format_external_snapshot_review_plain_text,
    "artifact-review": _format_artifact_review_plain_text,
    "approval-tool-runner": _format_approval_tool_runner_plain_text,
    "terminal-exec": _format_terminal_exec_plain_text,
    "model-tool-bridge": _format_model_tool_bridge_plain_text,
    "llm-provider-route": _format_llm_provider_route_plain_text,
    "llm-tool-result-loop": _format_llm_tool_result_loop_plain_text,
    "llm-product-chat-app-entry": _format_llm_product_chat_app_entry_plain_text,
    "llm-terminal-tool-loop": _format_llm_terminal_tool_loop_plain_text,
    "memory-query-smoke": _format_memory_query_smoke_plain_text,
    "workbench": _format_workbench_plain_text,
    "workbench-ask": _format_workbench_ask_plain_text,
    "project-workspace": _format_project_workspace_plain_text,
    "v0.2": _format_v0_2_plain_text,
}


def _format_plain_text(result: dict[str, Any]) -> str:
    formatter = _FORMATTERS.get(str(result.get("scenario")))
    if formatter is not None:
        return formatter(result)
    return _format_default_plain_text(result)
