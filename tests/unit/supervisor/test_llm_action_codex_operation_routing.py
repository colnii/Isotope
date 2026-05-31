from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.commands.llm.action import execute_llm_action


class RecordingApi:
    DEFAULT_MAX_CONTEXT_REQUESTS = 0

    def __init__(self, expected_result: dict[str, Any]) -> None:
        self.expected_result = expected_result
        self.codex_operation_actions: list[dict[str, Any]] = []

    def _execute_context_action(self, args: argparse.Namespace, action: dict[str, Any]) -> dict[str, Any]:
        return {"kind": "request_context", "direct": True}

    def _execute_codex_operation_action(
        self,
        args: argparse.Namespace,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        self.codex_operation_actions.append(dict(action))
        return self.expected_result


def test_execute_llm_action_routes_request_context_through_codex_operation_capacity(tmp_path):
    expected = {
        "kind": "call_capacity",
        "capacity_id": "supervisor.codex_operation",
        "operation": "request_context",
        "agent_loop_summary": {"agent_loop_executed": True},
    }
    api = RecordingApi(expected)
    args = argparse.Namespace(
        codex_home=str(tmp_path / "codex"),
        max_context_requests=0,
    )
    action = {
        "kind": "request_context",
        "cwd": str(Path.cwd()),
        "query": "loop capacity",
    }

    result = execute_llm_action(
        args,
        report=None,
        payload={"llm_action": action},
        api=api,
    )

    assert result == expected
    assert api.codex_operation_actions == [action]
