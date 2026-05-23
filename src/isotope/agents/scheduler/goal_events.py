"""Pure goal event parsing helpers for scheduler-owned queue facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from isotope.platform.state.goal_status import GOAL_STATUS_VALUES, SupervisorGoalStatus


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


def active_supervisor_goals_from_events(
    events: Iterable[dict[str, Any]],
    *,
    limit: int,
) -> tuple[SupervisorGoal, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    latest: dict[str, SupervisorGoal] = {}
    archived: set[str] = set()
    for raw in events:
        archived_id = archive_supervisor_goal_id(raw)
        if archived_id is not None:
            archived.add(archived_id)
            latest.pop(archived_id, None)
            continue
        goal = supervisor_goal_from_event(raw)
        if goal is None or goal.goal_id in archived:
            continue
        latest[goal.goal_id] = goal
    goals = sorted(latest.values(), key=lambda item: item.created_at)
    return tuple(goals[:limit])


def latest_supervisor_goal_statuses_from_events(
    events: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for raw in events:
        if raw.get("event") != "supervisor_goal_status":
            continue
        status = supervisor_goal_status_from_event(raw)
        if status is not None:
            latest[status["goal_id"]] = status
    return latest


def archive_supervisor_goal_id(raw: dict[str, Any]) -> str | None:
    if raw.get("event") != "supervisor_goal_archive":
        return None
    goal_id = raw.get("goal_id")
    if not isinstance(goal_id, str) or not goal_id:
        return None
    return goal_id


def supervisor_goal_from_event(raw: dict[str, Any]) -> SupervisorGoal | None:
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


def supervisor_goal_status_from_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    status = SupervisorGoalStatus.from_event(raw)
    if status is None:
        return None
    return status.to_latest_payload()


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
