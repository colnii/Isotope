"""Persistent goals for the Codex Supervisor loop."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from ....agents.scheduler.goal_events import (
    SupervisorGoal,
    active_supervisor_goals_from_events,
    latest_supervisor_goal_statuses_from_events,
)
from ....agents.scheduler.goal_queue import (
    GOAL_QUEUE_VIEW_GROUPS,
    build_supervisor_goal_queue_view,
)
from ....platform.state.goal_status import GOAL_STATUS_VALUES, SupervisorGoalStatus
from ..notifications.notifications import notify_goal_status_written


def default_goals_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "goals.jsonl"


def record_supervisor_goal(
    *,
    codex_home: Path | str,
    cwd: Path | str,
    goal: str,
    target_name: str | None = None,
    depends_on: Iterable[str] = (),
    stage: str | None = None,
    scope: str | None = None,
    merge_gate: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> SupervisorGoal:
    workspace = Path(cwd).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    goal_text = _required_string(goal, "goal")
    goal_id = "goal-" + uuid.uuid4().hex[:12]
    target = _optional_string(target_name) or goal_id
    item = SupervisorGoal(
        goal_id=goal_id,
        created_at=_ensure_aware_utc((now or _utc_now)()).isoformat(),
        cwd=str(workspace),
        goal=goal_text,
        target_name=target,
        depends_on=tuple(
            dependency
            for value in depends_on
            for dependency in (_optional_string(value),)
            if dependency is not None
        ),
        stage=_optional_string(stage),
        scope=_optional_string(scope),
        merge_gate=_optional_string(merge_gate),
    )
    append_goal_event(default_goals_path(codex_home), item.to_dict())
    return item


def archive_supervisor_goal(
    *,
    codex_home: Path | str,
    goal_id: str,
    status: str | None = None,
    target_name: str | None = None,
    session_id: str | None = None,
    summary: str | None = None,
    next_step: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    goal_id_text = _required_string(goal_id, "goal_id")
    active = {
        goal.goal_id
        for goal in read_active_supervisor_goals(codex_home=codex_home, limit=1000)
    }
    if goal_id_text not in active:
        raise ValueError(f"active supervisor goal not found: {goal_id_text}")
    event = {
        "event": "supervisor_goal_archive",
        "goal_id": goal_id_text,
        "created_at": _ensure_aware_utc((now or _utc_now)()).isoformat(),
    }
    _add_optional_event_fields(
        event,
        status=status,
        target_name=target_name,
        session_id=session_id,
        summary=summary,
        next_step=next_step,
    )
    append_goal_event(default_goals_path(codex_home), event)
    return event


def record_supervisor_goal_status(
    *,
    codex_home: Path | str,
    goal_id: str,
    status: str,
    target_name: str | None = None,
    session_id: str | None = None,
    summary: str | None = None,
    next_step: str | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any] | None:
    goal_id_text = _required_string(goal_id, "goal_id")
    status_text = _required_string(status, "status").lower()
    if status_text not in GOAL_STATUS_VALUES:
        supported = ", ".join(sorted(GOAL_STATUS_VALUES))
        raise ValueError(f"status must be one of: {supported}")
    active = {
        goal.goal_id
        for goal in read_active_supervisor_goals(codex_home=codex_home, limit=1000)
    }
    if goal_id_text not in active:
        raise ValueError(f"active supervisor goal not found: {goal_id_text}")
    event = {
        "event": "supervisor_goal_status",
        "goal_id": goal_id_text,
        "status": status_text,
        "created_at": _ensure_aware_utc((now or _utc_now)()).isoformat(),
    }
    _add_optional_event_fields(
        event,
        target_name=target_name,
        session_id=session_id,
        summary=summary,
        next_step=next_step,
    )
    path = default_goals_path(codex_home)
    latest = _latest_goal_status_event(path, goal_id_text)
    if latest is not None and _status_event_matches(latest, event):
        return None
    append_goal_event(path, event)
    notify_goal_status_written(
        codex_home=codex_home,
        goal_id=goal_id_text,
        status=status_text,
        target_name=event.get("target_name"),
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
    return event


def read_active_supervisor_goals(
    *,
    codex_home: Path | str,
    limit: int = 20,
) -> tuple[SupervisorGoal, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    path = default_goals_path(codex_home)
    if not path.is_file():
        return ()
    return active_supervisor_goals_from_events(_read_goal_event_dicts(path), limit=limit)


def read_latest_supervisor_goal_statuses(
    *,
    codex_home: Path | str,
) -> dict[str, dict[str, Any]]:
    return latest_supervisor_goal_statuses_from_events(
        _read_goal_event_dicts(default_goals_path(codex_home))
    )


def append_goal_event(path: Path | str, event: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _latest_goal_status_event(path: Path | str, goal_id: str) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for raw in _read_goal_event_dicts(Path(path).expanduser()):
        if raw.get("event") != "supervisor_goal_status":
            continue
        if raw.get("goal_id") == goal_id:
            latest = raw
    return latest


def _status_event_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = ("goal_id", "status", "target_name", "session_id", "summary", "next")
    return all(left.get(key) == right.get(key) for key in keys)


def _read_goal_event_dicts(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            events.append(raw)
    return tuple(events)


def _add_optional_event_fields(
    event: dict[str, Any],
    *,
    status: str | None = None,
    target_name: str | None = None,
    session_id: str | None = None,
    summary: str | None = None,
    next_step: str | None = None,
) -> None:
    for key, value in (
        ("status", status),
        ("target_name", target_name),
        ("session_id", session_id),
        ("summary", summary),
        ("next", next_step),
    ):
        text = _optional_string(value)
        if text is not None:
            event[key] = text


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
