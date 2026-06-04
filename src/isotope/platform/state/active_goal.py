"""Supervisor active goal schema for public state snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class SupervisorActiveGoal:
    """Active goal payload used by Supervisor read models."""

    goal_id: str
    created_at: str
    cwd: str
    goal: str
    target_name: str
    depends_on: tuple[str, ...] = ()
    stage: str | None = None
    scope: str | None = None
    merge_gate: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.goal_id, "goal_id")
        _required_text(self.created_at, "created_at")
        _required_text(self.cwd, "cwd")
        _required_text(self.goal, "goal")
        _required_text(self.target_name, "target_name")
        object.__setattr__(self, "depends_on", tuple(_dependency_ids(self.depends_on)))
        _optional_text(self.stage, "stage")
        _optional_text(self.scope, "scope")
        _optional_text(self.merge_gate, "merge_gate")

    @classmethod
    def from_scheduler_goal(cls, goal: Any) -> "SupervisorActiveGoal":
        return cls(
            goal_id=goal.goal_id,
            created_at=goal.created_at,
            cwd=goal.cwd,
            goal=goal.goal,
            target_name=goal.target_name,
            depends_on=tuple(goal.depends_on),
            stage=goal.stage,
            scope=goal.scope,
            merge_gate=goal.merge_gate,
        )

    def to_state_payload(
        self,
        *,
        latest_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "goal_id": self.goal_id,
            "created_at": self.created_at,
            "cwd": self.cwd,
            "goal": self.goal,
            "target_name": self.target_name,
            "depends_on": list(self.depends_on),
            "stage": self.stage,
            "scope": self.scope,
            "merge_gate": self.merge_gate,
        }
        if isinstance(latest_status, dict):
            payload.update(dict(latest_status))
        return payload


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _dependency_ids(values: Iterable[Any]) -> list[str]:
    dependencies: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("depends_on must contain non-empty strings")
        dependencies.append(value)
    return dependencies
