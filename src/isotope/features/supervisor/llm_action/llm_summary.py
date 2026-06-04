"""Codex Supervisor 的 LLM summary（大模型摘要）和 action decision 工具.

本模块是 facade：summary 生成 + action decision 调度 + 历史 import path 兼容 re-export.
实际实现分布在各子模块中（llm_action_*）。
"""

from __future__ import annotations

from typing import Any

from isotope.llm.prompts import load_system_prompt, render_json_prompt_template

from ..flow import CodexSupervisorReport
from .guards import (
    has_any_llm_target as _has_any_llm_target,
    is_completed_session as _is_completed_session,
)
from .payload import (
    extract_json_object as _extract_json_object,
    normalize_llm_action_payload as _normalize_llm_action_payload,
    optional_payload_string as _optional_payload_string,
    required_payload_string as _required_payload_string,
)
from .prompt import (
    LLM_ACTION_ALLOWED_KINDS,
    build_llm_action_messages,
)
from .llm_pool import (
    PoolEntry,
    PooledSummaryProvider,
    SummaryProvider,
    resolve_summary_provider_from_env,
)
from .context_payload import (
    _active_goal_payload,
    _blocked_context_priority,
    _candidate_target_payloads,
    _clip,
    _context_request_history,
    _worker_review_context_payload,
)
from .kind_handlers import (
    handle_ask_user,
    handle_call_capacity,
    handle_delete_worktree,
    handle_generic_managed_kind,
    handle_launch_session,
    handle_request_context,
    handle_resume_session,
)
from .suggestions import (
    _active_goal_scoped_command_suggestions,
    _command_suggestion_for_kind,
    _command_targets_name,
    _resumable_session_ids_from_suggestions,
    _running_worker_planner_priority,
    _running_worker_scoped_command_suggestions,
)
from .workspace import (
    _available_workspaces,
)

# ---------------------------------------------------------------------------
# Summary API
# ---------------------------------------------------------------------------


def build_llm_summary_messages(report: CodexSupervisorReport) -> list[dict[str, str]]:
    compact_sessions = [
        {
            "session_id": session.session_id,
            "cwd": session.cwd,
            "git_branch": session.git_branch,
            "status": session.status_label,
            "reason": session.reason,
            "status_evidence": session.status_evidence,
            "source_size_bytes": session.source_size_bytes,
            "age_seconds": session.age_seconds,
            "managed": session.managed,
            "managed_name": session.managed_name,
            "managed_backend": session.managed_backend,
            "managed_tmux_session": session.managed_tmux_session,
            "managed_bell": session.managed_bell,
            "managed_bell_event_at": session.managed_bell_event_at,
            "managed_bell_hook_installed": session.managed_bell_hook_installed,
            "managed_terminal_ready": session.managed_terminal_ready,
            "supervisor_status": session.supervisor_status,
            "supervisor_summary": _clip(session.supervisor_summary),
            "supervisor_next": _clip(session.supervisor_next),
            "last_user": _clip(session.last_user_message),
            "last_reply": _clip(session.last_assistant_message),
        }
        for session in report.sessions
    ]
    return [
        {
            "role": "system",
            "content": load_system_prompt("supervisor_llm_summary"),
        },
        {
            "role": "user",
            "content": render_json_prompt_template(
                "supervisor_llm_summary_user",
                {
                    "generated_at": report.generated_at,
                    "recommendation": report.recommendation.to_dict(),
                    "sessions": compact_sessions,
                },
            ),
        },
    ]


def generate_llm_summary(
    report: CodexSupervisorReport,
    provider: SummaryProvider,
) -> str:
    return provider.summarize(build_llm_summary_messages(report))


# ---------------------------------------------------------------------------
# Action Decision API
# ---------------------------------------------------------------------------

_KINDS_THAT_REQUIRE_TARGET = frozenset(
    kind for kind in LLM_ACTION_ALLOWED_KINDS
    if kind not in (
        "monitor",
        "resume_session",
        "launch_session",
        "request_context",
        "ask_user",
        "delete_worktree",
        "call_capacity",
    )
)


def generate_llm_action_decision(
    report: CodexSupervisorReport,
    command_suggestions: list[dict[str, str]],
    provider: SummaryProvider,
    recent_context_results: list[dict[str, Any]] | None = None,
    active_goals: list[dict[str, Any]] | None = None,
    recent_decision_answers: list[dict[str, Any]] | None = None,
    worker_reviews: dict[str, Any] | None = None,
    delete_worktree_candidates: list[dict[str, Any]] | None = None,
    capacity_decisions: list[dict[str, Any]] | None = None,
    worker_lifecycle_decision: dict[str, Any] | None = None,
    worker_lifecycle_execution: dict[str, Any] | None = None,
    worker_lifecycle_execution_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action_command_suggestions = _active_goal_scoped_command_suggestions(
        command_suggestions,
        active_goals,
    )
    if not _has_any_llm_target(
        report,
        action_command_suggestions,
        delete_worktree_candidates=delete_worktree_candidates,
        available_workspaces=_available_workspaces(
            report,
            action_command_suggestions,
        ),
    ):
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
            "command_suggestion": None,
        }
    raw = provider.summarize(
        build_llm_action_messages(
            report,
            command_suggestions,
            recent_context_results,
            active_goals,
            recent_decision_answers,
            worker_reviews,
            delete_worktree_candidates,
            capacity_decisions,
            worker_lifecycle_decision,
            worker_lifecycle_execution,
            worker_lifecycle_execution_result,
        )
    )
    payload = _normalize_llm_action_payload(_extract_json_object(raw))
    kind = _required_payload_string(payload, "kind")
    if kind not in LLM_ACTION_ALLOWED_KINDS:
        supported = ", ".join(LLM_ACTION_ALLOWED_KINDS)
        raise ValueError(f"unsupported LLM action: {kind}; allowed: {supported}")
    target_name = _optional_payload_string(payload, "target_name")
    reason = _optional_payload_string(payload, "reason") or "LLM 建议执行该白名单动作。"

    if kind == "resume_session":
        extra = handle_resume_session(
            payload, report, action_command_suggestions, target_name,
        )
    elif kind == "launch_session":
        extra = handle_launch_session(
            payload, report, action_command_suggestions, target_name,
        )
    elif kind == "request_context":
        extra = handle_request_context(
            payload, report, action_command_suggestions,
        )
    elif kind == "ask_user":
        extra = handle_ask_user(
            payload, report, active_goals, recent_context_results, target_name,
        )
    elif kind == "delete_worktree":
        extra = handle_delete_worktree(
            payload, delete_worktree_candidates, target_name,
        )
    elif kind == "call_capacity":
        extra = handle_call_capacity(payload, capacity_decisions)
    elif kind in _KINDS_THAT_REQUIRE_TARGET:
        extra = handle_generic_managed_kind(
            payload, kind, report, action_command_suggestions, target_name,
        )
    else:
        command_suggestion = _command_suggestion_for_kind(
            action_command_suggestions,
            kind,
        )
        extra = {"command_suggestion": command_suggestion}

    return {
        "kind": kind,
        "target_name": extra.pop("target_name", target_name),
        "reason": reason,
        **{k: v for k, v in extra.items() if v is not None or k == "command_suggestion"},
    }
