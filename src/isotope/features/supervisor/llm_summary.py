"""Codex Supervisor 的 LLM summary（大模型摘要）和 action decision 工具."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from .flow import CodexSupervisorReport
from .llm_action_guards import (
    ask_user_goal as _ask_user_goal,
    ask_user_target as _ask_user_target,
    can_resume_session as _can_resume_session,
    delete_worktree_candidate as _delete_worktree_candidate,
    goal_requests_user_decision as _goal_requests_user_decision,
    goal_target_name as _goal_target_name,
    has_any_llm_target as _has_any_llm_target,
    has_context_check_for_goal as _has_context_check_for_goal,
    has_context_check_for_target as _has_context_check_for_target,
    has_managed_process_target as _has_managed_process_target,
    has_managed_send_target as _has_managed_send_target,
    has_resume_target as _has_resume_target,
    has_running_managed_worker as _has_running_managed_worker,
    is_completed_session as _is_completed_session,
    is_llm_candidate_target as _is_llm_candidate_target,
    is_terminal_done_session as _is_terminal_done_session,
    session_requests_user_decision as _session_requests_user_decision,
    suggested_target_name as _suggested_target_name,
)
from .llm_action_payload import (
    extract_json_object as _extract_json_object,
    normalize_llm_action_payload as _normalize_llm_action_payload,
    optional_payload_string as _optional_payload_string,
    required_payload_bool as _required_payload_bool,
    required_payload_string as _required_payload_string,
)
from .llm_action_prompt import (
    LLM_ACTION_ALLOWED_KINDS,
    build_llm_action_messages,
)
from .llm_pool import (
    PoolEntry,
    PooledSummaryProvider,
    SummaryProvider,
    resolve_summary_provider_from_env,
)
from .merge_dispatch import DEFAULT_TARGET_NAME as MERGE_DISPATCH_TARGET_NAME

LARGE_RESUME_SOURCE_BYTES = 64 * 1024
LLM_RESUME_PROMPT_KINDS = ("send_status", "send_continue")
LLM_ASK_USER_CONTEXT_STATUSES = ("missing", "outdated", "conflict")
LLM_WORKER_PROFILES = ("coding", "light")


# Re-exported from ``llm_pool`` to keep the historical import path stable.


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
            "content": (
                "你是 Codex Supervisor 的中文摘要层。"
                "根据压缩后的会话状态，判断每个窗口在干什么、是否需要介入、"
                "优先处理哪个窗口。不要编造日志里没有的信息。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "generated_at": report.generated_at,
                    "recommendation": report.recommendation.to_dict(),
                    "sessions": compact_sessions,
                    "output_requirements": [
                        "用中文输出 3-6 行",
                        "每行都要短",
                        "说明优先处理建议",
                        "不要输出 JSON",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def generate_llm_summary(
    report: CodexSupervisorReport,
    provider: SummaryProvider,
) -> str:
    return provider.summarize(build_llm_summary_messages(report))


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
        )
    )
    payload = _normalize_llm_action_payload(_extract_json_object(raw))
    kind = _required_payload_string(payload, "kind")
    if kind not in LLM_ACTION_ALLOWED_KINDS:
        supported = ", ".join(LLM_ACTION_ALLOWED_KINDS)
        raise ValueError(f"unsupported LLM action: {kind}; allowed: {supported}")
    target_name = _optional_payload_string(payload, "target_name")
    reason = _optional_payload_string(payload, "reason") or "LLM 建议执行该白名单动作。"
    session_id: str | None = None
    prompt_kind: str | None = None
    goal_id: str | None = None
    worker_profile: str | None = None
    question: str | None = None
    context_status: str | None = None
    codex_requested_decision: bool | None = None
    instructions_exhausted: bool | None = None
    record_id: str | None = None
    confirm_delete_worktree: bool | None = None
    capacity_id: str | None = None
    if kind == "resume_session":
        session_id = _required_payload_string(payload, "session_id")
        if not _has_resume_target(report, session_id):
            raise ValueError(f"unknown resumable session for LLM action: {session_id}")
        prompt_kind = _optional_payload_string(payload, "prompt_kind") or "send_continue"
        if prompt_kind not in LLM_RESUME_PROMPT_KINDS:
            supported = ", ".join(LLM_RESUME_PROMPT_KINDS)
            raise ValueError(f"unsupported resume prompt_kind: {prompt_kind}; allowed: {supported}")
        command_suggestion = _command_suggestion_for_kind(
            action_command_suggestions,
            kind,
            session_id=session_id,
            prompt_kind=prompt_kind,
        )
        if command_suggestion is None:
            raise ValueError(f"no command suggestion for LLM action: {kind}")
        target_name = target_name or command_suggestion.get("target_name")
    elif kind == "launch_session":
        target_name = target_name or "planner-session"
        if _has_running_managed_worker(report, target_name):
            raise ValueError(f"target already has running managed worker: {target_name}")
        existing_launch_suggestion = _command_suggestion_for_kind(
            action_command_suggestions,
            kind,
            target_name=target_name,
        )
        cwd = (
            _optional_payload_string(payload, "cwd")
            or _suggestion_string(existing_launch_suggestion, "cwd")
            or _default_workspace(
            report,
            action_command_suggestions,
            )
        )
        if cwd is None or cwd not in _available_workspaces(
            report,
            action_command_suggestions,
        ):
            raise ValueError(f"unknown workspace for LLM action: {cwd}")
        if _requires_workspace_action_suggestion(cwd) and not _has_workspace_action_suggestion(
            action_command_suggestions,
            kind,
            cwd,
        ):
            raise ValueError(f"no command suggestion for LLM action: {kind}")
        prompt = _optional_payload_string(payload, "prompt") or _suggestion_string(
            existing_launch_suggestion,
            "prompt",
        )
        if prompt is None:
            raise ValueError("LLM action field is required: prompt")
        worker_profile = _optional_payload_string(payload, "worker_profile")
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
    elif kind == "request_context":
        target_name = None
        cwd = _optional_payload_string(payload, "cwd") or _default_workspace(
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
            kind,
            cwd,
        ):
            raise ValueError(f"no command suggestion for LLM action: {kind}")
        query = _required_payload_string(payload, "query")
        command_suggestion = _request_context_command_suggestion(cwd=cwd, query=query)
    elif kind == "ask_user":
        goal_id = _optional_payload_string(payload, "goal_id")
        goal_target: dict[str, Any] | None = None
        if goal_id is not None:
            goal_target = _ask_user_goal(active_goals, goal_id)
            if goal_target is None:
                raise ValueError("ask_user requires an active blocked/needs_user goal")
            session_id = _optional_payload_string(payload, "session_id") or f"goal:{goal_id}"
        else:
            session_id = _required_payload_string(payload, "session_id")
            target = _ask_user_target(report, session_id)
            if target is None:
                raise ValueError("ask_user requires a Codex decision request")
        if not _required_payload_bool(payload, "codex_requested_decision"):
            raise ValueError("ask_user requires codex_requested_decision=true")
        if not _required_payload_bool(payload, "instructions_exhausted"):
            raise ValueError("ask_user requires instructions_exhausted=true")
        if goal_target is not None:
            if not _has_context_check_for_goal(recent_context_results, goal_target):
                raise ValueError("ask_user requires a context check")
        elif not _has_context_check_for_target(recent_context_results, target):
            raise ValueError("ask_user requires a context check")
        context_status = _required_payload_string(payload, "context_status")
        if context_status not in LLM_ASK_USER_CONTEXT_STATUSES:
            supported = ", ".join(LLM_ASK_USER_CONTEXT_STATUSES)
            raise ValueError(
                f"ask_user context_status must be one of: {supported}"
            )
        question = _required_payload_string(payload, "question")
        codex_requested_decision = True
        instructions_exhausted = True
        target_name = target_name or (
            _goal_target_name(goal_target)
            if goal_target is not None
            else _suggested_target_name(target)
        )
        command_suggestion = None
    elif kind == "delete_worktree":
        target_name = target_name or _optional_payload_string(payload, "name")
        record_id = _optional_payload_string(payload, "record_id")
        if not isinstance(target_name, str) or not target_name:
            raise ValueError("target_name is required for delete_worktree")
        if payload.get("confirm_delete_worktree") is not True:
            raise ValueError("delete_worktree requires confirm_delete_worktree=true")
        confirm_delete_worktree = True
        candidate = _delete_worktree_candidate(
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
        command_suggestion = None
    elif kind == "call_capacity":
        target_name = None
        capacity_id = _required_payload_string(payload, "capacity_id")
        if _call_capacity_decision(capacity_decisions, capacity_id) is None:
            raise ValueError("call_capacity requires a ready capacity decision")
        command_suggestion = None
    elif kind != "monitor":
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
    else:
        command_suggestion = _command_suggestion_for_kind(
            action_command_suggestions,
            kind,
        )
    return {
        "kind": kind,
        "target_name": target_name,
        **({"session_id": session_id} if session_id is not None else {}),
        **({"goal_id": goal_id} if goal_id is not None else {}),
        **({"capacity_id": capacity_id} if capacity_id is not None else {}),
        **({"prompt_kind": prompt_kind} if prompt_kind is not None else {}),
        **({"worker_profile": worker_profile} if worker_profile is not None else {}),
        **({"cwd": cwd} if kind == "launch_session" else {}),
        **({"prompt": prompt} if kind == "launch_session" else {}),
        **({"cwd": cwd} if kind == "request_context" else {}),
        **({"query": query} if kind == "request_context" else {}),
        **({"cwd": cwd} if kind == "delete_worktree" else {}),
        **({"question": question} if question is not None else {}),
        **({"record_id": record_id} if record_id is not None else {}),
        **(
            {"confirm_delete_worktree": confirm_delete_worktree}
            if confirm_delete_worktree is not None
            else {}
        ),
        **({"context_status": context_status} if context_status is not None else {}),
        **(
            {"codex_requested_decision": codex_requested_decision}
            if codex_requested_decision is not None
            else {}
        ),
        **(
            {"instructions_exhausted": instructions_exhausted}
            if instructions_exhausted is not None
            else {}
        ),
        "reason": reason,
        "command_suggestion": command_suggestion,
    }


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _worker_review_context_payload(
    worker_reviews: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(worker_reviews, dict):
        return {}
    workers = [
        _worker_review_prompt_item(worker)
        for worker in worker_reviews.get("workers", [])
        if isinstance(worker, dict)
    ]
    return {
        "status": worker_reviews.get("status"),
        "summary": worker_reviews.get("summary") or {},
        "decision_summary": worker_reviews.get("decision_summary") or {},
        "automation_candidates": _worker_review_automation_candidates_payload(
            worker_reviews.get("automation_candidates")
        ),
        "safety": worker_reviews.get("safety") or {},
        "workers": workers,
    }


def _worker_review_automation_candidates_payload(raw: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}
    payload: dict[str, list[dict[str, Any]]] = {}
    for bucket in (
        "review_then_merge",
        "continue_or_split",
        "archive_or_wait",
        "recover_or_archive",
    ):
        items = raw.get(bucket)
        if not isinstance(items, list):
            continue
        compact_items = [
            _worker_review_automation_candidate_item(item)
            for item in items[:5]
            if isinstance(item, dict)
        ]
        if compact_items:
            payload[bucket] = compact_items
    return payload


def _worker_review_automation_candidate_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": item.get("record_id"),
        "name": item.get("name"),
        "cwd": item.get("cwd"),
        "branch": item.get("branch"),
        "recommendation": item.get("recommendation"),
        "risk_level": item.get("risk_level"),
        "reason": _clip(item.get("reason")),
        "next_actions": item.get("next_actions") or [],
        "validation_commands": (item.get("validation_commands") or [])[:3],
        "reviewer_command": _clip(item.get("reviewer_command")),
    }


def _worker_review_prompt_item(worker: dict[str, Any]) -> dict[str, Any]:
    reviewer = worker.get("reviewer")
    reviewer_payload = reviewer if isinstance(reviewer, dict) else {}
    worktree = worker.get("worktree")
    worktree_payload = worktree if isinstance(worktree, dict) else {}
    changes = worker.get("changes")
    changes_payload = changes if isinstance(changes, dict) else {}
    protocol = worker.get("supervisor_protocol")
    protocol_payload = protocol if isinstance(protocol, dict) else {}
    return {
        "record_id": worker.get("record_id"),
        "name": worker.get("name"),
        "backend": worker.get("backend"),
        "process_running": worker.get("process_running"),
        "registry_status": worker.get("registry_status"),
        "cwd": worker.get("cwd"),
        "cwd_exists": worker.get("cwd_exists"),
        "worktree": {
            "exists": worktree_payload.get("exists"),
            "branch": worktree_payload.get("branch"),
            "inferred_branch": worktree_payload.get("inferred_branch"),
        },
        "supervisor_protocol": {
            "status": protocol_payload.get("status"),
            "summary": _clip(protocol_payload.get("summary")),
            "next": _clip(protocol_payload.get("next")),
        },
        "changes": {
            "status": changes_payload.get("status"),
            "summary": changes_payload.get("summary"),
            "files": changes_payload.get("files") or [],
            "stat": _clip(changes_payload.get("stat")),
        },
        "validation_commands": worker.get("validation_commands") or [],
        "next_decision": worker.get("next_decision") or {},
        "reviewer": {
            "needed": reviewer_payload.get("needed"),
            "reason": reviewer_payload.get("reason"),
            "command": reviewer_payload.get("command"),
            "must_check_risks": reviewer_payload.get("must_check_risks") or [],
        },
        "merge_hint": worker.get("merge_hint"),
    }


def _active_goal_scoped_command_suggestions(
    command_suggestions: list[dict[str, str]],
    active_goals: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    if not active_goals:
        return command_suggestions
    goal_names = {
        target_name
        for goal in active_goals
        if isinstance(goal, dict)
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str) and target_name
    }
    goal_texts = {
        text
        for goal in active_goals
        if isinstance(goal, dict)
        for text in (goal.get("goal"),)
        if isinstance(text, str) and text
    }
    scoped: list[dict[str, str]] = []
    for suggestion in command_suggestions:
        kind = suggestion.get("kind")
        if kind == "monitor":
            scoped.append(suggestion)
            continue
        if _command_suggestion_targets_goal(suggestion, goal_names, goal_texts):
            scoped.append(suggestion)
    return scoped


def _command_suggestion_targets_goal(
    suggestion: dict[str, str],
    goal_names: set[str],
    goal_texts: set[str],
) -> bool:
    target_name = suggestion.get("target_name")
    if isinstance(target_name, str) and target_name in goal_names:
        return True
    query = suggestion.get("query")
    if isinstance(query, str) and query in goal_texts:
        return True
    prompt = suggestion.get("prompt")
    if isinstance(prompt, str) and prompt in goal_texts:
        return True
    command = suggestion.get("command")
    return isinstance(command, str) and any(
        _command_targets_name(command, name) for name in goal_names
    )


def _running_worker_scoped_command_suggestions(
    command_suggestions: list[dict[str, str]],
    *,
    planner_priority: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if not planner_priority:
        return command_suggestions
    noisy_kinds = {"request_context", "launch_session", "resume_session", "watch_changes"}
    return [
        suggestion
        for suggestion in command_suggestions
        if suggestion.get("kind") not in noisy_kinds
    ]


def _running_worker_planner_priority(
    report: CodexSupervisorReport,
    *,
    active_goals: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    priorities: list[dict[str, Any]] = []
    running_by_name = _running_managed_worker_payload_by_name(report)
    merge_worker = running_by_name.get(MERGE_DISPATCH_TARGET_NAME)
    if merge_worker is not None:
        priorities.append(
            {
                "kind": "monitor",
                "reason": "running_merge_worker",
                "target_name": MERGE_DISPATCH_TARGET_NAME,
                "worker_session_id": merge_worker["session_id"],
                "message": "merge dispatch worker 正在运行，等待下一轮状态变化。",
            }
        )
    for goal in active_goals or []:
        if not isinstance(goal, dict):
            continue
        target_name = goal.get("target_name")
        if not isinstance(target_name, str) or not target_name:
            continue
        worker = running_by_name.get(target_name)
        if worker is None:
            continue
        priorities.append(
            {
                "kind": "monitor",
                "reason": "running_worker",
                "target_name": target_name,
                "goal_id": goal.get("goal_id"),
                "worker_session_id": worker["session_id"],
                "message": "active goal worker 正在运行，等待下一轮状态变化。",
            }
        )
    return priorities


def _running_managed_worker_payload_by_name(
    report: CodexSupervisorReport,
) -> dict[str, dict[str, Any]]:
    workers: dict[str, dict[str, Any]] = {}
    for session in report.sessions:
        name = getattr(session, "managed_name", None)
        if not isinstance(name, str) or not name:
            continue
        if not _is_running_managed_worker(session):
            continue
        workers[name] = {
            "session_id": session.session_id,
            "cwd": session.cwd,
            "status": session.status,
        }
    return workers


def _is_running_managed_worker(session: Any) -> bool:
    return bool(
        getattr(session, "managed", False)
        and getattr(session, "managed_name", None)
        and getattr(session, "managed_backend", None) != "tmux"
        and getattr(session, "status", None) == "working"
        and not _is_terminal_done_session(session)
    )


def _suggestion_string(
    suggestion: dict[str, str] | None,
    field: str,
) -> str | None:
    if not isinstance(suggestion, dict):
        return None
    value = suggestion.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _command_suggestion_for_kind(
    command_suggestions: list[dict[str, str]],
    kind: str,
    *,
    target_name: str | None = None,
    session_id: str | None = None,
    prompt_kind: str | None = None,
) -> dict[str, str] | None:
    for suggestion in command_suggestions:
        if suggestion.get("kind") != kind:
            continue
        if session_id is not None and suggestion.get("session_id") != session_id:
            continue
        if prompt_kind is not None and suggestion.get("prompt_kind") != prompt_kind:
            continue
        if target_name is not None and not _command_targets_name(
            suggestion.get("command", ""),
            target_name,
        ):
            continue
        return suggestion
    return None


def _call_capacity_decision(
    capacity_decisions: list[dict[str, Any]] | None,
    capacity_id: str,
) -> dict[str, Any] | None:
    for decision in capacity_decisions or []:
        if not isinstance(decision, dict):
            continue
        if decision.get("capacity_id") != capacity_id:
            continue
        if decision.get("next_action") != "call_capacity":
            continue
        if decision.get("can_execute_agent_loop") is not True:
            continue
        return decision
    return None


def _has_workspace_action_suggestion(
    command_suggestions: list[dict[str, str]],
    kind: str,
    cwd: str,
) -> bool:
    return any(
        suggestion.get("kind") == kind and suggestion.get("cwd") == cwd
        for suggestion in command_suggestions
    )


def _requires_workspace_action_suggestion(cwd: str) -> bool:
    return Path(cwd).expanduser().is_dir()


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


def _command_targets_name(command: str, target_name: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    for index, part in enumerate(parts[:-1]):
        if part == "--name" and parts[index + 1] == target_name:
            return True
    return False


def _has_managed_target(report: CodexSupervisorReport, target_name: str) -> bool:
    return any(
        _has_managed_send_target(session) and session.managed_name == target_name
        for session in report.sessions
    )


def _delete_worktree_target_cwd(
    report: CodexSupervisorReport,
    target_name: str,
) -> str | None:
    for session in report.sessions:
        if _suggested_target_name(session) == target_name:
            cwd = getattr(session, "cwd", None)
            return cwd if isinstance(cwd, str) and cwd else None
    return None


def _is_known_missing_worktree_target(
    report: CodexSupervisorReport,
    target_name: str,
    cwd: str,
) -> bool:
    if Path(cwd).expanduser().is_dir():
        return False
    return any(
        _suggested_target_name(session) == target_name
        and getattr(session, "cwd", None) == cwd
        for session in report.sessions
    )


def _context_request_history(
    recent_context_results: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for result in recent_context_results or []:
        if not isinstance(result, dict):
            continue
        cwd = result.get("cwd")
        query = result.get("query")
        if not isinstance(cwd, str) or not isinstance(query, str):
            continue
        item_count = result.get("items")
        history.append(
            {
                "cwd": cwd,
                "query": query,
                "items": str(len(item_count) if isinstance(item_count, list) else 0),
            }
        )
    return history


def _blocked_context_priority(
    active_goals: list[dict[str, Any]] | None,
    command_suggestions: list[dict[str, str]],
    context_request_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    history_keys = {
        (item.get("cwd"), item.get("query"))
        for item in context_request_history
        if isinstance(item.get("cwd"), str) and isinstance(item.get("query"), str)
    }
    priorities: list[dict[str, str]] = []
    for goal in active_goals or []:
        if not isinstance(goal, dict):
            continue
        status = str(goal.get("last_status") or "").lower()
        if status not in {"blocked", "needs_user"}:
            continue
        suggestion = _request_context_suggestion_for_goal(goal, command_suggestions)
        if suggestion is None:
            continue
        cwd = suggestion["cwd"]
        query = suggestion["query"]
        if (cwd, query) in history_keys:
            continue
        priority: dict[str, str] = {
            "kind": "request_context",
            "reason": "context_first_for_blocked_goal",
            "cwd": cwd,
            "query": query,
            "message": "blocked/needs_user 目标缺上下文时先检索，再判断是否 ask_user。",
        }
        for key in ("goal_id", "target_name"):
            value = goal.get(key)
            if isinstance(value, str) and value:
                priority[key] = value
        priorities.append(priority)
    return priorities


def _request_context_suggestion_for_goal(
    goal: dict[str, Any],
    command_suggestions: list[dict[str, str]],
) -> dict[str, str] | None:
    goal_cwd = goal.get("cwd")
    if not isinstance(goal_cwd, str) or not goal_cwd:
        return None
    goal_text = goal.get("goal")
    for suggestion in command_suggestions:
        if suggestion.get("kind") != "request_context":
            continue
        if suggestion.get("cwd") != goal_cwd:
            continue
        if isinstance(goal_text, str) and suggestion.get("query") == goal_text:
            return suggestion
    for suggestion in command_suggestions:
        if (
            suggestion.get("kind") == "request_context"
            and suggestion.get("cwd") == goal_cwd
        ):
            return suggestion
    return None


def _candidate_target_payloads(
    report: CodexSupervisorReport,
    *,
    resumable_session_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "target_name": _suggested_target_name(session),
            "session_id": session.session_id,
            "cwd": session.cwd,
            "status": session.supervisor_status or session.status,
            "reason": session.supervisor_summary or session.reason,
            "source_size_bytes": session.source_size_bytes,
            "resume_context_hint": _resume_context_hint(
                session,
                resumable_session_ids=resumable_session_ids,
            ),
            "can_send_to_tmux": _has_managed_send_target(session),
            "can_resume": _can_resume_session(
                session,
                resumable_session_ids=resumable_session_ids,
            ),
            "tmux_session": session.managed_tmux_session,
            "managed_terminal_ready": session.managed_terminal_ready,
            "managed_bell": session.managed_bell,
            "managed_bell_event_at": session.managed_bell_event_at,
            "supervisor_status": session.supervisor_status,
            "supervisor_summary": _clip(session.supervisor_summary),
            "supervisor_next": _clip(session.supervisor_next),
        }
        for session in report.sessions
        if _is_llm_candidate_target(
            session,
            resumable_session_ids=resumable_session_ids,
        )
    ]


def _active_goal_payload(
    active_goals: list[dict[str, Any]] | None,
    candidate_targets: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    runtime_by_name = {
        target["target_name"]: target
        for target in candidate_targets or []
        if isinstance(target.get("target_name"), str)
    }
    items: list[dict[str, Any]] = []
    for goal in active_goals or []:
        if not isinstance(goal, dict):
            continue
        item: dict[str, Any] = {}
        for key in (
            "goal_id",
            "goal",
            "cwd",
            "target_name",
            "last_status",
            "last_summary",
            "last_next",
            "last_status_at",
        ):
            value = goal.get(key)
            if isinstance(value, str) and value:
                item[key] = _clip(value)
        target_name = item.get("target_name")
        runtime = runtime_by_name.get(target_name) if isinstance(target_name, str) else None
        if runtime is not None:
            item["worker_status"] = runtime.get("status")
            item["worker_session_id"] = runtime.get("session_id")
            reason = runtime.get("reason")
            if isinstance(reason, str) and reason:
                item["worker_reason"] = _clip(reason)
        if item:
            items.append(item)
    return items


def _resume_context_hint(
    session: Any,
    *,
    resumable_session_ids: set[str] | None = None,
) -> str | None:
    if not _can_resume_session(session, resumable_session_ids=resumable_session_ids):
        return None
    source_size = getattr(session, "source_size_bytes", None)
    if isinstance(source_size, int) and source_size >= LARGE_RESUME_SOURCE_BYTES:
        return "large_session_file"
    return "normal_session_file"


def _resumable_session_ids_from_suggestions(
    command_suggestions: list[dict[str, str]],
) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for suggestion in command_suggestions:
        if suggestion.get("kind") != "resume_session":
            continue
        session_id = suggestion.get("session_id")
        if not isinstance(session_id, str) or not session_id or session_id in seen:
            continue
        seen.add(session_id)
        ids.append(session_id)
    return ids


def _available_workspaces(
    report: CodexSupervisorReport,
    command_suggestions: list[dict[str, str]] | None = None,
) -> list[str]:
    seen: set[str] = set()
    workspaces: list[str] = []
    for session in report.sessions:
        if _is_terminal_done_session(session):
            continue
        cwd = getattr(session, "cwd", None)
        if not isinstance(cwd, str) or not cwd or cwd in seen:
            continue
        if not _workspace_exists(cwd):
            continue
        seen.add(cwd)
        workspaces.append(cwd)
    for suggestion in command_suggestions or []:
        cwd = suggestion.get("cwd")
        if not isinstance(cwd, str) or not cwd or cwd in seen:
            continue
        if not _workspace_exists(cwd):
            continue
        seen.add(cwd)
        workspaces.append(cwd)
    return workspaces


def _workspace_exists(cwd: str) -> bool:
    return Path(cwd).expanduser().is_dir()


def _default_workspace(
    report: CodexSupervisorReport,
    command_suggestions: list[dict[str, str]] | None = None,
) -> str | None:
    workspaces = _available_workspaces(report, command_suggestions)
    return workspaces[0] if workspaces else None


def _clip(text: str | None, *, limit: int = 160) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "\u2026"
