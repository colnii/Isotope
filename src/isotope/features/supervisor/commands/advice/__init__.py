"""Advice command payload and suggestion helpers for the Supervisor CLI."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any


def _default_api() -> Any:
    from isotope.features.supervisor import runner as api

    return api


def automation_status(report: Any, *, api: Any | None = None) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    tmux_lanes = [
        session for session in report.sessions if is_active_managed_tmux_session(session)
    ]
    process_lanes = [
        session
        for session in report.sessions
        if is_active_managed_process_session(session, api=api)
    ]
    managed_lanes = tmux_lanes + process_lanes
    names = [session.managed_name for session in managed_lanes if session.managed_name]
    if managed_lanes:
        process_note = (
            f"{len(process_lanes)} 个后台托管 Codex 进程"
            if process_lanes
            else ""
        )
        tmux_note = f"{len(tmux_lanes)} 个可旁观 tmux lane" if tmux_lanes else ""
        joined = "，".join(item for item in (process_note, tmux_note) if item)
        return {
            "ready": True,
            "managed_tmux_count": len(tmux_lanes),
            "managed_process_count": len(process_lanes),
            "managed_names": names,
            "reason": f"当前有 {joined}。",
            "launch_hint": api.LAUNCH_PROCESS_HINT,
            "adopt_hint": api.ADOPT_TMUX_HINT,
        }
    return {
        "ready": False,
        "managed_tmux_count": 0,
        "managed_process_count": 0,
        "managed_names": [],
        "reason": "当前没有托管的 Codex 进程或可旁观 tmux lane。",
        "launch_hint": api.LAUNCH_PROCESS_HINT,
        "adopt_hint": api.ADOPT_TMUX_HINT,
    }


def advice_payload(
    report: Any,
    *,
    target_name: str | None = None,
    include_all_managed: bool = False,
    allow_workspace_actions: bool = True,
    goal: str | None = None,
    goal_workspace: str | None = None,
    goal_target_name: str | None = None,
    active_goals: list[dict[str, Any]] | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    recommendation = report.recommendation
    suggestions = command_suggestions(
        report,
        target_name=target_name,
        include_all_managed=include_all_managed,
        allow_workspace_actions=allow_workspace_actions,
        goal=goal,
        goal_workspace=goal_workspace,
        goal_target_name=goal_target_name,
        active_goals=active_goals,
        api=api,
    )
    return {
        "status": "ok",
        "generated_at": report.generated_at,
        "recommendation": recommendation.to_dict(),
        "command_suggestion": suggestions[0] if suggestions else None,
        "command_suggestions": suggestions,
    }


def command_suggestions(
    report: Any,
    *,
    target_name: str | None = None,
    include_all_managed: bool = False,
    allow_workspace_actions: bool = True,
    goal: str | None = None,
    goal_workspace: str | None = None,
    goal_target_name: str | None = None,
    active_goals: list[dict[str, Any]] | None = None,
    api: Any | None = None,
) -> list[dict[str, str]]:
    if api is None:
        api = _default_api()
    if target_name:
        managed_tmux = managed_tmux_session_by_name(report, target_name)
        if managed_tmux is not None:
            return managed_tmux_command_suggestions(managed_tmux, api=api) + [
                watch_command_suggestion()
            ]
        return [watch_command_suggestion()]
    if should_wait_for_running_worker(report, active_goals, api=api):
        return [watch_command_suggestion()]
    goal_suggestions = active_goal_action_command_suggestions(
        active_goals,
        running_target_names=running_managed_target_names(report, api=api),
        api=api,
    ) or goal_action_command_suggestions(
        goal,
        goal_workspace,
        goal_target_name=goal_target_name,
        api=api,
    )
    if include_all_managed:
        suggestions: list[dict[str, str]] = []
        suggestions.extend(goal_suggestions)
        for session in report.sessions:
            if is_active_managed_tmux_session(session):
                suggestions.extend(managed_tmux_command_suggestions(session, api=api))
            if is_resume_capable_session(session, api=api):
                suggestions.extend(resume_session_command_suggestions(session, api=api))
        if allow_workspace_actions:
            suggestions.extend(workspace_action_command_suggestions(report, api=api))
        if suggestions:
            suggestions.append(watch_command_suggestion())
            return dedupe_command_suggestions(suggestions)
    if goal_suggestions:
        return dedupe_command_suggestions(goal_suggestions + [watch_command_suggestion()])
    recommendation = report.recommendation
    target = api._target_session(report, recommendation.target_session_id)
    if target is not None and target.managed_tmux_session:
        return managed_tmux_command_suggestions(target, api=api)
    if target is not None and is_resume_capable_session(target, api=api):
        return resume_session_command_suggestions(target, api=api) + [
            watch_command_suggestion()
        ]
    managed_tmux = first_managed_tmux_session(report)
    if managed_tmux is not None:
        return managed_tmux_command_suggestions(managed_tmux, api=api) + [
            watch_command_suggestion()
        ]
    if recommendation.action == "monitor":
        return [watch_command_suggestion()]
    return []


def should_wait_for_running_worker(
    report: Any,
    active_goals: list[dict[str, Any]] | None,
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        api = _default_api()
    running_names = running_managed_target_names(report, api=api)
    if api.MERGE_DISPATCH_TARGET_NAME in running_names:
        return True
    active_target_names = {
        target_name
        for goal in active_goals or []
        if isinstance(goal, dict)
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str) and target_name
    }
    return bool(active_target_names & running_names)


def workspace_action_command_suggestions(
    report: Any,
    *,
    api: Any | None = None,
) -> list[dict[str, str]]:
    if api is None:
        api = _default_api()
    suggestions: list[dict[str, str]] = []
    for cwd in workspace_cwds(report, api=api):
        suggestions.append(workspace_context_command_suggestion(cwd, api=api))
        suggestions.append(workspace_launch_command_suggestion(cwd, api=api))
    return suggestions


def goal_action_command_suggestions(
    goal: str | None,
    goal_workspace: str | None,
    *,
    goal_target_name: str | None = None,
    api: Any | None = None,
) -> list[dict[str, str]]:
    if api is None:
        api = _default_api()
    if not goal or not goal_workspace:
        return []
    return [
        workspace_context_command_suggestion(goal_workspace, query=goal, api=api),
        workspace_launch_command_suggestion(
            goal_workspace,
            prompt=goal,
            target_name=goal_target_name or "planner-session",
            api=api,
        ),
    ]


def active_goal_action_command_suggestions(
    active_goals: list[dict[str, Any]] | None,
    *,
    running_target_names: set[str] | None = None,
    api: Any | None = None,
) -> list[dict[str, str]]:
    if api is None:
        api = _default_api()
    suggestions: list[dict[str, str]] = []
    running_names = running_target_names or set()
    for goal in active_goals or []:
        goal_text = goal.get("goal")
        goal_workspace = goal.get("cwd")
        goal_target_name = goal.get("target_name")
        if not isinstance(goal_text, str) or not isinstance(goal_workspace, str):
            continue
        if isinstance(goal_target_name, str) and goal_target_name in running_names:
            continue
        suggestions.extend(
            goal_action_command_suggestions(
                goal_text,
                goal_workspace,
                goal_target_name=goal_target_name
                if isinstance(goal_target_name, str)
                else None,
                api=api,
            )
        )
    return suggestions


def running_managed_target_names(report: Any, *, api: Any | None = None) -> set[str]:
    if api is None:
        api = _default_api()
    names: set[str] = set()
    for session in report.sessions:
        name = getattr(session, "managed_name", None)
        if not isinstance(name, str) or not name:
            continue
        if getattr(session, "status", None) != "working":
            continue
        if api._session_marks_terminal_done(session):
            continue
        names.add(name)
    return names


def running_managed_target_names_from_registry(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> set[str]:
    if api is None:
        api = _default_api()
    names: set[str] = set()
    for record in api.read_managed_records(api.default_registry_path(codex_home)):
        if record.backend == "tmux":
            continue
        if api._pid_is_running(record.pid):
            names.add(record.name)
    return names


def workspace_cwds(report: Any, *, api: Any | None = None) -> list[str]:
    if api is None:
        api = _default_api()
    seen: set[str] = set()
    workspaces: list[str] = []
    for session in report.sessions:
        if api._session_marks_terminal_done(session):
            continue
        cwd = getattr(session, "cwd", None)
        if not isinstance(cwd, str) or not cwd or cwd in seen:
            continue
        if not api._cwd_is_existing_dir(cwd):
            continue
        seen.add(cwd)
        workspaces.append(cwd)
    return workspaces


def workspace_context_command_suggestion(
    cwd: str,
    *,
    query: str | None = None,
    api: Any | None = None,
) -> dict[str, str]:
    if api is None:
        api = _default_api()
    if query is None:
        query = api.DEFAULT_CONTEXT_QUERY
    return {
        "kind": "request_context",
        "label": "让 LLM 先检索项目上下文",
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


def workspace_launch_command_suggestion(
    cwd: str,
    *,
    prompt: str | None = None,
    target_name: str = "planner-session",
    api: Any | None = None,
) -> dict[str, str]:
    if api is None:
        api = _default_api()
    if prompt is None:
        prompt = api.DEFAULT_LAUNCH_PROMPT
    return {
        "kind": "launch_session",
        "label": "让 LLM 启动新的 Codex 会话",
        "target_name": target_name,
        "cwd": cwd,
        "prompt": prompt,
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


def dedupe_command_suggestions(
    suggestions: list[dict[str, str]],
) -> list[dict[str, str]]:
    seen: set[tuple[str | None, str | None, str | None]] = set()
    deduped: list[dict[str, str]] = []
    for suggestion in suggestions:
        key = (
            suggestion.get("kind"),
            suggestion.get("command"),
            suggestion.get("session_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(suggestion)
    return deduped


def resume_session_command_suggestions(
    session: Any,
    *,
    api: Any | None = None,
) -> list[dict[str, str]]:
    if api is None:
        api = _default_api()
    if not is_resume_capable_session(session, api=api):
        return []
    return [
        resume_session_command_suggestion(session, prompt_kind="send_status", api=api),
        resume_session_command_suggestion(session, prompt_kind="send_continue", api=api),
    ]


def resume_session_command_suggestion(
    session: Any,
    *,
    prompt_kind: str,
    api: Any | None = None,
) -> dict[str, str]:
    if api is None:
        api = _default_api()
    prompt_text = api.EXECUTABLE_ADVICE_TEXT[prompt_kind]
    label = (
        "恢复 Codex 历史会话并汇报状态"
        if prompt_kind == "send_status"
        else "恢复 Codex 历史会话并继续推进"
    )
    target_name = resume_managed_name_for_session(session)
    return {
        "kind": "resume_session",
        "label": label,
        "target_name": target_name,
        "session_id": session.session_id,
        "prompt_kind": prompt_kind,
        "command": shlex.join(
            [
                "isotope-supervisor",
                "resume",
                "--name",
                target_name,
                "--cwd",
                session.cwd,
                "--session-id",
                session.session_id,
                "--prompt",
                prompt_text,
            ]
        ),
    }


def managed_tmux_command_suggestions(
    session: Any,
    *,
    api: Any | None = None,
) -> list[dict[str, str]]:
    if api is None:
        api = _default_api()
    if not session.managed_name or not session.managed_tmux_session:
        return []
    return [
        {
            "kind": "tmux_attach",
            "label": "打开托管 tmux 窗口",
            "command": shlex.join(["tmux", "attach", "-t", session.managed_tmux_session]),
        },
        {
            "kind": "send_status",
            "label": "让托管 Codex 汇报状态",
            "command": shlex.join(
                [
                    "isotope-supervisor",
                    "send",
                    "--name",
                    session.managed_name,
                    "--text",
                    api.EXECUTABLE_ADVICE_TEXT["send_status"],
                ]
            ),
        },
        {
            "kind": "send_continue",
            "label": "让托管 Codex 继续推进",
            "command": shlex.join(
                [
                    "isotope-supervisor",
                    "send",
                    "--name",
                    session.managed_name,
                    "--text",
                    api.EXECUTABLE_ADVICE_TEXT["send_continue"],
                ]
            ),
        },
        {
            "kind": "archive",
            "label": "归档托管记录",
            "command": shlex.join(
                [
                    "isotope-supervisor",
                    "archive",
                    "--name",
                    session.managed_name,
                ]
            ),
        },
    ]


def watch_command_suggestion() -> dict[str, str]:
    return {
        "kind": "watch_changes",
        "label": "继续监控变化",
        "command": "isotope-supervisor watch --interval 180 --changes-only",
    }


def managed_tmux_session_by_name(report: Any, name: str) -> Any | None:
    for session in report.sessions:
        if is_active_managed_tmux_session(session) and session.managed_name == name:
            return session
    return None


def first_managed_tmux_session(report: Any) -> Any | None:
    for session in report.sessions:
        if is_active_managed_tmux_session(session):
            return session
    return None


def is_active_managed_tmux_session(session: Any) -> bool:
    return bool(session.managed_tmux_session) and session.status != "exited"


def is_active_managed_process_session(
    session: Any,
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        api = _default_api()
    return bool(
        getattr(session, "managed", False)
        and getattr(session, "managed_name", None)
        and getattr(session, "managed_backend", None) != "tmux"
        and not is_completed_session(session)
        and getattr(session, "status", None) != "exited"
    )


def is_resume_capable_session(session: Any, *, api: Any | None = None) -> bool:
    if api is None:
        api = _default_api()
    session_id = getattr(session, "session_id", None)
    return (
        isinstance(session_id, str)
        and bool(session_id)
        and not session_id.startswith("managed:")
        and bool(getattr(session, "cwd", None))
        and api._cwd_is_existing_dir(getattr(session, "cwd", None))
        and not is_completed_session(session)
    )


def resume_managed_name_for_session(session: Any) -> str:
    return "resume-" + session.short_session_id


def is_completed_session(session: Any) -> bool:
    return (
        getattr(session, "status", None) in {"done", "archived"}
        or getattr(session, "supervisor_status", None) == "done"
    )
