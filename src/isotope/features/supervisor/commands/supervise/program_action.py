"""Program-owned Supervisor action selection for supervise/loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isotope.features.supervisor.lifecycle import worker_lifecycle_execution_action


@dataclass(frozen=True)
class ProgramSupervisorAction:
    action: dict[str, Any]
    reason: str


def select_program_supervisor_action(
    args: Any,
    action_report: Any,
    *,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    fanout_status: dict[str, Any] | None,
    fanout_paused: bool,
    worker_role_guard: dict[str, Any] | None,
    merge_dispatch: dict[str, Any] | None,
    fanout_plan: dict[str, Any] | None,
    lifecycle_execution: dict[str, Any] | None,
    api: Any,
) -> ProgramSupervisorAction | None:
    if fanout_paused:
        return ProgramSupervisorAction(
            action=api._fanout_paused_action(fanout_status),
            reason="fanout_paused",
        )
    if fanout_plan is not None:
        return ProgramSupervisorAction(
            action=api._fanout_llm_action(fanout_plan),
            reason="fanout_plan",
        )
    if worker_role_guard is not None:
        return ProgramSupervisorAction(
            action=api._recursive_worker_role_guard_action(worker_role_guard),
            reason="worker_role_guard",
        )
    if lifecycle_execution is not None:
        return ProgramSupervisorAction(
            action=worker_lifecycle_execution_action(lifecycle_execution),
            reason="worker_lifecycle_execution",
        )
    if merge_dispatch is not None:
        if merge_dispatch.get("status") == "worker_already_running":
            action = api._merge_dispatch_already_running_action(merge_dispatch)
        else:
            action = merge_dispatch["launch_spec"]
        return ProgramSupervisorAction(
            action=action,
            reason="merge_dispatch",
        )
    if api._loop_without_autonomous_scope(
        args,
        action_report,
        active_goals,
        explicit_goal,
    ):
        return ProgramSupervisorAction(
            action=api._idle_loop_llm_action(),
            reason="idle_loop",
        )
    return None
