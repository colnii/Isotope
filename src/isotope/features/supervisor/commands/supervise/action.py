"""LLM action selection for supervise/loop commands."""

from __future__ import annotations

from typing import Any

from isotope.features.supervisor.lifecycle import worker_lifecycle_execution_action


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
    if api is None:
        from isotope.features.supervisor import runner as api

    if not (args.llm_action or args.llm_execute):
        return None

    if fanout_paused:
        action = api._fanout_paused_action(fanout_status)
    elif fanout_plan is not None:
        action = api._fanout_llm_action(fanout_plan)
    elif worker_role_guard is not None:
        action = api._recursive_worker_role_guard_action(worker_role_guard)
    elif lifecycle_execution is not None:
        action = worker_lifecycle_execution_action(lifecycle_execution)
    elif merge_dispatch is not None:
        if merge_dispatch.get("status") == "worker_already_running":
            action = api._merge_dispatch_already_running_action(merge_dispatch)
        else:
            action = merge_dispatch["launch_spec"]
    elif api._loop_without_autonomous_scope(
        args,
        action_report,
        active_goals,
        explicit_goal,
    ):
        action = api._idle_loop_llm_action()
    else:
        action = api._decide_action_with_llm(args, action_report, payload)
        payload["llm_action"] = action
        api._promote_llm_command_suggestion(payload)
        return action

    payload["llm_action"] = action
    return action
