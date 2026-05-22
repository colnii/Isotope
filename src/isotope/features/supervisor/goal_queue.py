"""Persistent goals for the Codex Supervisor loop."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from ...agents.scheduler.goal_queue import (
    GOAL_QUEUE_VIEW_GROUPS,
    build_supervisor_goal_queue_view,
)
from .notifications import notify_goal_status_written

GOAL_STATUS_VALUES = {"done", "blocked", "needs_user"}


@dataclass(frozen=True)
class SupervisorGoal:
    goal_id: str
    created_at: str
    cwd: str
    goal: str
    target_name: str
    depends_on: tuple[str, ...] = ()
    stage: str | None = None
    scope: str | None = None
    merge_gate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "event": "supervisor_goal",
            "goal_id": self.goal_id,
            "created_at": self.created_at,
            "cwd": self.cwd,
            "goal": self.goal,
            "target_name": self.target_name,
        }
        if self.depends_on:
            item["depends_on"] = list(self.depends_on)
        if self.stage is not None:
            item["stage"] = self.stage
        if self.scope is not None:
            item["scope"] = self.scope
        if self.merge_gate is not None:
            item["merge_gate"] = self.merge_gate
        return item


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
    latest: dict[str, SupervisorGoal] = {}
    archived: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        archived_id = _archive_goal_id(raw)
        if archived_id is not None:
            archived.add(archived_id)
            latest.pop(archived_id, None)
            continue
        goal = _goal_from_dict(raw)
        if goal is None or goal.goal_id in archived:
            continue
        latest[goal.goal_id] = goal
    goals = sorted(latest.values(), key=lambda item: item.created_at)
    return tuple(goals[:limit])


def read_latest_supervisor_goal_statuses(
    *,
    codex_home: Path | str,
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for raw in _read_goal_event_dicts(default_goals_path(codex_home)):
        if raw.get("event") != "supervisor_goal_status":
            continue
        status = _goal_status_from_dict(raw)
        if status is not None:
            latest[status["goal_id"]] = status
    return latest


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


def _archive_goal_id(raw: dict[str, Any]) -> str | None:
    if raw.get("event") != "supervisor_goal_archive":
        return None
    goal_id = raw.get("goal_id")
    if not isinstance(goal_id, str) or not goal_id:
        return None
    return goal_id


def _goal_from_dict(raw: dict[str, Any]) -> SupervisorGoal | None:
    if raw.get("event") != "supervisor_goal":
        return None
    goal_id = raw.get("goal_id")
    created_at = raw.get("created_at")
    cwd = raw.get("cwd")
    goal = raw.get("goal")
    target_name = raw.get("target_name")
    if not all(
        isinstance(value, str) and value
        for value in (goal_id, created_at, cwd, goal, target_name)
    ):
        return None
    return SupervisorGoal(
        goal_id=goal_id,
        created_at=created_at,
        cwd=cwd,
        goal=goal,
        target_name=target_name,
        depends_on=tuple(_string_list(raw.get("depends_on"))),
        stage=_optional_string(raw.get("stage")),
        scope=_optional_string(raw.get("scope")),
        merge_gate=_optional_string(raw.get("merge_gate")),
    )


def _goal_status_from_dict(raw: dict[str, Any]) -> dict[str, Any] | None:
    goal_id = raw.get("goal_id")
    status = raw.get("status")
    created_at = raw.get("created_at")
    if not all(isinstance(value, str) and value for value in (goal_id, status, created_at)):
        return None
    if status not in GOAL_STATUS_VALUES:
        return None
    item: dict[str, Any] = {
        "goal_id": goal_id,
        "last_status": status,
        "last_status_at": created_at,
    }
    for source_key, target_key in (
        ("target_name", "last_target_name"),
        ("session_id", "last_session_id"),
        ("summary", "last_summary"),
        ("next", "last_next"),
    ):
        value = raw.get(source_key)
        if isinstance(value, str) and value:
            item[target_key] = value
    return item


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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _optional_string(item)
        if text is not None:
            items.append(text)
    return items


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
