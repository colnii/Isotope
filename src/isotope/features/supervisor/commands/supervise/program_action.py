"""Program-prepared Supervisor action context for supervise/loop."""

from __future__ import annotations

from typing import Any

from isotope.features.supervisor.lifecycle import worker_lifecycle_execution_action


def select_required_supervisor_action(
    args: Any,
    action_report: Any,
    *,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    fanout_status: dict[str, Any] | None,
    fanout_paused: bool,
    worker_role_guard: dict[str, Any] | None,
    fanout_plan: dict[str, Any] | None,
    api: Any,
) -> dict[str, Any] | None:
    if fanout_paused:
        return _candidate(
            reason="fanout_paused",
            action=api._fanout_paused_action(fanout_status),
        )
    if fanout_plan is not None:
        return _candidate(
            reason="fanout_plan",
            action=api._fanout_llm_action(fanout_plan),
        )
    if worker_role_guard is not None:
        return _candidate(
            reason="worker_role_guard",
            action=api._recursive_worker_role_guard_action(worker_role_guard),
        )
    if api._loop_without_autonomous_scope(
        args,
        action_report,
        active_goals,
        explicit_goal,
    ):
        return _candidate(
            reason="idle_loop",
            action=api._idle_loop_llm_action(),
        )
    return None


def build_supervisor_prepared_action_context(
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
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    if lifecycle_execution is not None:
        candidates.append(
            _candidate(
                reason="worker_lifecycle_execution",
                action=worker_lifecycle_execution_action(lifecycle_execution),
            )
        )
    if merge_dispatch is not None:
        if merge_dispatch.get("status") == "worker_already_running":
            action = api._merge_dispatch_already_running_action(merge_dispatch)
        else:
            action = merge_dispatch["launch_spec"]
        candidates.append(
            _candidate(
                reason="merge_dispatch",
                action=action,
            )
        )
    if not candidates:
        return None
    return {
        "kind": "supervisor_prepared_action_context",
        "source": "program",
        "candidates": candidates,
    }


def _candidate(*, reason: str, action: dict[str, Any]) -> dict[str, Any]:
    return {
        "reason": reason,
        "action": action,
    }
