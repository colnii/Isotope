"""Supervisor adapter for product-level native coding.

This module drives the existing agent loop. It is not a separate coding loop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from isotope.platform.ids import new_id
from isotope.runtime.in_process import InProcessServer


CODING_TASK_RUN_CAPABILITY = "coding_task.run"


def run_native_coding_agent_loop(
    *,
    state_root: Path,
    cwd: Path,
    goal: str,
    inputs: Mapping[str, Any],
    provider: Any,
    max_steps: int,
) -> dict[str, Any]:
    server = InProcessServer(state_root / "supervisor" / "native-coding-runs")
    session = server.create_session()
    run = server.create_run(session["session_id"], goal)
    workspace_id = _string(inputs.get("workspace_id"), "workspace_" + new_id("coding_task"))
    ticks: list[dict[str, Any]] = []

    for index in range(max_steps):
        tick_workspace_id = f"{workspace_id}_tick_{index + 1}"
        tick = server.run_agent_loop_provider_planner_tick(
            run["run_id"],
            provider=provider,
            agent_id="agent_native_coding",
            tick_id=f"tick_native_coding_{index + 1}",
            decision_id=f"decision_native_coding_{index + 1}",
            tick_budget={
                "max_ticks": max_steps,
                "ticks_used": index,
                "budget_basis": "coding_task.run",
            },
            default_context_extra={
                "coding_task": {
                    "goal": goal,
                    "workspace_label": "current_project",
                    "allowed_capabilities": [
                        "code.search",
                        "code.read",
                        "code.ast_edit",
                        "coding_task.execute",
                    ],
                    "verification_intent": _string(
                        inputs.get("verification_intent"),
                        "",
                    ),
                }
            },
            capability_system_inputs={
                "root": str(state_root),
                "cwd": str(cwd),
                "workspace_id": tick_workspace_id,
            },
            max_tokens=512,
        )
        ticks.append(tick)
        if _coding_status([tick]) == "verified":
            break
        after_policy = tick.get("after_policy")
        if isinstance(after_policy, Mapping) and after_policy.get("should_continue") is not True:
            break

    return {
        "kind": "native_coding_agent_loop",
        "status": _coding_status(ticks),
        "workspace_id": _coding_workspace_id(ticks) or workspace_id,
        "tick_count": len(ticks),
        "context_call_count": _capability_call_count(ticks, {"code.search", "code.read"}),
        "source_workspace_write": "not_performed",
        "reviewed_apply_request": _reviewed_apply_request(ticks),
        "ticks": ticks,
    }


def _coding_status(ticks: list[dict[str, Any]]) -> str:
    for tick in reversed(ticks):
        execution = _coding_execution(tick)
        if isinstance(execution, Mapping):
            status = execution.get("status")
            if isinstance(status, str):
                return status
    return "blocked"


def _coding_execution(tick: Mapping[str, Any]) -> Mapping[str, Any] | None:
    capability_run = _capability_run(tick)
    if not isinstance(capability_run, Mapping):
        return None
    execution = capability_run.get("coding_execution")
    return execution if isinstance(execution, Mapping) else None


def _coding_workspace_id(ticks: list[dict[str, Any]]) -> str | None:
    for tick in reversed(ticks):
        execution = _coding_execution(tick)
        if isinstance(execution, Mapping):
            workspace_id = execution.get("workspace_id")
            if isinstance(workspace_id, str) and workspace_id:
                return workspace_id
    return None


def _reviewed_apply_request(ticks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for tick in reversed(ticks):
        execution = _coding_execution(tick)
        if not isinstance(execution, Mapping):
            continue
        reviewed_apply = execution.get("reviewed_apply")
        if not isinstance(reviewed_apply, Mapping):
            continue
        handle_id = reviewed_apply.get("review_handle_id")
        workspace_id = reviewed_apply.get("workspace_id")
        changed_files = reviewed_apply.get("changed_files")
        if not isinstance(handle_id, str) or not isinstance(workspace_id, str):
            continue
        return {
            "capability_id": "coding_task.apply_reviewed_diff",
            "arguments": {"review_handle_id": handle_id},
            "workspace_id": workspace_id,
            "changed_files": list(changed_files) if isinstance(changed_files, list) else [],
            "source_workspace_write": "requires_explicit_apply",
        }
    return None


def _capability_call_count(ticks: list[dict[str, Any]], capability_ids: set[str]) -> int:
    count = 0
    for tick in ticks:
        capability_run = _capability_run(tick)
        if isinstance(capability_run, Mapping) and capability_run.get("capability_id") in capability_ids:
            count += 1
    return count


def _capability_run(tick: Mapping[str, Any]) -> Mapping[str, Any] | None:
    contract = tick.get("planner_contract_result")
    if not isinstance(contract, Mapping):
        return None
    planner = contract.get("planner_result")
    if not isinstance(planner, Mapping):
        return None
    step_result = planner.get("step_result")
    if not isinstance(step_result, Mapping):
        return None
    action_result = step_result.get("action_result")
    if not isinstance(action_result, Mapping):
        return None
    capability_run = action_result.get("capability_run")
    return capability_run if isinstance(capability_run, Mapping) else None


def _string(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default
