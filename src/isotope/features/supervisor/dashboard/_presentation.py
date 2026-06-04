"""Dashboard command handling for the Supervisor CLI."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.state.current_batch import build_current_batch_view
from isotope.features.supervisor.state.snapshot_display import (
    STATE_SNAPSHOT_SOURCE_LABEL,
    state_snapshot_schema_label,
    state_snapshot_schema_status,
)
from isotope.platform.state.multi_worker import (
    build_multi_worker_status_payload,
)
from isotope.features.supervisor.state.projection import (
    build_supervisor_state_snapshot,
)
from isotope.features.supervisor.state.worker_lifecycle import (
    worker_lifecycle_projection_payload,
)


dashboard_worker_lifecycle_payload = worker_lifecycle_projection_payload


def _default_api() -> Any:
    from isotope.features.supervisor import runner as api

    return api


def handle_dashboard_command(args: argparse.Namespace, *, api: Any) -> int:
    report = api._scan_report(args)
    state_snapshot = dashboard_state_snapshot(Path(args.codex_home))
    payload = dashboard_payload(
        report,
        active_goals=state_snapshot["active_goals"],
        decision_requests=state_snapshot["active_decisions"],
        notifications=state_snapshot["notifications"]["recent"],
        multi_worker=build_multi_worker_status_payload(root=Path(args.codex_home)),
        state_snapshot=state_snapshot,
        api=api,
    )
    if args.json:
        api._print_json(payload)
    else:
        print_dashboard_plain(payload, api=api)
    return 0


def dashboard_payload(
    report: Any,
    *,
    active_goals: list[dict[str, Any]] | None = None,
    decision_requests: list[dict[str, Any]] | None = None,
    notifications: list[dict[str, Any]] | None = None,
    multi_worker: dict[str, Any] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    worker_lifecycle_decision: dict[str, Any] | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    groups: dict[str, list[dict[str, Any]]] = {
        "needs_attention": [],
        "done": [],
        "working": [],
    }
    display_sessions = dashboard_display_sessions(report.sessions, api=api)
    for session, linked_session, linked_match in display_sessions:
        groups[dashboard_group_for(session, linked_session=linked_session, api=api)].append(
            dashboard_item(
                session,
                linked_session=linked_session,
                linked_match=linked_match,
                api=api,
            )
        )
    notification_items = notifications or []
    notification_counts = dashboard_notification_counts(
        notification_items,
        state_snapshot=state_snapshot,
    )
    snapshot = state_snapshot or dashboard_state_snapshot_from_items(
        active_goals=active_goals or [],
        decision_requests=decision_requests or [],
        notifications=notification_items,
    )
    return {
        "status": "ok",
        "generated_at": report.generated_at,
        "recommendation": report.recommendation.to_dict(),
        "counts": {key: len(value) for key, value in groups.items()},
        "groups": groups,
        "current": dashboard_current_payload(
            display_sessions,
            active_goals=active_goals,
            state_snapshot=state_snapshot,
            api=api,
        ),
        "multi_worker": multi_worker or empty_multi_worker_payload(),
        "decision_requests": decision_requests or [],
        "notifications": notification_items,
        "notification_counts": notification_counts,
        "worker_lifecycle": worker_lifecycle_projection_payload(
            worker_lifecycle_decision=worker_lifecycle_decision,
            state_snapshot=snapshot,
        ),
        "worker_lifecycle_execution": dashboard_worker_lifecycle_execution_payload(
            snapshot
        ),
        "state_snapshot_meta": dashboard_state_snapshot_meta(snapshot),
        "state_snapshot": snapshot,
    }


def dashboard_notification_counts(
    notifications: list[dict[str, Any]],
    *,
    state_snapshot: dict[str, Any] | None,
) -> dict[str, int]:
    snapshot_notifications = (
        state_snapshot.get("notifications") if isinstance(state_snapshot, dict) else None
    )
    if isinstance(snapshot_notifications, dict):
        total = snapshot_notifications.get("total")
        unread = snapshot_notifications.get("unread")
        if isinstance(total, int) and isinstance(unread, int):
            return {"total": total, "unread": unread}
    return {
        "total": len(notifications),
        "unread": sum(1 for item in notifications if item.get("unread") is True),
    }


def dashboard_state_snapshot(codex_home: Path) -> dict[str, Any]:
    return build_supervisor_state_snapshot(codex_home=codex_home)


def dashboard_state_snapshot_meta(snapshot: dict[str, Any]) -> dict[str, Any]:
    schema_status = state_snapshot_schema_status(snapshot)
    return {
        "kind": snapshot.get("kind"),
        "schema_version": snapshot.get("schema_version"),
        "schema_label": state_snapshot_schema_label(snapshot),
        "schema_status": schema_status["schema_status"],
        "schema_reason": schema_status["schema_reason"],
        "source_label": STATE_SNAPSHOT_SOURCE_LABEL,
    }


def dashboard_state_snapshot_from_items(
    *,
    active_goals: list[dict[str, Any]],
    decision_requests: list[dict[str, Any]],
    notifications: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "kind": "supervisor_state_snapshot",
        "schema_version": 1,
        "summary": {
            "active_goals": len(active_goals),
            "goals_done": _goal_status_count(active_goals, "done"),
            "goals_blocked": _goal_status_count(active_goals, "blocked"),
            "goals_needs_user": _goal_status_count(active_goals, "needs_user"),
            "active_decisions": len(decision_requests),
            "failed_lanes": 0,
            "worker_events": 0,
            "notifications": len(notifications),
            "unread_notifications": sum(
                1 for item in notifications if item.get("unread") is True
            ),
        },
        "active_goals": list(active_goals),
        "active_decisions": list(decision_requests),
        "failed_lanes": [],
        "recent_worker_events": [],
        "notifications": {
            "total": len(notifications),
            "unread": sum(1 for item in notifications if item.get("unread") is True),
            "recent": list(notifications),
        },
    }


def _goal_status_count(goals: list[dict[str, Any]], status: str) -> int:
    return sum(1 for goal in goals if goal.get("last_status") == status)


def empty_multi_worker_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "store": {"root": "", "path": "", "format": "file_memory_store"},
        "filters": {"worker": None},
        "summary": {
            "worker_count": 0,
            "memory_records_total": 0,
            "worker_events_total": 0,
            "capacity_calls_total": 0,
            "hidden_workers": 0,
        },
        "workers": [],
    }


def dashboard_current_payload(
    display_sessions: list[tuple[Any, Any | None, dict[str, Any] | None]],
    *,
    active_goals: list[dict[str, Any]] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    dependency_limit: int | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    return current_batch_payload_from_display_sessions(
        display_sessions,
        active_goals=_active_goals_from_snapshot(
            active_goals,
            state_snapshot=state_snapshot,
        ),
        state_snapshot=state_snapshot,
        dependency_limit=dependency_limit,
        api=api,
    )


def current_batch_payload(
    report: Any,
    *,
    active_goals: list[dict[str, Any]] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    worker_reviews: dict[str, Any] | None = None,
    dependency_limit: int | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    return current_batch_payload_from_display_sessions(
        dashboard_display_sessions(report.sessions, api=api),
        active_goals=_active_goals_from_snapshot(
            active_goals,
            state_snapshot=state_snapshot,
        ),
        state_snapshot=state_snapshot,
        worker_reviews=worker_reviews,
        dependency_limit=dependency_limit,
        api=api,
    )


def current_batch_payload_from_display_sessions(
    display_sessions: list[tuple[Any, Any | None, dict[str, Any] | None]],
    *,
    active_goals: list[dict[str, Any]] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    worker_reviews: dict[str, Any] | None = None,
    dependency_limit: int | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    active_goals = _active_goals_from_snapshot(
        active_goals,
        state_snapshot=state_snapshot,
    )
    current_goals = [
        item
        for item in (dashboard_active_goal_item(goal, api=api) for goal in active_goals or [])
    ]
    managed_workers = [
        dashboard_item(
            session,
            linked_session=linked_session,
            linked_match=linked_match,
            api=api,
        )
        for session, linked_session, linked_match in display_sessions
        if getattr(session, "managed", False) and getattr(session, "managed_name", None)
    ]
    return build_current_batch_view(
        active_goals=current_goals,
        managed_workers=managed_workers,
        worker_reviews=worker_reviews,
        dependency_limit=dependency_limit,
    ).to_dict()


def _active_goals_from_snapshot(
    active_goals: list[dict[str, Any]] | None,
    *,
    state_snapshot: dict[str, Any] | None,
) -> list[dict[str, Any]] | None:
    if active_goals is not None:
        return active_goals
    if not isinstance(state_snapshot, dict):
        return None
    snapshot_goals = state_snapshot.get("active_goals")
    if not isinstance(snapshot_goals, list):
        return None
    return [dict(goal) for goal in snapshot_goals if isinstance(goal, dict)]


def dashboard_active_goal_item(goal: dict[str, Any], *, api: Any | None = None) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    item = dict(goal)
    cwd_exists = api._cwd_is_existing_dir(goal.get("cwd"))
    item["cwd_exists"] = cwd_exists
    item["current"] = cwd_exists and goal.get("last_status") != "done"
    return item


def is_current_managed_worker(session: Any, *, api: Any | None = None) -> bool:
    if api is None:
        api = _default_api()
    return bool(
        getattr(session, "managed", False)
        and getattr(session, "status", None) != "exited"
        and not api._is_completed_session(session)
        and getattr(session, "managed_name", None)
        and api._cwd_is_existing_dir(getattr(session, "cwd", None))
    )


def notification_dicts(codex_home: Path) -> list[dict[str, Any]]:
    return [
        dashboard_notification_dict(notification.to_dict())
        for notification in NotificationFlow.in_process(codex_home).list_notifications()
    ]


def dashboard_notification_dict(notification: dict[str, Any]) -> dict[str, Any]:
    item = dict(notification)
    source_ref = item.get("source_ref")
    item["source_ref"] = (
        dashboard_notification_source_ref(source_ref)
        if isinstance(source_ref, dict)
        else {}
    )
    return item


def dashboard_notification_source_ref(source_ref: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "ref_type",
        "goal_id",
        "request_id",
        "run_id",
        "session_id",
        "notification_id",
        "status",
        "target_name",
        "timeout_seconds",
    }
    return {
        key: value
        for key, value in source_ref.items()
        if key in allowed_keys and isinstance(value, (str, bool, int, float))
    }


def dashboard_group_for(
    session: Any,
    *,
    linked_session: Any | None = None,
    api: Any | None = None,
) -> str:
    if api is None:
        api = _default_api()
    status_source = dashboard_status_source(session, linked_session)
    supervisor_status = (status_source.supervisor_status or "").lower()
    cwd = getattr(session, "cwd", None)
    if not getattr(session, "managed", False) and is_missing_supervisor_worktree(cwd, api=api):
        return "done"
    if supervisor_status in {"blocked", "needs_user"}:
        return "needs_attention"
    if supervisor_status == "done":
        return "done"
    if status_source.status in {"needs_user", "error", "stale"}:
        return "needs_attention"
    if session.managed_bell:
        return "needs_attention"
    return "working"


def is_missing_supervisor_worktree(value: Any, *, api: Any | None = None) -> bool:
    if api is None:
        api = _default_api()
    if not isinstance(value, (str, Path)) or not str(value):
        return False
    path = Path(value)
    return ".worktrees" in path.parts and not api._cwd_is_existing_dir(path)


def dashboard_display_sessions(
    sessions: Any,
    *,
    api: Any | None = None,
) -> list[tuple[Any, Any | None, dict[str, Any] | None]]:
    if api is None:
        api = _default_api()
    linkable_sessions: list[Any] = []
    for session in sessions:
        if session.managed:
            continue
        if session.status == "exited":
            continue
        if not api._cwd_is_existing_dir(getattr(session, "cwd", None)):
            continue
        linkable_sessions.append(session)

    managed_sessions = [
        session
        for session in sessions
        if session.managed and session.status != "exited"
    ]
    linked_by_managed_id = best_linked_sessions_for_managed_lanes(
        managed_sessions,
        linkable_sessions,
    )
    consumed_linked_ids = {
        candidate.session_id
        for candidate, _match in linked_by_managed_id.values()
    }

    display_sessions: list[tuple[Any, Any | None, dict[str, Any] | None]] = []
    for session in sessions:
        if session.managed and session.status == "exited":
            continue
        if session.session_id in consumed_linked_ids:
            continue
        linked = linked_by_managed_id.get(session.session_id)
        linked_session = linked[0] if linked else None
        linked_match = linked[1] if linked else None
        display_sessions.append((session, linked_session, linked_match))
    return display_sessions


def best_linked_sessions_for_managed_lanes(
    managed_sessions: list[Any],
    candidates: list[Any],
) -> dict[str, tuple[Any, dict[str, Any]]]:
    scored_pairs: list[tuple[int, int, int, Any, Any, dict[str, Any]]] = []
    for managed_index, managed_session in enumerate(managed_sessions):
        for candidate_index, candidate in enumerate(candidates):
            match = managed_link_analysis(managed_session, candidate)
            score = match["score"]
            if score <= 0:
                continue
            scored_pairs.append(
                (score, managed_index, candidate_index, managed_session, candidate, match)
            )
    scored_pairs.sort(key=lambda item: (-item[0], item[1], item[2]))

    linked_by_managed_id: dict[str, tuple[Any, dict[str, Any]]] = {}
    consumed_linked_ids: set[str] = set()
    for (
        _score,
        _managed_index,
        _candidate_index,
        managed_session,
        candidate,
        match,
    ) in scored_pairs:
        if managed_session.session_id in linked_by_managed_id:
            continue
        if candidate.session_id in consumed_linked_ids:
            continue
        linked_by_managed_id[managed_session.session_id] = (candidate, match)
        consumed_linked_ids.add(candidate.session_id)
    return linked_by_managed_id


def best_linked_session_for_managed(
    managed_session: Any,
    candidates: list[Any],
    consumed_linked_ids: set[str],
) -> Any | None:
    available = [
        candidate
        for candidate in candidates
        if candidate.session_id not in consumed_linked_ids
    ]
    if not available:
        return None
    scored = [
        (
            managed_link_score(managed_session, candidate),
            index,
            candidate,
        )
        for index, candidate in enumerate(available)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score, _index, candidate = scored[0]
    return candidate if best_score > 0 else None


def managed_link_score(managed_session: Any, candidate: Any) -> int:
    return managed_link_analysis(managed_session, candidate)["score"]


def managed_link_analysis(managed_session: Any, candidate: Any) -> dict[str, Any]:
    score = 0
    reasons: list[dict[str, Any]] = []
    raw_pane_text = getattr(managed_session, "managed_terminal_excerpt", None)
    pane_text = normalize_match_text(raw_pane_text)
    active_pane_text = active_terminal_match_text(raw_pane_text)
    active_scope = "active_terminal" if active_pane_text != pane_text else "terminal"

    def add_reason(kind: str, label: str, weight: int) -> None:
        nonlocal score
        score += weight
        reasons.append({"kind": kind, "label": label, "weight": weight})

    if managed_prompt_matches_candidate(managed_session, candidate):
        add_reason("managed_prompt", "托管登记 prompt 命中真实 session", 320)
    if pane_text:
        if text_contains(active_pane_text, getattr(candidate, "session_id", None)):
            add_reason("session_id", "活跃终端片段命中真实 session id", 40)
        thread_marker_matched = candidate_thread_marker_matches(
            active_pane_text, candidate
        )
        if thread_marker_matched:
            add_reason("thread_marker", "活跃终端片段命中 Thread renamed 标题", 250)
        elif candidate_text_matches(active_pane_text, candidate):
            add_reason("title_or_message", "活跃终端片段命中标题或最近消息", 40)
        if candidate_snippet_matches(active_pane_text, candidate):
            add_reason("message_snippet", "活跃终端片段命中最近消息片段", 160)
    if getattr(managed_session, "managed_name", None):
        name_text = normalize_match_text(managed_session.managed_name)
        if candidate_text_matches(name_text, candidate):
            add_reason("managed_name", "托管名命中真实 session 标题或消息", 20)
    has_active_reason = any(
        reason["kind"]
        in {
            "session_id",
            "thread_marker",
            "title_or_message",
            "message_snippet",
        }
        for reason in reasons
    )
    has_managed_prompt_reason = any(
        reason["kind"] == "managed_prompt" for reason in reasons
    )
    if has_active_reason:
        scope = active_scope
    elif has_managed_prompt_reason:
        scope = "managed_prompt"
    else:
        scope = "managed_name"
    return {
        "score": score,
        "scope": scope,
        "reasons": reasons,
        "label": linked_match_label(scope, reasons),
    }


def linked_match_label(scope: str, reasons: list[dict[str, Any]]) -> str:
    if not reasons:
        return "无正分匹配"
    active_parts = [
        {
            "session_id": "真实 session id",
            "thread_marker": "Thread renamed 标题",
            "title_or_message": "标题或最近消息",
            "message_snippet": "最近消息片段",
        }[reason["kind"]]
        for reason in reasons
        if reason["kind"]
        in {
            "session_id",
            "thread_marker",
            "title_or_message",
            "message_snippet",
        }
    ]
    if active_parts:
        prefix = "活跃终端片段" if scope == "active_terminal" else "终端片段"
        return f"{prefix}命中 " + "、".join(active_parts)
    if any(reason["kind"] == "managed_prompt" for reason in reasons):
        return "托管登记 prompt 命中真实 session"
    return "托管名命中真实 session 标题或消息"


def managed_prompt_matches_candidate(managed_session: Any, candidate: Any) -> bool:
    prompt = normalize_match_text(getattr(managed_session, "last_user_message", None))
    if is_generic_managed_prompt(prompt):
        return False
    for field in (
        getattr(candidate, "initial_user_title", None),
        getattr(candidate, "last_user_message", None),
        getattr(candidate, "thread_name", None),
    ):
        text = normalize_match_text(field)
        if len(text) < 16:
            continue
        if prompt in text or text in prompt:
            return True
    return False


def is_generic_managed_prompt(text: str) -> bool:
    return (
        len(text) < 16
        or text in {"接管已有 tmux 会话", "等待输入"}
        or is_generic_supervisor_status_prompt(text)
    )


def active_terminal_match_text(value: Any) -> str:
    text = normalize_match_text(value)
    if not text:
        return ""
    marker_positions = [
        text.rfind(marker)
        for marker in (
            "thread renamed to",
            ">_ openai codex",
            "openai codex",
            "tip: use /copy",
        )
    ]
    start = max(marker_positions)
    return text[start:] if start >= 0 else text


def candidate_thread_marker_matches(haystack: str, candidate: Any) -> bool:
    for field in (
        getattr(candidate, "thread_name", None),
        getattr(candidate, "initial_user_title", None),
    ):
        title = normalize_match_text(field)
        if len(title) < 2:
            continue
        if f"thread renamed to {title}" in haystack:
            return True
        if f"codex resume '{title}'" in haystack:
            return True
        if f'codex resume "{title}"' in haystack:
            return True
    return False


def candidate_snippet_matches(haystack: str, candidate: Any) -> bool:
    for field in (
        getattr(candidate, "initial_user_title", None),
        getattr(candidate, "last_user_message", None),
        getattr(candidate, "last_assistant_message", None),
    ):
        text = normalize_match_text(field)
        if is_generic_supervisor_status_prompt(text):
            continue
        if len(text) < 16:
            continue
        for snippet in (text[:32], text[-32:]):
            if text_contains(haystack, snippet):
                return True
    return False


def is_generic_supervisor_status_prompt(text: str) -> bool:
    return (
        "请汇报当前状态" in text
        and "supervisor_status" in text
        and "supervisor_summary" in text
    )


def candidate_text_matches(haystack: str, candidate: Any) -> bool:
    fields = (
        getattr(candidate, "thread_name", None),
        getattr(candidate, "initial_user_title", None),
        getattr(candidate, "last_user_message", None),
        getattr(candidate, "last_assistant_message", None),
    )
    for field in fields:
        text = normalize_match_text(field)
        if is_generic_supervisor_status_prompt(text):
            continue
        if text_contains_positive(haystack, text):
            return True
    return False


def text_contains(haystack: str, value: Any) -> bool:
    needle = normalize_match_text(value)
    return len(needle) >= 4 and needle in haystack


def text_contains_positive(haystack: str, value: Any) -> bool:
    needle = normalize_match_text(value)
    if len(needle) < 4 or needle not in haystack:
        return False
    negative_phrases = (
        f"不要继续 {needle}",
        f"不要再继续 {needle}",
        f"不继续 {needle}",
        f"别继续 {needle}",
    )
    return not any(phrase in haystack for phrase in negative_phrases)


def normalize_match_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().split())


def dashboard_item(
    session: Any,
    *,
    linked_session: Any | None = None,
    linked_match: dict[str, Any] | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    display_source = linked_session or session
    resume_session = linked_session or session
    status_source = dashboard_status_source(session, linked_session)
    cwd_exists = api._cwd_is_existing_dir(session.cwd)
    return {
        "session_id": session.session_id,
        "short_session_id": display_source.short_session_id,
        "display_title": display_source.display_title,
        "resume_command": f"codex resume {resume_session.session_id}",
        "linked_session_id": linked_session.session_id if linked_session else None,
        "linked_short_session_id": linked_session.short_session_id
        if linked_session
        else None,
        "linked_resume_command": f"codex resume {linked_session.session_id}"
        if linked_session
        else None,
        "linked_match": linked_match if linked_session else None,
        "managed_display_title": session.display_title if linked_session else None,
        "name": session.managed_name,
        "thread_name": display_source.thread_name,
        "thread_id": display_source.thread_id,
        "initial_user_title": display_source.initial_user_title,
        "agent_nickname": display_source.agent_nickname,
        "agent_role": display_source.agent_role,
        "cwd": session.cwd,
        "cwd_exists": cwd_exists,
        "current": dashboard_item_is_current(session, cwd_exists=cwd_exists, api=api),
        "git_branch": display_source.git_branch or session.git_branch,
        "status": status_source.status,
        "status_label": status_source.status_label,
        "status_evidence": status_source.status_evidence,
        "supervisor_status": status_source.supervisor_status,
        "supervisor_summary": status_source.supervisor_summary,
        "supervisor_next": status_source.supervisor_next,
        "managed": session.managed,
        "managed_backend": session.managed_backend,
        "managed_tmux_session": session.managed_tmux_session,
        "managed_terminal_excerpt": session.managed_terminal_excerpt,
        "managed_terminal_ready": session.managed_terminal_ready,
        "managed_bell": session.managed_bell,
        "managed_bell_event_at": session.managed_bell_event_at,
        "managed_bell_hook_installed": session.managed_bell_hook_installed,
        "control_commands": api._managed_tmux_command_suggestions(session)
        if session.managed_tmux_session
        else [],
        "reason": status_source.reason,
        "age_seconds": status_source.age_seconds,
    }


def dashboard_item_is_current(
    session: Any,
    *,
    cwd_exists: bool,
    api: Any | None = None,
) -> bool:
    if api is None:
        api = _default_api()
    if not cwd_exists or api._session_marks_terminal_done(session):
        return False
    if is_current_managed_worker(session, api=api):
        return True
    return getattr(session, "status", None) in {"working", "needs_user", "error"}


def dashboard_status_source(session: Any, linked_session: Any | None) -> Any:
    if linked_session is not None and linked_session.supervisor_status:
        return linked_session
    return session


def print_dashboard_plain(payload: dict[str, Any], *, api: Any | None = None) -> None:
    if api is None:
        api = _default_api()
    print("[Codex Supervisor dashboard]")
    print(f"生成时间：{payload['generated_at']}")
    print(f"建议：{payload['recommendation']['label']}")
    decision_requests = payload.get("decision_requests") or []
    print(f"等待拍板：{len(decision_requests)}")
    for item in decision_requests:
        target = item.get("target_name") or item.get("session_id") or "未知"
        context_status = item.get("context_status") or "unknown"
        print(f"- {item['question']} context={context_status} target={target}")
    print_dashboard_dependency_batch(payload)
    print_dashboard_capacity_summaries(payload)
    print_dashboard_worker_lifecycle(payload.get("worker_lifecycle"))
    print_dashboard_worker_lifecycle_execution(
        payload.get("worker_lifecycle_execution")
    )
    for group_key, label in api.DASHBOARD_GROUP_LABELS.items():
        items = payload["groups"][group_key]
        print(f"{label}：{len(items)}")
        for item in items:
            title = item["display_title"]
            status = item["status_label"]
            detail = item["supervisor_summary"] or item["reason"]
            suffix = dashboard_item_suffix(item)
            print(f"- {title} {status} / {detail}{suffix}")
            if item["status_evidence"]:
                evidence = item["status_evidence"]
                print(f"  依据：{evidence['label']} - {evidence['detail']}")


def print_dashboard_worker_lifecycle(worker_lifecycle: Any) -> None:
    if not isinstance(worker_lifecycle, dict) or worker_lifecycle.get("status") != "ok":
        return
    print(
        "Worker 生命周期："
        f"stage={_dashboard_text(worker_lifecycle.get('stage'), 'unknown')} "
        f"next_step={_dashboard_text(worker_lifecycle.get('next_step'), 'unknown')} "
        f"policy={_dashboard_text(worker_lifecycle.get('policy_status'), 'unknown')}"
    )
    remaining_step = _dashboard_text(worker_lifecycle.get("remaining_step"), "")
    blocked_reason = _dashboard_text(worker_lifecycle.get("blocked_reason"), "")
    if remaining_step:
        print(f"  remaining_step={remaining_step}")
    if blocked_reason:
        print(f"  blocked_reason={blocked_reason}")
    timeline = _dashboard_worker_lifecycle_timeline_summary(
        worker_lifecycle.get("timeline")
    )
    if timeline:
        print(f"  timeline: {timeline}")


def print_dashboard_worker_lifecycle_execution(execution: Any) -> None:
    if not isinstance(execution, dict) or execution.get("status") == "absent":
        return
    print(
        "  execution="
        f"{_dashboard_text(execution.get('kind'), 'unknown')} "
        f"status={_dashboard_text(execution.get('execution_status'), 'planned')} "
        f"actions={_dashboard_text(execution.get('action_count'), 0)}"
    )
    reason = _dashboard_text(execution.get("execution_reason"), "")
    hint = _dashboard_text(execution.get("execute_hint"), "")
    if reason:
        print(f"  execution_reason={reason}")
    if hint:
        print(f"  execute_hint={hint}")
    command = _dashboard_text(execution.get("execute_command"), "")
    if command:
        print(f"  execute_command={command}")


def dashboard_worker_lifecycle_execution_payload(
    state_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(state_snapshot, dict):
        return {"status": "absent"}
    plan = state_snapshot.get("worker_lifecycle_execution")
    if not isinstance(plan, dict):
        return {"status": "absent"}
    result = state_snapshot.get("worker_lifecycle_execution_result")
    result = result if isinstance(result, dict) else None
    execution_status = "planned"
    if result is not None:
        execution_status = "skipped" if result.get("skipped") is True else "executed"
    return {
        "status": _dashboard_text(plan.get("status"), "planned"),
        "kind": _dashboard_text(plan.get("kind"), "unknown"),
        "next_step": _dashboard_text(plan.get("next_step"), "unknown"),
        "source": _dashboard_text(plan.get("source"), "unknown"),
        "action_count": _dashboard_lifecycle_execution_action_count(plan),
        "execution_status": execution_status,
        "execution_reason": (
            _dashboard_text(result.get("reason"), "") if result is not None else ""
        ),
        "execute_hint": _dashboard_lifecycle_execution_hint(plan, result),
        "execute_command": _dashboard_lifecycle_execution_command(plan, result),
    }


def _dashboard_lifecycle_execution_action_count(plan: dict[str, Any]) -> int:
    if isinstance(plan.get("delete_worktree_actions"), list):
        return len(plan["delete_worktree_actions"])
    if isinstance(plan.get("cleanup_candidates"), list):
        return len(plan["cleanup_candidates"])
    if isinstance(plan.get("merge_dispatch"), dict):
        return 1
    return 0


def _dashboard_lifecycle_execution_hint(
    plan: dict[str, Any],
    result: dict[str, Any] | None,
) -> str:
    kind = plan.get("kind")
    reason = result.get("reason") if isinstance(result, dict) else None
    if kind in {"archive_cleanup", "cleanup_worktree"}:
        return "--lifecycle-cleanup-execute"
    if (
        kind == "merge_dispatch"
        and isinstance(reason, str)
        and "merge dispatch" in reason
    ):
        return "--merge-dispatch-execute"
    return ""


def _dashboard_lifecycle_execution_command(
    plan: dict[str, Any],
    result: dict[str, Any] | None,
) -> str:
    hint = _dashboard_lifecycle_execution_hint(plan, result)
    if not hint:
        return ""
    return shlex.join(["isotope-supervisor", "loop", "--iterations", "1", hint])


def _dashboard_worker_lifecycle_timeline_summary(timeline: Any) -> str:
    if not isinstance(timeline, list):
        return ""
    items: list[str] = []
    for item in timeline:
        if not isinstance(item, dict):
            continue
        stage = _dashboard_text(item.get("stage"), "unknown")
        action = _dashboard_text(item.get("action"), "unknown")
        status = _dashboard_text(item.get("status"), "unknown")
        items.append(f"{stage}/{action} {status}")
    return "; ".join(items)


def print_dashboard_capacity_summaries(payload: dict[str, Any]) -> None:
    multi_worker = payload.get("multi_worker")
    if not isinstance(multi_worker, dict):
        return
    summary = multi_worker.get("summary") if isinstance(multi_worker.get("summary"), dict) else {}
    total = summary.get("capacity_calls_total", 0)
    print(f"能力调用：{total}")
    supervised = multi_worker.get("supervised_execution")
    if isinstance(supervised, dict):
        runs = supervised.get("recent_capacity_runs")
        recent_runs = (
            [item for item in runs if isinstance(item, dict)]
            if isinstance(runs, list)
            else []
        )
        print(
            "受监督执行："
            f"workers={supervised.get('capacity_workers_total', 0)} "
            f"agent_loop_calls={supervised.get('capacity_agent_loop_calls_total', 0)} "
            f"recent={len(recent_runs)}"
        )
        for run in recent_runs:
            print(f"- {_dashboard_supervised_capacity_run_text(run)}")
        return
    workers = multi_worker.get("workers")
    if not isinstance(workers, list):
        return
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        recent = worker.get("recent_capacity_result")
        if not isinstance(recent, dict):
            continue
        print(f"- {_dashboard_capacity_result_text(worker, recent)}")


def _dashboard_supervised_capacity_run_text(run: dict[str, Any]) -> str:
    loop = (
        run.get("agent_loop_result")
        if isinstance(run.get("agent_loop_result"), dict)
        else {}
    )
    return _dashboard_capacity_line_text(
        worker=run.get("worker"),
        capacity_id=run.get("capacity_id"),
        summary=run.get("summary"),
        loop=loop,
    )


def _dashboard_capacity_result_text(
    worker: dict[str, Any],
    recent: dict[str, Any],
) -> str:
    loop = (
        recent.get("agent_loop_result")
        if isinstance(recent.get("agent_loop_result"), dict)
        else {}
    )
    return _dashboard_capacity_line_text(
        worker=worker.get("name"),
        capacity_id=recent.get("capacity_id"),
        summary=recent.get("summary"),
        loop=loop,
    )


def _dashboard_capacity_line_text(
    *,
    worker: Any,
    capacity_id: Any,
    summary: Any,
    loop: dict[str, Any],
) -> str:
    parts = [
        _dashboard_text(worker, "unknown"),
        _dashboard_text(capacity_id, "unknown"),
        f"tick={_dashboard_text(loop.get('agent_loop_tick_status'), 'unknown')}",
        "step="
        f"{_dashboard_text(loop.get('agent_loop_planner_selected_step'), 'unknown')}",
    ]
    artifact_id = _dashboard_text(loop.get("agent_loop_artifact_id"), "")
    if artifact_id:
        parts.append(f"artifact={artifact_id}")
    stop_reason = _dashboard_text(loop.get("agent_loop_tick_after_stop_reason"), "")
    if stop_reason:
        parts.append(f"stop={stop_reason}")
    summary_text = _dashboard_text(summary, "")
    if summary_text:
        parts.append(f"/ {summary_text}")
    return " ".join(parts)


def _dashboard_text(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    if isinstance(value, (bool, int, float)):
        return str(value)
    return fallback


def print_dashboard_dependency_batch(payload: dict[str, Any]) -> None:
    current = payload.get("current")
    if not isinstance(current, dict):
        return
    batch = current.get("dependency_batch")
    if not isinstance(batch, dict):
        return
    status = batch.get("status") or "unknown"
    summary = batch.get("summary") if isinstance(batch.get("summary"), dict) else {}
    print(
        "依赖批次："
        f"{status} / "
        f"可启动={summary.get('ready', 0)} "
        f"工作中={summary.get('running', 0)} "
        f"等待={summary.get('blocked', 0)} "
        f"需处理={summary.get('attention', 0)} "
        f"上限={summary.get('limit', 0)}"
    )
    ready = dependency_batch_items(batch, "ready_goals")
    if ready:
        print("  可启动：" + " / ".join(dependency_item_name(item) for item in ready))
    running = dependency_batch_items(batch, "running_goals")
    if running:
        print("  工作中：" + " / ".join(dependency_item_name(item) for item in running))
    blocked = dependency_batch_items(batch, "blocked_goals")
    if blocked:
        print(
            "  等待依赖："
            + " / ".join(dependency_blocked_text(item) for item in blocked)
        )
    attention = dependency_batch_items(batch, "attention_goals")
    if attention:
        print("  需要处理：" + " / ".join(dependency_item_name(item) for item in attention))


def dependency_batch_items(batch: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = batch.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dependency_item_name(item: dict[str, Any]) -> str:
    for key in ("target_name", "goal_id", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def dependency_blocked_text(item: dict[str, Any]) -> str:
    name = dependency_item_name(item)
    dependency = item.get("dependency")
    if isinstance(dependency, str) and dependency.strip():
        return f"{name} <- {dependency.strip()}"
    reason = item.get("reason")
    if isinstance(reason, str) and reason.strip():
        return f"{name} ({reason.strip()})"
    return name


def dashboard_item_suffix(item: dict[str, Any]) -> str:
    parts: list[str] = []
    if item["git_branch"]:
        parts.append(f"分支={item['git_branch']}")
    if item["managed_tmux_session"]:
        parts.append(f"tmux={item['managed_tmux_session']}")
    if item["managed_bell_event_at"]:
        parts.append(f"bell={item['managed_bell_event_at']}")
    return f" ({', '.join(parts)})" if parts else ""
