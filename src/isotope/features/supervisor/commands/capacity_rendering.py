"""Plain terminal rendering for Supervisor capacity command payloads."""

from __future__ import annotations

from typing import Any, Mapping

from isotope.features.supervisor.commands.capacity_summary import agent_loop_json_summary


def print_capacity_plan_plain(payload: Mapping[str, Any]) -> None:
    selection = payload.get("selection") if isinstance(payload, Mapping) else {}
    launch_plan = (
        payload.get("capability_launch_plan") if isinstance(payload, Mapping) else {}
    )
    print("Supervisor capacity plan")
    capacity_id = (
        selection.get("capacity_id") if isinstance(selection, Mapping) else "unknown"
    )
    selection_status = (
        selection.get("status") if isinstance(selection, Mapping) else "unknown"
    )
    launch_status = (
        launch_plan.get("status") if isinstance(launch_plan, Mapping) else "unknown"
    )
    status_reason = payload.get("status_reason", "unknown")
    print(f"capacity_id: {capacity_id}")
    print(f"selection_status: {selection_status}")
    print(f"status_reason: {status_reason}")
    print(f"launch_status: {launch_status}")
    supervisor_decision = payload.get("supervisor_decision")
    if isinstance(supervisor_decision, Mapping):
        print(
            "supervisor_decision_next_action: "
            f"{supervisor_decision.get('next_action')}"
        )
    _print_capacity_blockers(payload, selection=selection, launch_plan=launch_plan)
    agent_loop_summary = agent_loop_json_summary(payload)
    print(f"agent_loop_executed: {agent_loop_summary['agent_loop_executed']}")
    if agent_loop_summary["agent_loop_executed"]:
        print(
            "agent_loop_next_tick_kind: "
            f"{agent_loop_summary.get('agent_loop_next_tick_kind')}"
        )
        print(
            "agent_loop_planner_selected_step: "
            f"{agent_loop_summary.get('agent_loop_planner_selected_step')}"
        )
        print(
            f"agent_loop_tick_status: {agent_loop_summary.get('agent_loop_tick_status')}"
        )
        print(
            "agent_loop_tick_after_stop_reason: "
            f"{agent_loop_summary.get('agent_loop_tick_after_stop_reason')}"
        )
        artifact_id = agent_loop_summary.get("agent_loop_artifact_id")
        if artifact_id is not None:
            print(f"agent_loop_artifact_ref: {artifact_id}")
        print(
            "agent_loop_post_step_phase: "
            f"{agent_loop_summary.get('agent_loop_post_step_phase')}"
        )
        print(
            "agent_loop_post_step_should_continue: "
            f"{agent_loop_summary.get('agent_loop_post_step_should_continue')}"
        )
        print(
            "agent_loop_post_step_stop_reason: "
            f"{agent_loop_summary.get('agent_loop_post_step_stop_reason')}"
        )
        memory_query_status = agent_loop_summary.get("agent_loop_memory_query_status")
        if memory_query_status is not None:
            print(f"agent_loop_memory_query_status: {memory_query_status}")
            print(
                "agent_loop_memory_query_result_count: "
                f"{agent_loop_summary.get('agent_loop_memory_query_result_count')}"
            )
            content_policy = agent_loop_summary.get(
                "agent_loop_memory_query_content_policy"
            )
            if content_policy is not None:
                print(
                    "agent_loop_memory_query_content_policy: "
                    f"{content_policy}"
                )
        research_status = agent_loop_summary.get("agent_loop_research_search_status")
        if research_status is not None:
            print(f"agent_loop_research_search_status: {research_status}")
            print(
                "agent_loop_research_provider: "
                f"{agent_loop_summary.get('agent_loop_research_provider')}"
            )
            print(
                "agent_loop_research_source_count: "
                f"{agent_loop_summary.get('agent_loop_research_source_count')}"
            )
            print(
                "agent_loop_research_artifact_count: "
                f"{agent_loop_summary.get('agent_loop_research_artifact_count')}"
            )
        promotion_status = agent_loop_summary.get(
            "agent_loop_research_promotion_status"
        )
        if promotion_status is not None:
            print(f"agent_loop_research_promotion_status: {promotion_status}")
            print(
                "agent_loop_research_promotion_action_type: "
                f"{agent_loop_summary.get('agent_loop_research_promotion_action_type')}"
            )
            print(
                "agent_loop_research_promotion_memory_write: "
                f"{agent_loop_summary.get('agent_loop_research_promotion_memory_write')}"
            )
            quality_gate_status = agent_loop_summary.get(
                "agent_loop_research_promotion_quality_gate_status"
            )
            if quality_gate_status is not None:
                print(
                    "agent_loop_research_promotion_quality_gate_status: "
                    f"{quality_gate_status}"
                )


def _print_capacity_blockers(
    payload: Mapping[str, Any],
    *,
    selection: Any,
    launch_plan: Any,
) -> None:
    blocked_reason = payload.get("capacity_blocked_reason")
    if isinstance(blocked_reason, str) and blocked_reason:
        print(f"capacity_blocked_reason: {blocked_reason}")
    if payload.get("status_reason") == "needs_input" and isinstance(selection, Mapping):
        missing_inputs = selection.get("missing_inputs")
        if isinstance(missing_inputs, list) and missing_inputs:
            print(f"capacity_missing_inputs: {_comma_join_strings(missing_inputs)}")
    if payload.get("status_reason") == "not_launchable" and isinstance(
        launch_plan,
        Mapping,
    ):
        blocking_reasons = launch_plan.get("blocking_reasons")
        if isinstance(blocking_reasons, list) and blocking_reasons:
            print(f"launch_blocking_reasons: {_comma_join_strings(blocking_reasons)}")


def _comma_join_strings(values: list[Any]) -> str:
    return ", ".join(str(value) for value in values if isinstance(value, str))
