"""Public summaries for Supervisor capacity execution payloads."""

from __future__ import annotations

from typing import Any, Mapping


def agent_loop_json_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return public capacity handoff fields for JSON and plain output."""
    agent_loop = payload.get("agent_loop") if isinstance(payload, Mapping) else None
    summary: dict[str, Any] = {"agent_loop_executed": isinstance(agent_loop, Mapping)}
    if not isinstance(agent_loop, Mapping):
        return summary
    if agent_loop.get("kind") == "native_coding_agent_loop":
        summary.update(_agent_loop_native_coding_summary(agent_loop))
        return summary

    handoff = agent_loop.get("handoff")
    if isinstance(handoff, Mapping):
        summary["agent_loop_next_tick_kind"] = handoff.get("initial_next_tick_kind")
        summary["agent_loop_post_step_phase"] = handoff.get("post_step_phase")
        summary["agent_loop_post_step_should_continue"] = handoff.get(
            "post_step_should_continue"
        )
        summary["agent_loop_post_step_stop_reason"] = handoff.get(
            "post_step_stop_reason"
        )

    planner_summary = agent_loop.get("planner_output_summary")
    if isinstance(planner_summary, Mapping):
        summary["agent_loop_planner_selected_step"] = planner_summary.get(
            "selected_step"
        )

    tick_result = agent_loop.get("tick_result")
    if not isinstance(tick_result, Mapping):
        return summary
    summary["agent_loop_tick_status"] = tick_result.get("tick_status")
    after_policy = tick_result.get("after_policy")
    if isinstance(after_policy, Mapping):
        summary["agent_loop_tick_after_stop_reason"] = after_policy.get(
            "must_stop_reason"
        )
    artifact_ref = _agent_loop_artifact_ref(tick_result)
    if isinstance(artifact_ref, Mapping):
        summary["agent_loop_artifact_id"] = artifact_ref.get("artifact_id")
    capability_run = _agent_loop_capability_run(tick_result)
    if isinstance(capability_run, Mapping):
        screen_report = capability_run.get("screen_report")
        if isinstance(screen_report, Mapping):
            summary.update(_agent_loop_screen_report_summary(screen_report))
        summary.update(_agent_loop_memory_query_summary(capability_run))
        summary.update(_agent_loop_research_search_summary(capability_run))
        summary.update(_agent_loop_research_promotion_summary(capability_run))
        summary.update(_agent_loop_project_status_summary(capability_run))
        summary.update(_agent_loop_self_repair_summary(capability_run))
    return summary


def _agent_loop_native_coding_summary(agent_loop: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "agent_loop_coding_status": agent_loop.get("status"),
        "agent_loop_coding_workspace_id": agent_loop.get("workspace_id"),
        "agent_loop_coding_tick_count": agent_loop.get("tick_count"),
        "agent_loop_coding_context_calls": agent_loop.get("context_call_count"),
        "agent_loop_coding_source_workspace_write": agent_loop.get("source_workspace_write"),
    }


def agent_loop_handoff_summary(
    tick_policy_before: Mapping[str, Any],
    tick_policy_after: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "initial_next_tick_kind": tick_policy_before.get("max_next_tick_kind"),
        "post_step_phase": tick_policy_after.get("phase"),
        "post_step_should_continue": tick_policy_after.get("should_continue"),
        "post_step_stop_reason": tick_policy_after.get("must_stop_reason"),
    }


def _agent_loop_artifact_ref(tick_result: Mapping[str, Any]) -> Mapping[str, Any] | None:
    planner_result = tick_result.get("planner_result")
    step_result = (
        planner_result.get("step_result")
        if isinstance(planner_result, Mapping)
        else None
    )
    action_result = (
        step_result.get("action_result") if isinstance(step_result, Mapping) else None
    )
    artifact_ref = (
        action_result.get("artifact_ref") if isinstance(action_result, Mapping) else None
    )
    return artifact_ref if isinstance(artifact_ref, Mapping) else None


def _agent_loop_capability_run(
    tick_result: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    planner_result = tick_result.get("planner_result")
    step_result = (
        planner_result.get("step_result")
        if isinstance(planner_result, Mapping)
        else None
    )
    action_result = (
        step_result.get("action_result") if isinstance(step_result, Mapping) else None
    )
    capability_run = (
        action_result.get("capability_run")
        if isinstance(action_result, Mapping)
        else None
    )
    return capability_run if isinstance(capability_run, Mapping) else None


def _agent_loop_screen_report_summary(
    screen_report: Mapping[str, Any],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "agent_loop_screen_report_status": screen_report.get("status")
    }
    screen_summary = screen_report.get("summary")
    if not isinstance(screen_summary, Mapping):
        return summary
    summary["agent_loop_screen_observe_status"] = screen_summary.get("observe_status")
    summary["agent_loop_screen_control_status"] = screen_summary.get("control_status")
    summary["agent_loop_screen_screenshot_available"] = screen_summary.get(
        "screenshot_available"
    )
    summary["agent_loop_screen_interferes_with_screen"] = screen_summary.get(
        "interferes_with_screen"
    )
    return summary


def _agent_loop_memory_query_summary(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "memory.query":
        return {}
    memory_query = capability_run.get("memory_query")
    if not isinstance(memory_query, Mapping):
        return {}
    results = memory_query.get("results")
    summary: dict[str, Any] = {
        "agent_loop_memory_query_status": memory_query.get("status"),
        "agent_loop_memory_query_result_count": (
            len(results) if isinstance(results, list) else 0
        ),
    }
    content_policy = memory_query.get("content_policy")
    if isinstance(content_policy, str) and content_policy:
        summary["agent_loop_memory_query_content_policy"] = content_policy
    return summary


def _agent_loop_research_search_summary(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "research.search":
        return {}
    research_search = capability_run.get("research_search")
    if not isinstance(research_search, Mapping):
        return {}
    summary: dict[str, Any] = {
        "agent_loop_research_search_status": research_search.get("status"),
        "agent_loop_research_provider": research_search.get("provider"),
        "agent_loop_research_source_count": research_search.get("source_count"),
        "agent_loop_research_artifact_count": research_search.get("artifact_count"),
    }
    report_summary = research_search.get("report_summary")
    if isinstance(report_summary, str) and report_summary:
        summary["agent_loop_research_report_summary"] = report_summary
    source_previews = research_search.get("source_previews")
    if isinstance(source_previews, list):
        summary["agent_loop_research_source_previews"] = source_previews[:5]
    error = research_search.get("error")
    if isinstance(error, Mapping):
        summary["agent_loop_research_error_code"] = error.get("code")
        summary["agent_loop_research_error_message"] = error.get("message")
        summary["agent_loop_research_error_retryable"] = error.get("retryable")
    return summary


def _agent_loop_research_promotion_summary(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "research.promote":
        return {}
    promotion = capability_run.get("research_promotion")
    if not isinstance(promotion, Mapping):
        return {}
    return {
        "agent_loop_research_promotion_status": promotion.get("status"),
        "agent_loop_research_promotion_action_type": promotion.get("action_type"),
        "agent_loop_research_promotion_memory_write": promotion.get("memory_write"),
        "agent_loop_research_promotion_quality_gate_status": promotion.get(
            "quality_gate_status"
        ),
    }


def _agent_loop_project_status_summary(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "supervisor.project_status":
        return {}
    project_status = capability_run.get("project_state_summary")
    if not isinstance(project_status, Mapping):
        return {}
    counts = project_status.get("counts")
    return {
        "agent_loop_project_status_status": capability_run.get("status"),
        "agent_loop_project_status_snapshot_id": project_status.get("snapshot_id"),
        "agent_loop_project_status_counts": dict(counts) if isinstance(counts, Mapping) else {},
    }


def _agent_loop_self_repair_summary(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "isotope.self_repair":
        return {}
    self_repair = capability_run.get("self_repair")
    if not isinstance(self_repair, Mapping):
        return {}
    managed = self_repair.get("managed")
    worktree = self_repair.get("worktree")
    return {
        "agent_loop_self_repair_status": self_repair.get("status"),
        "agent_loop_self_repair_managed_name": (
            managed.get("name") if isinstance(managed, Mapping) else None
        ),
        "agent_loop_self_repair_worker_role": (
            managed.get("worker_role") if isinstance(managed, Mapping) else None
        ),
        "agent_loop_self_repair_worktree_enabled": (
            worktree.get("enabled") if isinstance(worktree, Mapping) else None
        ),
        "agent_loop_self_repair_worktree_branch": (
            worktree.get("branch") if isinstance(worktree, Mapping) else None
        ),
    }
