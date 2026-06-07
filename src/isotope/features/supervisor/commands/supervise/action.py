"""LLM action selection for supervise/loop commands."""

from __future__ import annotations

from typing import Any

from isotope.features.supervisor.commands.supervisor_action import (
    set_supervisor_action_planner_payload,
    set_supervisor_action_payload,
)
from isotope.features.supervisor.commands.supervise.program_action import (
    select_program_supervisor_action,
)


def append_supervise_llm_action(
    args: Any,
    payload: dict[str, Any],
    action_report: Any,
    *,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    fanout_status: dict[str, Any] | None,
    fanout_paused: bool,
    worker_role_guard: dict[str, Any] | None,
    merge_dispatch: dict[str, Any] | None,
    fanout_plan: dict[str, Any] | None,
    lifecycle_execution: dict[str, Any] | None = None,
    api: Any | None = None,
) -> dict[str, Any] | None:
    return append_supervise_supervisor_action(
        args,
        payload,
        action_report,
        active_goals=active_goals,
        explicit_goal=explicit_goal,
        fanout_status=fanout_status,
        fanout_paused=fanout_paused,
        worker_role_guard=worker_role_guard,
        merge_dispatch=merge_dispatch,
        fanout_plan=fanout_plan,
        lifecycle_execution=lifecycle_execution,
        api=api,
    )


def append_supervise_supervisor_action(
    args: Any,
    payload: dict[str, Any],
    action_report: Any,
    *,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    fanout_status: dict[str, Any] | None,
    fanout_paused: bool,
    worker_role_guard: dict[str, Any] | None,
    merge_dispatch: dict[str, Any] | None,
    fanout_plan: dict[str, Any] | None,
    lifecycle_execution: dict[str, Any] | None = None,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not (args.llm_action or args.llm_execute):
        return None

    program_action = select_program_supervisor_action(
        args,
        action_report,
        active_goals=active_goals,
        explicit_goal=explicit_goal,
        fanout_status=fanout_status,
        fanout_paused=fanout_paused,
        worker_role_guard=worker_role_guard,
        merge_dispatch=merge_dispatch,
        fanout_plan=fanout_plan,
        lifecycle_execution=lifecycle_execution,
        api=api,
    )
    if program_action is not None:
        set_supervisor_action_payload(payload, program_action.action)
        set_supervisor_action_planner_payload(
            payload,
            source="program",
            reason=program_action.reason,
        )
        return program_action.action

    action = api._decide_action_with_llm(args, action_report, payload)
    set_supervisor_action_payload(payload, action)
    set_supervisor_action_planner_payload(
        payload,
        source="llm",
        reason="llm_fallback",
    )
    api._promote_llm_command_suggestion(payload)
    return action
