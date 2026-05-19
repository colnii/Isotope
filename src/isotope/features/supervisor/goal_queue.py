"""Persistent goals for the Codex Supervisor loop."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class SupervisorGoal:
    goal_id: str
    created_at: str
    cwd: str
    goal: str
    target_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": "supervisor_goal",
            "goal_id": self.goal_id,
            "created_at": self.created_at,
            "cwd": self.cwd,
            "goal": self.goal,
            "target_name": self.target_name,
        }


def default_goals_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "goals.jsonl"


def record_supervisor_goal(
    *,
    codex_home: Path | str,
    cwd: Path | str,
    goal: str,
    target_name: str | None = None,
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
    )
    append_goal_event(default_goals_path(codex_home), item.to_dict())
    return item


def archive_supervisor_goal(
    *,
    codex_home: Path | str,
    goal_id: str,
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
    append_goal_event(default_goals_path(codex_home), event)
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


def append_goal_event(path: Path | str, event: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


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
    )


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
