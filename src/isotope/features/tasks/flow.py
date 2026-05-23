"""User-facing task feature flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ...core import CoreTaskState, ProductCore
from ...platform.schemas.refs import ResourceRef


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskSummary":
        latest_run_id = data.get("latest_run_id")
        result_summary = data.get("result_summary")
        result_ref = data.get("result_ref")
        if latest_run_id is not None and not isinstance(latest_run_id, str):
            raise ValueError("task summary requires latest_run_id")
        if result_summary is not None and not isinstance(result_summary, str):
            raise ValueError("task summary requires result_summary")
        if result_ref is not None and not isinstance(result_ref, dict):
            raise ValueError("task summary requires result_ref")
        return cls(
            task_id=_required_string(data, "task_id"),
            goal=_required_string(data, "goal"),
            status=_required_string(data, "status"),
            turn_count=_required_int(data, "turn_count"),
            run_ids=tuple(_required_string_list(data, "run_ids")),
            latest_run_id=latest_run_id,
            result_summary=result_summary,
            result_ref=dict(result_ref) if result_ref is not None else None,
        )


class TaskFlow:
    """Thin user-facing task flow over ProductCore."""

    def __init__(self, core: ProductCore):
        self.core = core
        self._index_path = Path(self.core.runtime.root) / "tasks" / "index.json"
        self._tasks: dict[str, TaskSummary] = self._load_index()

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
        return self._store_summary(self._summarize(state))

    def get_task(self, task_id: str) -> TaskSummary:
        try:
            summary = self._summarize(self.core.get_task(task_id))
            refreshed = self._refresh_from_result_record(summary)
            return self._store_summary(refreshed)
        except ValueError as exc:
            if "unknown task_id" not in str(exc):
                raise
            try:
                return self._refresh_from_result_record(self._tasks[task_id])
            except KeyError:
                raise exc

    def list_tasks(self) -> list[TaskSummary]:
        return [
            self._refresh_from_result_record(summary)
            for summary in self._tasks.values()
        ]

    def _refresh_from_result_record(self, summary: TaskSummary) -> TaskSummary:
        if summary.result_ref is None:
            return summary
        result_ref = _artifact_ref_from_dict(summary.result_ref)
        record = self.core.runtime.get_artifact_record(result_ref)
        refreshed = TaskSummary(
            task_id=summary.task_id,
            goal=summary.goal,
            status=summary.status,
            turn_count=summary.turn_count,
            run_ids=summary.run_ids,
            latest_run_id=summary.latest_run_id,
            result_summary=_required_string(record, "summary"),
            result_ref=dict(_required_dict(record, "ref")),
        )
        if refreshed != summary:
            self._tasks[summary.task_id] = refreshed
            self._save_index()
        return refreshed

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

    def _store_summary(self, summary: TaskSummary) -> TaskSummary:
        self._tasks[summary.task_id] = summary
        self._save_index()
        return summary

    def _load_index(self) -> dict[str, TaskSummary]:
        if not self._index_path.exists():
            return {}
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError(f"malformed task index: {self._index_path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
            raise ValueError(f"malformed task index: {self._index_path}")
        tasks: dict[str, TaskSummary] = {}
        for item in data["tasks"]:
            if not isinstance(item, dict):
                raise ValueError(f"malformed task index: {self._index_path}")
            summary = TaskSummary.from_dict(item)
            tasks[summary.task_id] = summary
        return tasks

    def _save_index(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tasks": [task_summary.to_dict() for task_summary in self._tasks.values()]
        }
        self._index_path.write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"task summary requires {field_name}")
    return value


def _required_int(data: dict[str, Any], field_name: str) -> int:
    value = data.get(field_name)
    if not isinstance(value, int):
        raise ValueError(f"task summary requires {field_name}")
    return value


def _required_dict(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = data.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"task summary requires {field_name}")
    return value


def _required_string_list(data: dict[str, Any], field_name: str) -> list[str]:
    value = data.get(field_name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"task summary requires {field_name}")
    return value


def _artifact_ref_from_dict(data: dict[str, Any]) -> ResourceRef:
    return ResourceRef(
        ref_type=_required_string(data, "ref_type"),
        scope=_required_string(data, "scope"),
        run_id=_required_string(data, "run_id"),
        artifact_id=_required_string(data, "artifact_id"),
    )
