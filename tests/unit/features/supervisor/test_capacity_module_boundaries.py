from __future__ import annotations

from isotope.features.supervisor.commands import capacity_rendering, capacity_result
from isotope.features.supervisor.commands.handlers import capacity as capacity_command


def test_capacity_handler_reexports_summary_and_rendering_boundaries():
    assert (
        capacity_command.agent_loop_json_result
        is capacity_result.agent_loop_json_result
    )
    assert (
        capacity_command._print_capacity_plan_plain
        is capacity_rendering.print_capacity_plan_plain
    )


def test_capacity_result_extracts_public_metadata_agent_loop_fields():
    payload = {
        "agent_loop": {
            "handoff": {
                "initial_next_tick_kind": "planner_step",
                "post_step_phase": "ready",
                "post_step_should_continue": True,
                "post_step_stop_reason": None,
            },
            "planner_output": {
                "selected_step": "call_capability",
                "raw": "PRIVATE_PLANNER_PAYLOAD",
            },
            "tick_result": {
                "tick_status": "executed",
                "after_policy": {"must_stop_reason": "tick_budget_exhausted"},
                "planner_result": {
                    "step_result": {
                        "action_result": {
                            "artifact_ref": {"artifact_id": "artifact_safe"},
                            "capability_run": {
                                "capability_id": "memory.query",
                                "memory_query": {
                                    "status": "completed",
                                    "results": [{"memory_id": "mem_1"}],
                                    "content_policy": "summary_only",
                                },
                            },
                            "raw": "PRIVATE_ACTION_PAYLOAD",
                        }
                    }
                },
            },
        }
    }

    summary = capacity_result.agent_loop_json_result(payload)

    assert summary == {
        "agent_loop_executed": True,
        "agent_loop_next_tick_kind": "planner_step",
        "agent_loop_planner_selected_step": "call_capability",
        "agent_loop_tick_status": "executed",
        "agent_loop_tick_after_stop_reason": "tick_budget_exhausted",
        "agent_loop_artifact_id": "artifact_safe",
        "agent_loop_post_step_phase": "ready",
        "agent_loop_post_step_should_continue": True,
        "agent_loop_post_step_stop_reason": None,
        "agent_loop_memory_query_status": "completed",
        "agent_loop_memory_query_result_count": 1,
        "agent_loop_memory_query_content_policy": "summary_only",
    }
    assert "PRIVATE_" not in str(summary)


def test_capacity_rendering_prints_plain_capacity_plan(capsys):
    payload = {
        "status_reason": "not_launchable",
        "capacity_blocked_reason": "not_allowlisted",
        "selection": {
            "capacity_id": "context.search",
            "status": "ready_to_call",
        },
        "capability_launch_plan": {
            "status": "not_allowlisted",
            "blocking_reasons": ["not_allowlisted"],
        },
        "supervisor_decision": {"next_action": "blocked"},
        "agent_loop": None,
    }

    capacity_rendering.print_capacity_plan_plain(payload)

    output = capsys.readouterr().out
    assert "Supervisor capacity plan" in output
    assert "capacity_id: context.search" in output
    assert "selection_status: ready_to_call" in output
    assert "status_reason: not_launchable" in output
    assert "launch_status: not_allowlisted" in output
    assert "supervisor_decision_next_action: blocked" in output
    assert "capacity_blocked_reason: not_allowlisted" in output
    assert "launch_blocking_reasons: not_allowlisted" in output
    assert "agent_loop_executed: False" in output
