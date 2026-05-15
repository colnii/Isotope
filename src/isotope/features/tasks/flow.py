"""User-facing task feature flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core import CoreTaskState, ProductCore


@dataclass(frozen=True)
class TaskSummary:
    task_id: str
    goal: str
    status: str
    turn_count: int
    run_ids: tuple[str, ...]
    latest_run_id: str | None
    result_summary: str | None
    result_ref: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "turn_count": self.turn_count,
            "run_ids": list(self.run_ids),
            "latest_run_id": self.latest_run_id,
            "result_summary": self.result_summary,
            "result_ref": dict(self.result_ref) if self.result_ref is not None else None,
        }


class TaskFlow:
    """Thin user-facing task flow over ProductCore."""

    def __init__(self, core: ProductCore):
        self.core = core

    @classmethod
    def in_process(cls, root: Path | str) -> "TaskFlow":
        return cls(ProductCore.in_process(root))

    def create_task(self, *, goal: str, first_message: str | None = None) -> TaskSummary:
        task = self.core.start_task(goal=goal)
        if first_message is not None:
            return self.submit_message(task.task_id, first_message)
        return self.get_task(task.task_id)

    def submit_message(self, task_id: str, message: str) -> TaskSummary:
        state = self.core.submit_task_message(task_id, message)
        return self._summarize(state)

    def get_task(self, task_id: str) -> TaskSummary:
        return self._summarize(self.core.get_task(task_id))

    def _summarize(self, state: CoreTaskState) -> TaskSummary:
        run_ids = state.conversation.run_ids
        return TaskSummary(
            task_id=state.task_id,
            goal=state.goal,
            status=state.status,
            turn_count=len(state.conversation.turns),
            run_ids=run_ids,
            latest_run_id=run_ids[-1] if run_ids else None,
            result_summary=state.result_summary,
            result_ref=state.result_ref,
        )
