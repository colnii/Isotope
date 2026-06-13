from __future__ import annotations

from isotope.features.supervisor.commands.capacity import capacity_rendering
from isotope.features.supervisor.commands.capacity import capacity_result
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
                                    "content_policy": "public_metadata",
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
        "agent_loop_memory_query_content_policy": "public_metadata",
    }
    assert "PRIVATE_" not in str(summary)


def test_capacity_result_extracts_research_recall_preview_fields():
    payload = {
        "agent_loop": {
            "tick_result": {
                "planner_result": {
                    "step_result": {
                        "action_result": {
                            "capability_run": {
                                "capability_id": "research.recall",
                                "research_recall": {
                                    "status": "ok",
                                    "content_policy": (
                                        "research_report_artifact_preview_only"
                                    ),
                                    "retrieval": {
                                        "backend": "hybrid",
                                        "dense_status": "ok",
                                    },
                                    "results": [
                                        {
                                            "run_id": "run_research",
                                            "artifact_id": "artifact_report",
                                            "artifact_type": "research.report",
                                            "summary": (
                                                "Stored research report preview."
                                            ),
                                            "ref": {
                                                "ref_type": "artifact",
                                                "scope": "run",
                                                "run_id": "run_research",
                                                "artifact_id": "artifact_report",
                                            },
                                            "source_refs": [
                                                {
                                                    "ref_type": "url",
                                                    "url": "https://example.com",
                                                }
                                            ],
                                            "provenance": {
                                                "execution_id": "exec_research"
                                            },
                                            "content": (
                                                "raw report body must not leak"
                                            ),
                                        }
                                    ],
                                },
                            },
                        }
                    }
                },
            },
        }
    }

    summary = capacity_result.agent_loop_json_result(payload)

    assert summary["agent_loop_research_recall_status"] == "ok"
    assert summary["agent_loop_research_recall_result_count"] == 1
    assert (
        summary["agent_loop_research_recall_content_policy"]
        == "research_report_artifact_preview_only"
    )
    assert summary["agent_loop_research_recall_retrieval_backend"] == "hybrid"
    assert summary["agent_loop_research_recall_dense_status"] == "ok"
    assert summary["agent_loop_research_recall_previews"] == [
        {
            "run_id": "run_research",
            "artifact_id": "artifact_report",
            "artifact_type": "research.report",
            "summary": "Stored research report preview.",
            "ref": {
                "ref_type": "artifact",
                "scope": "run",
                "run_id": "run_research",
                "artifact_id": "artifact_report",
            },
            "source_refs": [{"ref_type": "url", "url": "https://example.com"}],
            "provenance": {"execution_id": "exec_research"},
        }
    ]
    assert "raw report body" not in str(summary)


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


def test_capacity_rendering_prints_research_recall_plain_fields(capsys):
    payload = {
        "status_reason": "launchable",
        "selection": {
            "capacity_id": "research.recall",
            "status": "ready_to_call",
        },
        "capability_launch_plan": {"status": "launchable"},
        "agent_loop": {
            "tick_result": {
                "planner_result": {
                    "step_result": {
                        "action_result": {
                            "capability_run": {
                                "capability_id": "research.recall",
                                "research_recall": {
                                    "status": "ok",
                                    "content_policy": (
                                        "research_report_artifact_preview_only"
                                    ),
                                    "retrieval": {
                                        "backend": "hybrid",
                                        "dense_status": "ok",
                                    },
                                    "results": [
                                        {
                                            "run_id": "run_research",
                                            "artifact_id": "artifact_report",
                                            "artifact_type": "research.report",
                                            "summary": "Stored research report preview.",
                                        }
                                    ],
                                },
                            }
                        }
                    }
                }
            }
        },
    }

    capacity_rendering.print_capacity_plan_plain(payload)

    output = capsys.readouterr().out
    assert "agent_loop_research_recall_status: ok" in output
    assert "agent_loop_research_recall_result_count: 1" in output
    assert "agent_loop_research_recall_retrieval: hybrid/ok" in output
