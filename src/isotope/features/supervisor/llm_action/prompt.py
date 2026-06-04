"""LLM action prompt（动作提示词）builder for Codex Supervisor."""

from __future__ import annotations

from typing import Any

from isotope.llm.prompts import load_system_prompt, render_json_prompt_template

from ..flow import CodexSupervisorReport

LLM_ACTION_ALLOWED_KINDS = (
    "monitor",
    "send_status",
    "send_continue",
    "resume_session",
    "launch_session",
    "request_context",
    "ask_user",
    "delete_worktree",
    "call_capacity",
)


def build_llm_action_messages(
    report: CodexSupervisorReport,
    command_suggestions: list[dict[str, str]],
    recent_context_results: list[dict[str, Any]] | None = None,
    active_goals: list[dict[str, Any]] | None = None,
    recent_decision_answers: list[dict[str, Any]] | None = None,
    worker_reviews: dict[str, Any] | None = None,
    delete_worktree_candidates: list[dict[str, Any]] | None = None,
    capacity_decisions: list[dict[str, Any]] | None = None,
    worker_lifecycle_decision: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build the prompt for guarded LLM planning."""
    from . import llm_summary as _summary

    _active_goal_scoped_command_suggestions = (
        _summary._active_goal_scoped_command_suggestions
    )
    _active_goal_payload = _summary._active_goal_payload
    _available_workspaces = _summary._available_workspaces
    _blocked_context_priority = _summary._blocked_context_priority
    _candidate_target_payloads = _summary._candidate_target_payloads
    _context_request_history = _summary._context_request_history
    _is_completed_session = _summary._is_completed_session
    _resumable_session_ids_from_suggestions = (
        _summary._resumable_session_ids_from_suggestions
    )
    _running_worker_planner_priority = _summary._running_worker_planner_priority
    _running_worker_scoped_command_suggestions = (
        _summary._running_worker_scoped_command_suggestions
    )
    _worker_review_context_payload = _summary._worker_review_context_payload
    prompt_command_suggestions = _active_goal_scoped_command_suggestions(
        command_suggestions,
        active_goals,
    )
    planner_priority = _running_worker_planner_priority(
        report,
        active_goals=active_goals,
    )
    prompt_command_suggestions = _running_worker_scoped_command_suggestions(
        prompt_command_suggestions,
        planner_priority=planner_priority,
    )
    resumable_session_ids = _resumable_session_ids_from_suggestions(
        prompt_command_suggestions
    )
    resumable_session_id_set = set(resumable_session_ids)
    candidate_targets = _candidate_target_payloads(
        report,
        resumable_session_ids=resumable_session_id_set,
    )
    completed_session_ids = [
        session.session_id for session in report.sessions if _is_completed_session(session)
    ]
    context_request_history = _context_request_history(recent_context_results)
    blocked_context_priority = _blocked_context_priority(
        active_goals,
        prompt_command_suggestions,
        context_request_history,
    )
    return [
        {
            "role": "system",
            "content": load_system_prompt("supervisor_llm_action"),
        },
        {
            "role": "user",
            "content": render_json_prompt_template(
                "supervisor_llm_action_user",
                {
                    "allowed_kinds": list(LLM_ACTION_ALLOWED_KINDS),
                    "available_workspaces": _available_workspaces(
                        report,
                        prompt_command_suggestions,
                    ),
                    "candidate_targets": candidate_targets,
                    "active_goals": _active_goal_payload(
                        active_goals,
                        candidate_targets,
                    ),
                    "resumable_session_ids": resumable_session_ids,
                    "completed_session_ids": completed_session_ids,
                    "command_suggestions": prompt_command_suggestions,
                    "recent_context_results": recent_context_results or [],
                    "recent_decision_answers": recent_decision_answers or [],
                    "context_request_history": context_request_history,
                    "planner_priority": planner_priority,
                    "blocked_context_priority": blocked_context_priority,
                    "capacity_decisions": capacity_decisions or [],
                    "delete_worktree_candidates": delete_worktree_candidates or [],
                    "worker_lifecycle_contract": _worker_lifecycle_contract(
                        worker_lifecycle_decision
                    ),
                    "generated_at": report.generated_at,
                    "recommendation": report.recommendation.to_dict(),
                    "worker_reviews": _worker_review_context_payload(worker_reviews),
                },
            ),
        },
    ]


def _worker_lifecycle_contract(
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "kind": "worker_lifecycle_contract",
        "decision": decision,
        "rules": [
            "Treat worker_lifecycle_decision as program-owned lifecycle state.",
            "Do not repeat actions already present in execution.",
            "Do not repeat timeline entries where executed is true.",
            "If policy_status is program_resolved, prefer monitor unless remaining_step names an allowed guarded action.",
            "If policy_status is human_required, use ask_user or request_context only when the decision gate allows it.",
            "If policy_status is model_required, choose from the normal allowed action whitelist.",
            "If next_step is launch_merge_worker, prefer the existing merge dispatch path.",
            "If next_step is archive_worker or cleanup_worktree, prefer monitor unless a matching guarded cleanup candidate is present.",
            "Use LLM actions only for gaps, human decisions, or explicitly allowed follow-up actions.",
        ],
    }
