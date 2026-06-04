from __future__ import annotations

import argparse

from isotope.features.supervisor.lifecycle.executor import (
    build_worker_lifecycle_execution_plan,
    worker_lifecycle_execution_action,
    worker_lifecycle_execution_planned_executed,
)
from isotope.features.supervisor.commands.supervise.action import (
    append_supervise_llm_action,
)
from isotope.features.supervisor.commands.supervise.execution import (
    append_supervise_execution,
)


def test_lifecycle_execution_plan_launches_merge_worker_from_program_next_step() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(next_step="launch_merge_worker"),
        merge_dispatch={
            "status": "ready_to_launch",
            "launch_spec": {
                "kind": "launch_session",
                "target_name": "supervisor-merge-dispatch",
                "source": "integration_review",
            },
        },
    )

    assert plan is not None
    assert plan.to_dict() == {
        "kind": "merge_dispatch",
        "source": "worker_lifecycle",
        "next_step": "launch_merge_worker",
        "status": "ready_to_launch",
        "merge_dispatch": {
            "status": "ready_to_launch",
            "launch_spec": {
                "kind": "launch_session",
                "target_name": "supervisor-merge-dispatch",
                "source": "integration_review",
            },
        },
    }
    assert worker_lifecycle_execution_action(plan.to_dict()) == {
        "kind": "launch_session",
        "target_name": "supervisor-merge-dispatch",
        "source": "integration_review",
    }


def test_lifecycle_execution_plan_monitors_existing_merge_worker() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(next_step="launch_merge_worker"),
        merge_dispatch={
            "status": "worker_already_running",
            "running_worker": {
                "name": "supervisor-merge-dispatch",
                "record_id": "managed-merge",
            },
        },
    )

    assert plan is not None
    plan_payload = plan.to_dict()
    assert worker_lifecycle_execution_action(plan_payload) == {
        "kind": "monitor",
        "reason": "merge worker already running",
        "managed": {
            "name": "supervisor-merge-dispatch",
            "record_id": "managed-merge",
        },
    }
    assert worker_lifecycle_execution_planned_executed(plan_payload) == {
        "kind": "monitor",
        "reason": "merge worker already running",
        "managed": {
            "name": "supervisor-merge-dispatch",
            "record_id": "managed-merge",
        },
        "skipped": True,
    }


def test_lifecycle_execution_plan_ignores_non_program_decisions() -> None:
    assert (
        build_worker_lifecycle_execution_plan(
            worker_lifecycle_decision=_decision(
                next_step="monitor",
                policy_status="model_required",
                program_action=None,
            ),
            merge_dispatch={
                "status": "ready_to_launch",
                "launch_spec": {"kind": "launch_session"},
            },
        )
        is None
    )


def test_supervise_action_uses_lifecycle_execution_plan() -> None:
    payload: dict[str, object] = {}
    action = append_supervise_llm_action(
        argparse.Namespace(llm_action=True, llm_execute=False),
        payload,
        action_report=object(),
        active_goals=[],
        explicit_goal=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=_merge_dispatch_plan(),
        api=_StubActionApi(),
    )

    assert action == {
        "kind": "launch_session",
        "target_name": "supervisor-merge-dispatch",
        "source": "integration_review",
    }
    assert payload["llm_action"] == action


def test_supervise_execution_uses_lifecycle_execution_plan() -> None:
    api = _StubExecutionApi()
    payload: dict[str, object] = {}

    executed = append_supervise_execution(
        argparse.Namespace(
            llm_execute=True,
            auto_execute=False,
            execute=False,
            merge_dispatch_execute=True,
        ),
        payload,
        report=object(),
        action_report=object(),
        active_goals=[],
        goal_replenishment=None,
        worker_reviews=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=_merge_dispatch_plan(),
        api=api,
    )

    assert executed == {
        "kind": "launch_session",
        "display_kind": "merge_dispatch",
        "target_name": "supervisor-merge-dispatch",
        "source": "integration_review",
    }
    assert payload["executed"] == executed
    assert api.launched == [
        {
            "kind": "launch_session",
            "target_name": "supervisor-merge-dispatch",
            "source": "integration_review",
        }
    ]


def _decision(
    *,
    next_step: str,
    policy_status: str = "program_resolved",
    program_action: str | None = "dispatch_merge",
) -> dict[str, object]:
    return {
        "kind": "worker_lifecycle_decision",
        "action": program_action or "monitor",
        "stage": "ready_to_merge",
        "next_step": next_step,
        "policy": {
            "policy_status": policy_status,
            "program_action": program_action,
            "remaining_step": next_step,
            "blocked_reason": None,
        },
    }


def _merge_dispatch_plan() -> dict[str, object]:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(next_step="launch_merge_worker"),
        merge_dispatch={
            "status": "ready_to_launch",
            "launch_spec": {
                "kind": "launch_session",
                "target_name": "supervisor-merge-dispatch",
                "source": "integration_review",
            },
        },
    )
    assert plan is not None
    return plan.to_dict()


class _StubActionApi:
    def _fanout_paused_action(self, fanout_status):
        raise AssertionError("fanout should not be used")

    def _fanout_llm_action(self, fanout_plan):
        raise AssertionError("fanout should not be used")

    def _recursive_worker_role_guard_action(self, worker_role_guard):
        raise AssertionError("worker role guard should not be used")

    def _loop_without_autonomous_scope(self, *args, **kwargs):
        return False

    def _decide_action_with_llm(self, *args, **kwargs):
        raise AssertionError("LLM should not be called for lifecycle execution")

    def _promote_llm_command_suggestion(self, payload):
        raise AssertionError("LLM promotion should not run")


class _StubExecutionApi:
    def __init__(self) -> None:
        self.launched: list[dict[str, object]] = []

    def _fanout_paused_executed(self, fanout_status):
        raise AssertionError("fanout should not be used")

    def _execute_fanout_launch_actions(self, *args, **kwargs):
        raise AssertionError("fanout should not be used")

    def _recursive_worker_role_guard_executed(self, worker_role_guard):
        raise AssertionError("worker role guard should not be used")

    def _execute_llm_action(self, *args, **kwargs):
        raise AssertionError("LLM action should not execute lifecycle plan")

    def _maybe_replan_after_context_request(self, *args, **kwargs):
        raise AssertionError("context replan should not run")

    def _execute_auto_action(self, *args, **kwargs):
        raise AssertionError("auto execution should not be used")

    def _auto_execute_action(self, *args, **kwargs):
        raise AssertionError("auto execution should not be used")

    def _execute_advice(self, *args, **kwargs):
        raise AssertionError("advice execution should not be used")

    def _execute_launch_action(self, args, action):
        self.launched.append(dict(action))
        return {
            "kind": "launch_session",
            "target_name": action["target_name"],
            "source": action["source"],
        }

    def _execute_failure_guarded_action(self, args, *, action, execute, **kwargs):
        del args, action, kwargs
        return execute()

    def _mark_merge_dispatch_execution(self, executed):
        executed = dict(executed)
        executed["display_kind"] = "merge_dispatch"
        return executed

    def _refresh_current_batch_after_execution(self, *args, **kwargs):
        return True
