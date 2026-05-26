"""LLM action decision 中每种 action kind 的校验和处理逻辑."""

from __future__ import annotations

import shlex
from typing import Any

from ..flow import CodexSupervisorReport
from .constants import (
    LLM_ASK_USER_CONTEXT_STATUSES,
    LLM_RESUME_PROMPT_KINDS,
    LLM_WORKER_PROFILES,
)
from .guards import (
    ask_user_goal,
    ask_user_target,
    delete_worktree_candidate,
    goal_target_name,
    has_context_check_for_goal,
    has_context_check_for_target,
    has_resume_target,
    has_running_managed_worker,
    suggested_target_name,
)
from .payload import (
    optional_payload_string,
    required_payload_bool,
    required_payload_string,
)
from .suggestions import (
    _call_capacity_decision,
    _command_suggestion_for_kind,
    _suggestion_string,
)
from .workspace import (
    _available_workspaces,
    _default_workspace,
    _has_managed_target,
    _has_workspace_action_suggestion,
    _requires_workspace_action_suggestion,
)


def handle_resume_session(
    payload: dict[str, Any],
    report: CodexSupervisorReport,
    action_command_suggestions: list[dict[str, str]],
    target_name: str | None,
) -> dict[str, Any]:
    session_id = required_payload_string(payload, "session_id")
    if not has_resume_target(report, session_id):
        raise ValueError(f"unknown resumable session for LLM action: {session_id}")
    prompt_kind = optional_payload_string(payload, "prompt_kind") or "send_continue"
    if prompt_kind not in LLM_RESUME_PROMPT_KINDS:
        supported = ", ".join(LLM_RESUME_PROMPT_KINDS)
        raise ValueError(f"unsupported resume prompt_kind: {prompt_kind}; allowed: {supported}")
    command_suggestion = _command_suggestion_for_kind(
        action_command_suggestions,
        "resume_session",
        session_id=session_id,
        prompt_kind=prompt_kind,
    )
    if command_suggestion is None:
        raise ValueError("no command suggestion for LLM action: resume_session")
    return {
        "session_id": session_id,
        "prompt_kind": prompt_kind,
        "target_name": target_name or command_suggestion.get("target_name"),
        "command_suggestion": command_suggestion,
    }


def handle_launch_session(
    payload: dict[str, Any],
    report: CodexSupervisorReport,
    action_command_suggestions: list[dict[str, str]],
    target_name: str | None,
) -> dict[str, Any]:
    target_name = target_name or "planner-session"
    if has_running_managed_worker(report, target_name):
        raise ValueError(f"target already has running managed worker: {target_name}")
    existing_launch_suggestion = _command_suggestion_for_kind(
        action_command_suggestions,
        "launch_session",
        target_name=target_name,
    )
    cwd = (
        optional_payload_string(payload, "cwd")
        or _suggestion_string(existing_launch_suggestion, "cwd")
        or _default_workspace(report, action_command_suggestions)
    )
    if cwd is None or cwd not in _available_workspaces(
        report,
        action_command_suggestions,
    ):
        raise ValueError(f"unknown workspace for LLM action: {cwd}")
    if _requires_workspace_action_suggestion(cwd) and not _has_workspace_action_suggestion(
        action_command_suggestions,
        "launch_session",
        cwd,
    ):
        raise ValueError("no command suggestion for LLM action: launch_session")
    prompt = optional_payload_string(payload, "prompt") or _suggestion_string(
        existing_launch_suggestion,
        "prompt",
    )
    if prompt is None:
        raise ValueError("LLM action field is required: prompt")
    worker_profile = optional_payload_string(payload, "worker_profile")
    if worker_profile is not None and worker_profile not in LLM_WORKER_PROFILES:
        supported = ", ".join(LLM_WORKER_PROFILES)
        raise ValueError(
            f"unsupported worker_profile: {worker_profile}; allowed: {supported}"
        )
    command_suggestion = _launch_session_command_suggestion(
        target_name=target_name,
        cwd=cwd,
        prompt=prompt,
        worker_profile=worker_profile,
    )
    return {
        "target_name": target_name,
        "cwd": cwd,
        "prompt": prompt,
        "worker_profile": worker_profile,
        "command_suggestion": command_suggestion,
    }


def handle_request_context(
    payload: dict[str, Any],
    report: CodexSupervisorReport,
    action_command_suggestions: list[dict[str, str]],
) -> dict[str, Any]:
    cwd = optional_payload_string(payload, "cwd") or _default_workspace(
        report,
        action_command_suggestions,
    )
    if cwd is None or cwd not in _available_workspaces(
        report,
        action_command_suggestions,
    ):
        raise ValueError(f"unknown workspace for LLM action: {cwd}")
    if _requires_workspace_action_suggestion(cwd) and not _has_workspace_action_suggestion(
        action_command_suggestions,
        "request_context",
        cwd,
    ):
        raise ValueError("no command suggestion for LLM action: request_context")
    query = required_payload_string(payload, "query")
    command_suggestion = _request_context_command_suggestion(cwd=cwd, query=query)
    return {
        "cwd": cwd,
        "query": query,
        "command_suggestion": command_suggestion,
    }


def handle_ask_user(
    payload: dict[str, Any],
    report: CodexSupervisorReport,
    active_goals: list[dict[str, Any]] | None,
    recent_context_results: list[dict[str, Any]] | None,
    target_name: str | None,
) -> dict[str, Any]:
    goal_id = optional_payload_string(payload, "goal_id")
    goal_target: dict[str, Any] | None = None
    if goal_id is not None:
        goal_target = ask_user_goal(active_goals, goal_id)
        if goal_target is None:
            raise ValueError("ask_user requires an active blocked/needs_user goal")
        session_id = optional_payload_string(payload, "session_id") or f"goal:{goal_id}"
    else:
        session_id = required_payload_string(payload, "session_id")
        target = ask_user_target(report, session_id)
        if target is None:
            raise ValueError("ask_user requires a Codex decision request")
    if not required_payload_bool(payload, "codex_requested_decision"):
        raise ValueError("ask_user requires codex_requested_decision=true")
    if not required_payload_bool(payload, "instructions_exhausted"):
        raise ValueError("ask_user requires instructions_exhausted=true")
    if goal_target is not None:
        if not has_context_check_for_goal(recent_context_results, goal_target):
            raise ValueError("ask_user requires a context check")
    elif not has_context_check_for_target(recent_context_results, target):
        raise ValueError("ask_user requires a context check")
    context_status = required_payload_string(payload, "context_status")
    if context_status not in LLM_ASK_USER_CONTEXT_STATUSES:
        supported = ", ".join(LLM_ASK_USER_CONTEXT_STATUSES)
        raise ValueError(f"ask_user context_status must be one of: {supported}")
    question = required_payload_string(payload, "question")
    final_target_name = target_name or (
        goal_target_name(goal_target)
        if goal_target is not None
        else suggested_target_name(target)
    )
    return {
        "goal_id": goal_id,
        "session_id": session_id,
        "context_status": context_status,
        "question": question,
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "target_name": final_target_name,
        "command_suggestion": None,
    }


def handle_delete_worktree(
    payload: dict[str, Any],
    delete_worktree_candidates: list[dict[str, Any]] | None,
    target_name: str | None,
) -> dict[str, Any]:
    target_name = target_name or optional_payload_string(payload, "name")
    record_id = optional_payload_string(payload, "record_id")
    if not isinstance(target_name, str) or not target_name:
        raise ValueError("target_name is required for delete_worktree")
    if payload.get("confirm_delete_worktree") is not True:
        raise ValueError("delete_worktree requires confirm_delete_worktree=true")
    candidate = delete_worktree_candidate(
        delete_worktree_candidates,
        target_name=target_name,
        record_id=record_id,
    )
    if candidate is None:
        raise ValueError("delete_worktree target is not an allowed cleanup candidate")
    if candidate.get("archived") is not True:
        raise ValueError("delete_worktree candidate must be archived")
    if candidate.get("integration_group") != "already_integrated":
        raise ValueError("delete_worktree candidate must be already_integrated")
    candidate_cwd = candidate.get("cwd")
    cwd = candidate_cwd if isinstance(candidate_cwd, str) else None
    return {
        "target_name": target_name,
        "record_id": record_id,
        "cwd": cwd,
        "confirm_delete_worktree": True,
        "command_suggestion": None,
    }


def handle_call_capacity(
    payload: dict[str, Any],
    capacity_decisions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    capacity_id = required_payload_string(payload, "capacity_id")
    if _call_capacity_decision(capacity_decisions, capacity_id) is None:
        raise ValueError("call_capacity requires a ready capacity decision")
    return {
        "capacity_id": capacity_id,
        "command_suggestion": None,
    }


def handle_generic_managed_kind(
    payload: dict[str, Any],
    kind: str,
    report: CodexSupervisorReport,
    action_command_suggestions: list[dict[str, str]],
    target_name: str | None,
) -> dict[str, Any]:
    if target_name is None:
        raise ValueError(f"target_name is required for LLM action: {kind}")
    if not _has_managed_target(report, target_name):
        raise ValueError(f"unknown managed target for LLM action: {target_name}")
    command_suggestion = _command_suggestion_for_kind(
        action_command_suggestions,
        kind,
        target_name=target_name,
    )
    if command_suggestion is None:
        raise ValueError(f"no command suggestion for LLM action: {kind}")
    return {
        "command_suggestion": command_suggestion,
    }


# ---------------------------------------------------------------------------
# command suggestion 构造（launch / request_context 用）
# ---------------------------------------------------------------------------


def _launch_session_command_suggestion(
    *,
    target_name: str,
    cwd: str,
    prompt: str,
    worker_profile: str | None = None,
) -> dict[str, str]:
    return {
        "kind": "launch_session",
        "label": "启动新的 Codex 托管会话",
        "target_name": target_name,
        "cwd": cwd,
        "prompt": prompt,
        **({"worker_profile": worker_profile} if worker_profile else {}),
        "command": shlex.join(
            [
                "isotope-supervisor",
                "launch",
                "--name",
                target_name,
                "--cwd",
                cwd,
                "--prompt",
                prompt,
            ]
        ),
    }


def _request_context_command_suggestion(
    *,
    cwd: str,
    query: str,
) -> dict[str, str]:
    return {
        "kind": "request_context",
        "label": "检索项目上下文",
        "cwd": cwd,
        "query": query,
        "command": shlex.join(
            [
                "isotope-supervisor",
                "context",
                "--cwd",
                cwd,
                "--query",
                query,
            ]
        ),
    }
