"""LLM action decision 的 command suggestion 匹配、过滤和优先级工具."""

from __future__ import annotations

import shlex
from typing import Any

from .flow import CodexSupervisorReport
from .llm_action_guards import is_terminal_done_session as _is_terminal_done_session
from .merge_dispatch import DEFAULT_TARGET_NAME as MERGE_DISPATCH_TARGET_NAME


# ---------------------------------------------------------------------------
# active goal scoped command suggestions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# running worker priority
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# command suggestion 匹配
# ---------------------------------------------------------------------------


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


def _command_targets_name(command: str, target_name: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    for index, part in enumerate(parts[:-1]):
        if part == "--name" and parts[index + 1] == target_name:
            return True
    return False


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
