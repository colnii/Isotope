from __future__ import annotations

import argparse
from typing import Any

from isotope.features.supervisor.commands.supervise.action import (
    append_supervise_llm_action,
)


def test_lifecycle_execution_sets_program_supervisor_action_without_llm() -> None:
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
        api=_NoLLMApi(),
    )

    assert action == {
        "kind": "launch_session",
        "target_name": "supervisor-merge-dispatch",
        "source": "integration_review",
    }
    assert payload["supervisor_action"] == action
    assert payload["llm_action"] == action
    assert payload["supervisor_action_planner"] == {
        "source": "program",
        "reason": "worker_lifecycle_execution",
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


def _args(**overrides: Any) -> argparse.Namespace:
    values = {
        "llm_action": False,
        "llm_execute": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class _NoLLMApi:
    def _decide_action_with_llm(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("program-resolved supervisor action should not call LLM")

    def _promote_llm_command_suggestion(self, _payload: dict[str, Any]) -> None:
        raise AssertionError("program-resolved supervisor action should not promote LLM suggestions")


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
