from __future__ import annotations

from isotope.features.supervisor.commands.handlers.capacity import (
    execute_codex_operation_via_agent_loop,
)


def test_codex_operation_executes_request_context_via_agent_loop_capacity(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text(
        "Supervisor loop routes Codex operations through capacity.\n",
        encoding="utf-8",
    )

    result = execute_codex_operation_via_agent_loop(
        goal="查一下 loop capacity 接线",
        operation="request_context",
        inputs={
            "codex_home": str(tmp_path / "codex"),
            "cwd": str(workspace),
            "query": "capacity loop",
        },
        state_root=tmp_path / "agent-loop",
    )

    assert result["kind"] == "call_capacity"
    assert result["capacity_id"] == "supervisor.codex_operation"
    assert result["operation"] == "request_context"
    assert result["agent_loop"]["planner_output_summary"]["selected_step"] == "call_capability"
    assert result["agent_loop"]["planner_output_summary"]["capability_id"] == (
        "supervisor.codex_operation"
    )
    assert result["agent_loop_summary"]["agent_loop_executed"] is True
    assert result["agent_loop_summary"]["agent_loop_tick_status"] == "executed"
