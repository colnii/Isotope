"""Public results for Supervisor capacity execution payloads."""

from __future__ import annotations

from typing import Any, Mapping

from isotope.features.supervisor.notifications.context.projection import (
    request_context_agent_loop_result,
)


def agent_loop_json_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return public capacity handoff fields for JSON and plain output."""
    agent_loop = payload.get("agent_loop") if isinstance(payload, Mapping) else None
    result: dict[str, Any] = {"agent_loop_executed": isinstance(agent_loop, Mapping)}
    if not isinstance(agent_loop, Mapping):
        return result
    if agent_loop.get("kind") == "native_coding_agent_loop":
        result.update(_agent_loop_native_coding_result(agent_loop))
        return result

    handoff = agent_loop.get("handoff")
    if isinstance(handoff, Mapping):
        result["agent_loop_next_tick_kind"] = handoff.get("initial_next_tick_kind")
        result["agent_loop_post_step_phase"] = handoff.get("post_step_phase")
        result["agent_loop_post_step_should_continue"] = handoff.get(
            "post_step_should_continue"
        )
        result["agent_loop_post_step_stop_reason"] = handoff.get(
            "post_step_stop_reason"
        )

    planner_result = agent_loop.get("planner_output")
    if isinstance(planner_result, Mapping):
        result["agent_loop_planner_selected_step"] = planner_result.get(
            "selected_step"
        )

    tick_result = agent_loop.get("tick_result")
    if not isinstance(tick_result, Mapping):
        return result
    result["agent_loop_tick_status"] = tick_result.get("tick_status")
    after_policy = tick_result.get("after_policy")
    if isinstance(after_policy, Mapping):
        result["agent_loop_tick_after_stop_reason"] = after_policy.get(
            "must_stop_reason"
        )
    artifact_ref = _agent_loop_artifact_ref(tick_result)
    if isinstance(artifact_ref, Mapping):
        result["agent_loop_artifact_id"] = artifact_ref.get("artifact_id")
    capability_run = _agent_loop_capability_run(tick_result)
    if isinstance(capability_run, Mapping):
        screen_report = capability_run.get("screen_report")
        if isinstance(screen_report, Mapping):
            result.update(_agent_loop_screen_report_result(screen_report))
        result.update(_agent_loop_memory_query_result(capability_run))
        result.update(_agent_loop_memory_recall_result(capability_run))
        result.update(_agent_loop_research_search_result(capability_run))
        result.update(_agent_loop_research_promotion_result(capability_run))
        result.update(_agent_loop_project_status_result(capability_run))
        result.update(_agent_loop_terminal_exec_result(capability_run))
        result.update(request_context_agent_loop_result(capability_run))
        result.update(_agent_loop_self_repair_result(capability_run))
        result.update(_agent_loop_reviewed_apply_result(capability_run))
    return result


def _agent_loop_native_coding_result(agent_loop: Mapping[str, Any]) -> dict[str, Any]:
    reviewed_apply = agent_loop.get("reviewed_apply_request")
    changed_files = (
        reviewed_apply.get("changed_files")
        if isinstance(reviewed_apply, Mapping)
        else []
    )
    return {
        "agent_loop_coding_status": agent_loop.get("status"),
        "agent_loop_coding_workspace_id": agent_loop.get("workspace_id"),
        "agent_loop_coding_tick_count": agent_loop.get("tick_count"),
        "agent_loop_coding_context_calls": agent_loop.get("context_call_count"),
        "agent_loop_coding_source_workspace_write": agent_loop.get("source_workspace_write"),
        "agent_loop_coding_review_handle_available": isinstance(
            reviewed_apply,
            Mapping,
        ),
        "agent_loop_coding_reviewed_apply_capability_id": (
            reviewed_apply.get("capability_id")
            if isinstance(reviewed_apply, Mapping)
            else None
        ),
        "agent_loop_coding_reviewed_apply_changed_file_count": (
            len(changed_files) if isinstance(changed_files, list) else 0
        ),
    }


def agent_loop_handoff_result(
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


def _agent_loop_screen_report_result(
    screen_report: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "agent_loop_screen_report_status": screen_report.get("status")
    }
    screen_result = screen_report.get("summary")
    if not isinstance(screen_result, Mapping):
        return result
    result["agent_loop_screen_observe_status"] = screen_result.get("observe_status")
    result["agent_loop_screen_control_status"] = screen_result.get("control_status")
    result["agent_loop_screen_screenshot_available"] = screen_result.get(
        "screenshot_available"
    )
    result["agent_loop_screen_interferes_with_screen"] = screen_result.get(
        "interferes_with_screen"
    )
    return result


def _agent_loop_memory_query_result(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "memory.query":
        return {}
    memory_query = capability_run.get("memory_query")
    if not isinstance(memory_query, Mapping):
        return {}
    results = memory_query.get("results")
    result: dict[str, Any] = {
        "agent_loop_memory_query_status": memory_query.get("status"),
        "agent_loop_memory_query_result_count": (
            len(results) if isinstance(results, list) else 0
        ),
    }
    content_policy = memory_query.get("content_policy")
    if isinstance(content_policy, str) and content_policy:
        result["agent_loop_memory_query_content_policy"] = content_policy
    return result


def _agent_loop_memory_recall_result(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "memory.recall":
        return {}
    memory_recall = capability_run.get("memory_recall")
    if not isinstance(memory_recall, Mapping):
        return {}
    results = memory_recall.get("results")
    result: dict[str, Any] = {
        "agent_loop_memory_recall_status": memory_recall.get("status"),
        "agent_loop_memory_recall_result_count": (
            len(results) if isinstance(results, list) else 0
        ),
    }
    content_policy = memory_recall.get("content_policy")
    if isinstance(content_policy, str) and content_policy:
        result["agent_loop_memory_recall_content_policy"] = content_policy
    return result


def _agent_loop_research_search_result(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "research.search":
        return {}
    research_search = capability_run.get("research_search")
    if not isinstance(research_search, Mapping):
        return {}
    result: dict[str, Any] = {
        "agent_loop_research_search_status": research_search.get("status"),
        "agent_loop_research_provider": research_search.get("provider"),
        "agent_loop_research_source_count": research_search.get("source_count"),
        "agent_loop_research_artifact_count": research_search.get("artifact_count"),
    }
    report_summary = research_search.get("report_summary")
    if isinstance(report_summary, str) and report_summary:
        result["agent_loop_research_report"] = report_summary
    content_status = research_search.get("content_status")
    if isinstance(content_status, str) and content_status:
        result["agent_loop_research_content_status"] = content_status
    content_note = research_search.get("content_note")
    if isinstance(content_note, str) and content_note:
        result["agent_loop_research_content_note"] = content_note
    source_previews = research_search.get("source_previews")
    if isinstance(source_previews, list):
        result["agent_loop_research_source_previews"] = source_previews[:5]
    error = research_search.get("error")
    if isinstance(error, Mapping):
        result["agent_loop_research_error_code"] = error.get("code")
        result["agent_loop_research_error_message"] = error.get("message")
        result["agent_loop_research_error_retryable"] = error.get("retryable")
    return result


def _agent_loop_research_promotion_result(
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


def _agent_loop_terminal_exec_result(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "terminal.exec":
        return {}
    terminal = capability_run.get("terminal_exec")
    if not isinstance(terminal, Mapping):
        return {}
    result: dict[str, Any] = {
        "agent_loop_terminal_exec_status": terminal.get("status"),
        "agent_loop_terminal_exec_argv0": terminal.get("argv0"),
        "agent_loop_terminal_exec_approval_mode": terminal.get("approval_mode"),
    }
    for source_key, result_key in (
        ("approval_id", "agent_loop_terminal_exec_approval_id"),
        ("artifact_ref", "agent_loop_terminal_exec_artifact_ref"),
    ):
        value = terminal.get(source_key)
        if value:
            result[result_key] = value
    return result


def _agent_loop_reviewed_apply_result(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "coding_task.apply_reviewed_diff":
        return {}
    reviewed_apply = capability_run.get("reviewed_apply")
    if not isinstance(reviewed_apply, Mapping):
        return {}
    applied_files = reviewed_apply.get("applied_files")
    changed_files = reviewed_apply.get("changed_files")
    return {
        "agent_loop_reviewed_apply_status": reviewed_apply.get("status"),
        "agent_loop_reviewed_apply_workspace_id": reviewed_apply.get("workspace_id"),
        "agent_loop_reviewed_apply_applied_files": (
            list(applied_files) if isinstance(applied_files, list) else []
        ),
        "agent_loop_reviewed_apply_changed_file_count": (
            len(changed_files) if isinstance(changed_files, list) else 0
        ),
        "agent_loop_reviewed_apply_blocked_reason": reviewed_apply.get("blocked_reason"),
        "agent_loop_reviewed_apply_source_workspace_write": reviewed_apply.get(
            "source_workspace_write"
        ),
    }


def _agent_loop_project_status_result(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "supervisor.project_status":
        return {}
    project_status = capability_run.get("project_state")
    if not isinstance(project_status, Mapping):
        return {}
    counts = project_status.get("counts")
    self_repair_workers = project_status.get("self_repair_workers")
    latest_self_repair = project_status.get("latest_self_repair")
    open_capability_gaps = project_status.get("open_capability_gaps")
    latest_mapping = (
        latest_self_repair if isinstance(latest_self_repair, Mapping) else {}
    )
    return {
        "agent_loop_project_status_status": capability_run.get("status"),
        "agent_loop_project_status_snapshot_id": project_status.get("snapshot_id"),
        "agent_loop_project_status_counts": dict(counts) if isinstance(counts, Mapping) else {},
        "agent_loop_project_status_self_repair_count": (
            len(self_repair_workers) if isinstance(self_repair_workers, list) else 0
        ),
        "agent_loop_project_status_open_capability_gap_count": (
            len(open_capability_gaps) if isinstance(open_capability_gaps, list) else 0
        ),
        "agent_loop_project_status_latest_self_repair_name": (
            latest_mapping.get("name")
        ),
        "agent_loop_project_status_latest_self_repair_status": (
            latest_mapping.get("protocol_status")
        ),
        "agent_loop_project_status_latest_self_repair_merge_suitable": (
            latest_mapping.get("merge_suitable")
        ),
    }


def _agent_loop_self_repair_result(
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
