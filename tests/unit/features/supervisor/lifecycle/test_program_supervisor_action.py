from __future__ import annotations

import argparse
from typing import Any

from isotope.features.supervisor.commands.supervise.action import (
    append_supervise_llm_action,
)
from isotope.features.supervisor.commands.supervise.execution import (
    append_supervise_execution,
)


def test_lifecycle_execution_prepares_context_but_llm_selects_action() -> None:
    payload: dict[str, Any] = {}
    action = append_supervise_llm_action(
        _args(llm_execute=True),
        payload,
        action_report=object(),
        active_goals=[],
        explicit_goal=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution={
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
        },
        api=_LLMUsesPreparedContextApi(),
    )

    assert action == {
        "kind": "monitor",
        "reason": "LLM chose to wait after reading prepared lifecycle context",
    }
    assert payload["supervisor_action"] == action
    assert payload["llm_action"] == action
    assert payload["supervisor_prepared_action_context"] == {
        "kind": "supervisor_prepared_action_context",
        "source": "program",
        "candidates": [
            {
                "reason": "worker_lifecycle_execution",
                "action": {
                    "kind": "launch_session",
                    "target_name": "supervisor-merge-dispatch",
                    "source": "integration_review",
                },
            }
        ],
    }
    assert payload["supervisor_action_planner"] == {
        "source": "llm",
        "reason": "prepared_context",
    }


def test_supervisor_action_falls_back_to_llm_when_program_has_no_deterministic_action() -> None:
    payload: dict[str, Any] = {}
    action = append_supervise_llm_action(
        _args(llm_execute=True),
        payload,
        action_report=object(),
        active_goals=[],
        explicit_goal="ship the requested change",
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=None,
        api=_LLMFallbackApi(),
    )

    assert action == {
        "kind": "request_context",
        "query": "existing supervisor action planner contract",
    }
    assert payload["supervisor_action"] == action
    assert payload["llm_action"] == action
    assert payload["supervisor_action_planner"] == {
        "source": "llm",
        "reason": "llm_fallback",
    }


def test_lifecycle_execution_does_not_override_llm_selected_action() -> None:
    payload = {
        "supervisor_action": {
            "kind": "monitor",
            "reason": "LLM chose to wait",
        },
        "llm_action": {
            "kind": "monitor",
            "reason": "LLM chose to wait",
        },
        "supervisor_action_planner": {
            "source": "llm",
            "reason": "prepared_context",
        },
    }

    executed = append_supervise_execution(
        _args(llm_execute=True),
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
        lifecycle_execution={
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
        },
        api=_ExecutionUsesLLMActionApi(),
    )

    assert executed == {
        "kind": "monitor",
        "skipped": True,
        "reason": "LLM chose to wait",
    }
    assert payload["executed"] == executed


def _args(**overrides: Any) -> argparse.Namespace:
    values = {
        "llm_action": False,
        "llm_execute": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class _LLMUsesPreparedContextApi:
    def _loop_without_autonomous_scope(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def _decide_action_with_llm(
        self,
        _args: Any,
        _report: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        assert payload["supervisor_prepared_action_context"]["candidates"][0][
            "reason"
        ] == "worker_lifecycle_execution"
        return {
            "kind": "monitor",
            "reason": "LLM chose to wait after reading prepared lifecycle context",
        }

    def _promote_llm_command_suggestion(self, _payload: dict[str, Any]) -> None:
        return None


class _LLMFallbackApi:
    def _loop_without_autonomous_scope(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def _decide_action_with_llm(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "kind": "request_context",
            "query": "existing supervisor action planner contract",
        }

    def _promote_llm_command_suggestion(self, _payload: dict[str, Any]) -> None:
        return None


class _ExecutionUsesLLMActionApi:
    def _execute_llm_action(
        self,
        _args: Any,
        _report: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "kind": payload["supervisor_action"]["kind"],
            "skipped": True,
            "reason": payload["supervisor_action"]["reason"],
        }

    def _worker_lifecycle_execution_executed(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("lifecycle execution should not override LLM action")

    def _maybe_replan_after_context_request(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> None:
        return None
