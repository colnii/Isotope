from __future__ import annotations

import argparse
from typing import Any

from isotope.features.supervisor.commands.supervise.action import (
    append_supervise_llm_action,
    append_supervise_supervisor_action,
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


def test_supervisor_action_prepares_fixed_facts_for_llm_choice() -> None:
    payload: dict[str, Any] = {
        "current_batch": {
            "target_names": ["running-worker"],
            "summary": {"running": 1, "blocked": 0},
        },
        "recent_context_results": [
            {
                "cwd": "/repo",
                "query": "已有上下文",
                "items": [{"path": "docs/current/status.md"}],
            }
        ],
        "decision_requests": [
            {
                "target_name": "blocked-worker",
                "question": "选 A 还是 B？",
                "context_status": "conflict",
            }
        ],
        "worker_reviews": {
            "status": "ok",
            "decision_summary": {"merge_candidates": 1},
            "workers": [
                {
                    "name": "merge-worker",
                    "next_decision": {"merge_suitable": True},
                }
            ],
        },
        "delete_worktree_candidates": [
            {"target_name": "done-worker", "record_id": "managed-done"}
        ],
        "capacity_decisions": [
            {
                "capacity_id": "artifact.review",
                "next_action": "call_capacity",
                "can_execute_agent_loop": True,
            },
            {
                "capacity_id": "memory.recall",
                "next_action": "request_input",
                "can_execute_agent_loop": False,
            },
        ],
    }

    action = append_supervise_supervisor_action(
        _args(llm_action=True),
        payload,
        action_report=object(),
        active_goals=[
            {
                "goal_id": "goal-1",
                "target_name": "blocked-worker",
                "last_status": "blocked",
            }
        ],
        explicit_goal=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=None,
        api=_LLMUsesPreparedFactsApi(),
    )

    assert action == {
        "kind": "request_context",
        "query": "复查 blocked-worker 的上下文",
    }
    assert payload["supervisor_action"] == action
    assert payload["supervisor_action_planner"] == {
        "source": "llm",
        "reason": "prepared_context",
    }
    assert payload["supervisor_prepared_action_context"] == {
        "kind": "supervisor_prepared_action_context",
        "source": "program",
        "facts": [
            {
                "kind": "active_goals",
                "count": 1,
                "target_names": ["blocked-worker"],
                "statuses": {"blocked": 1},
            },
            {
                "kind": "current_batch",
                "target_names": ["running-worker"],
                "summary": {"running": 1, "blocked": 0},
            },
            {
                "kind": "decision_requests",
                "count": 1,
                "target_names": ["blocked-worker"],
                "context_statuses": {"conflict": 1},
            },
            {
                "kind": "recent_context_results",
                "count": 1,
                "queries": ["已有上下文"],
            },
            {
                "kind": "worker_reviews",
                "status": "ok",
                "decision_summary": {"merge_candidates": 1},
                "merge_suitable": 1,
            },
            {
                "kind": "delete_worktree_candidates",
                "count": 1,
                "target_names": ["done-worker"],
            },
            {
                "kind": "capacity_decisions",
                "ready": ["artifact.review"],
                "request_input": ["memory.recall"],
                "blocked": [],
            },
        ],
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


class _LLMUsesPreparedFactsApi:
    def _loop_without_autonomous_scope(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def _decide_action_with_llm(
        self,
        _args: Any,
        _report: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        prepared = payload["supervisor_prepared_action_context"]
        assert not prepared.get("candidates")
        assert [fact["kind"] for fact in prepared["facts"]] == [
            "active_goals",
            "current_batch",
            "decision_requests",
            "recent_context_results",
            "worker_reviews",
            "delete_worktree_candidates",
            "capacity_decisions",
        ]
        return {
            "kind": "request_context",
            "query": "复查 blocked-worker 的上下文",
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
