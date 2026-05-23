"""LLM action dispatch and failure guard helpers for Supervisor."""

from __future__ import annotations

import argparse
from typing import Any

from isotope.features.supervisor.llm_summary import _command_targets_name


def execute_llm_action(
    args: argparse.Namespace,
    report: Any,
    payload: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    action = payload["llm_action"]
    kind = action["kind"]
    if kind == "monitor":
        return {
            "kind": kind,
            "skipped": True,
            "reason": action["reason"],
        }
    if kind == "resume_session":
        if resume_action_outside_active_goals(payload, action):
            return {
                "kind": "resume_session",
                "skipped": True,
                "reason": "resume session outside active goals",
                "session_id": action.get("session_id"),
            }
        return execute_failure_guarded_action(
            args,
            report=report,
            payload=payload,
            action=action,
            event_type="resume_failed",
            execute=lambda: api._execute_resume_action(args, report, action),
            api=api,
        )
    if kind == "launch_session":
        return execute_failure_guarded_action(
            args,
            report=report,
            payload=payload,
            action=action,
            event_type="worker_launch_failed",
            execute=lambda: api._execute_launch_action(args, action),
            api=api,
        )
    if kind == "request_context":
        if budget_result := context_request_budget_result(args, payload, api=api):
            return budget_result
        return execute_failure_guarded_action(
            args,
            report=report,
            payload=payload,
            action=action,
            event_type="context_retrieval_failed",
            execute=lambda: api._execute_context_action(args, action),
            api=api,
        )
    if kind == "ask_user":
        return api._execute_ask_user_action(args, action)
    if kind == "delete_worktree":
        return api._execute_delete_worktree_action(args, action)
    if kind == "call_capacity":
        return execute_failure_guarded_action(
            args,
            report=report,
            payload=payload,
            action=action,
            event_type="capacity_call_failed",
            execute=lambda: api._execute_capacity_action(args, action, payload),
            api=api,
        )
    return api._execute_advice(
        args,
        report,
        payload,
        kind=kind,
        target_name=action.get("target_name"),
    )


def execute_failure_guarded_action(
    args: argparse.Namespace,
    *,
    report: Any,
    payload: dict[str, Any],
    action: dict[str, Any],
    event_type: str,
    execute: Any,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    try:
        result = execute()
    except Exception as exc:  # noqa: BLE001 - failed lane should not stop the loop.
        summary = exception_summary(exc)
        event = api._record_failure_event(
            args,
            event_type=event_type,
            report=report,
            payload=payload,
            action=action,
            error_summary=summary,
        )
        if api._failure_retry_exhausted(args, event):
            return api._execute_ask_user_action(
                args,
                api._failure_decision_request_action(
                    event=event,
                    question=failure_question(event_type),
                    reason=f"{event_type} retry limit exceeded",
                ),
            )
        return {
            "kind": action.get("kind") or event_type,
            "skipped": True,
            "reason": "supervisor action failed",
            "error": summary,
            "failure_event": event,
        }
    if not isinstance(result, dict):
        return result
    skipped_event_type = failure_event_type_for_skipped_result(
        action,
        result,
        fallback_event_type=event_type,
        api=api,
    )
    if skipped_event_type is None:
        return result
    event = api._record_failure_event(
        args,
        event_type=skipped_event_type,
        report=report,
        payload=payload,
        action=action,
        error_summary=str(result.get("reason") or "supervisor action skipped"),
    )
    result = {**result, "failure_event": event}
    if api._failure_retry_exhausted(args, event):
        return api._execute_ask_user_action(
            args,
            api._failure_decision_request_action(
                event=event,
                question=failure_question(skipped_event_type),
                reason=f"{skipped_event_type} retry limit exceeded",
            ),
        )
    return result


def failure_event_type_for_skipped_result(
    action: dict[str, Any],
    result: dict[str, Any],
    *,
    fallback_event_type: str,
    api: Any | None = None,
) -> str | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if result.get("skipped") is not True:
        return None
    reason = result.get("reason")
    if not isinstance(reason, str):
        return None
    if api._is_merge_dispatch_launch_action(action):
        return "merge_dispatch_failed"
    if reason in {"launch cwd missing", "worktree setup failed"}:
        return "worker_launch_failed"
    if reason == "resume cwd missing":
        return "resume_failed"
    if reason == "request_context cwd missing":
        return "context_retrieval_failed"
    if reason == "supervisor action failed":
        return fallback_event_type
    return None


def exception_summary(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return type(exc).__name__
    return f"{type(exc).__name__}: {message}"


def failure_question(event_type: str) -> str:
    questions = {
        "llm_planner_invalid_response": (
            "Supervisor LLM planner 连续返回无效动作，请确认是否调整配置或改为人工处理当前目标。"
        ),
        "worker_launch_failed": (
            "Supervisor 连续启动 worker 失败，请确认是否修复启动环境或跳过当前目标。"
        ),
        "resume_failed": (
            "Supervisor 连续 resume 会话失败，请确认是否改为重新启动 worker 或人工接管。"
        ),
        "context_retrieval_failed": (
            "Supervisor 连续检索上下文失败，请确认是否修复路径或跳过当前目标。"
        ),
        "merge_dispatch_failed": (
            "Supervisor 连续派发 merge worker 失败，请确认是否人工处理合并。"
        ),
        "worker_retry_failed": (
            "Supervisor 已达到 worker 自动重启上限但仍失败，请确认是否拆分目标、修复环境或人工接管。"
        ),
    }
    return questions.get(
        event_type,
        "Supervisor 连续遇到同类失败，请确认下一步处理方式。",
    )


def resume_action_outside_active_goals(
    payload: dict[str, Any],
    action: dict[str, Any],
) -> bool:
    active_goals = payload.get("active_goals")
    if not isinstance(active_goals, list) or not active_goals:
        return False
    session_id = action.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return False
    allowed_session_ids = active_goal_resume_session_ids(
        payload.get("command_suggestions"),
        active_goals,
    )
    return session_id not in allowed_session_ids


def active_goal_resume_session_ids(
    command_suggestions: Any,
    active_goals: list[Any],
) -> set[str]:
    if not isinstance(command_suggestions, list):
        return set()
    goal_names = {
        target_name
        for goal in active_goals
        if isinstance(goal, dict)
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str) and target_name
    }
    allowed: set[str] = set()
    for suggestion in command_suggestions:
        if not isinstance(suggestion, dict) or suggestion.get("kind") != "resume_session":
            continue
        session_id = suggestion.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        target_name = suggestion.get("target_name")
        command = suggestion.get("command")
        targets_goal = (
            isinstance(target_name, str)
            and target_name in goal_names
        ) or (
            isinstance(command, str)
            and any(_command_targets_name(command, name) for name in goal_names)
        )
        if targets_goal:
            allowed.add(session_id)
    return allowed


def context_request_count(payload: dict[str, Any]) -> int:
    count = 0
    for key in ("executed", "followup_executed"):
        item = payload.get(key)
        if (
            isinstance(item, dict)
            and item.get("kind") == "request_context"
            and not item.get("skipped")
        ):
            count += 1
    return count


def context_request_budget_result(
    args: argparse.Namespace,
    payload: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    max_requests = getattr(
        args,
        "max_context_requests",
        getattr(api, "DEFAULT_MAX_CONTEXT_REQUESTS", 0),
    )
    if max_requests <= 0:
        return None
    count = context_request_count(payload)
    if count < max_requests:
        return None
    return {
        "kind": "request_context",
        "skipped": True,
        "reason": "context request budget exhausted",
        "context_request_count": count,
        "max_context_requests": max_requests,
    }
