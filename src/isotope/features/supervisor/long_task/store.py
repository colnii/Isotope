"""File-backed store for Supervisor long-task metadata."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .contracts import LongTaskControlRecord, LongTaskRecord


class LongTaskStore:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser()
        self.dir = self.root / "long_tasks"
        self.tasks_path = self.dir / "tasks.jsonl"
        self.controls_path = self.dir / "controls.jsonl"

    def append_task_record(self, record: LongTaskRecord) -> LongTaskRecord:
        _append_jsonl(self.tasks_path, record.to_dict())
        return record

    def append_control_record(
        self,
        record: LongTaskControlRecord,
    ) -> LongTaskControlRecord:
        _append_jsonl(self.controls_path, record.to_dict())
        return record

    def read_task_records(self) -> list[LongTaskRecord]:
        return [
            LongTaskRecord.from_dict(payload)
            for payload in _read_jsonl(self.tasks_path, label="tasks.jsonl")
        ]

    def read_control_records(self) -> list[LongTaskControlRecord]:
        return [
            LongTaskControlRecord.from_dict(payload)
            for payload in _read_jsonl(self.controls_path, label="controls.jsonl")
        ]

    def projection(self, task_id: str) -> dict[str, Any]:
        return long_task_projection(self, task_id)

    def list_task_projections(self) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for record in self.read_task_records():
            latest[record.task_id] = _projection_from_record(record)
        for control in self.read_control_records():
            if control.task_id not in latest:
                continue
            _apply_control(latest[control.task_id], control)
        return sorted(
            latest.values(),
            key=lambda item: str(item.get("updated_at", "")),
            reverse=True,
        )


def append_long_task_record(
    store: LongTaskStore,
    record: LongTaskRecord,
) -> LongTaskRecord:
    return store.append_task_record(record)


def append_long_task_control(
    store: LongTaskStore,
    *,
    task_id: str,
    control: str,
    reason: str,
    created_at: str,
) -> LongTaskControlRecord:
    return store.append_control_record(
        LongTaskControlRecord(
            task_id=task_id,
            control=control,
            reason=reason,
            created_at=created_at,
        )
    )


def long_task_projection(store: LongTaskStore, task_id: str) -> dict[str, Any]:
    projections = {item["task_id"]: item for item in store.list_task_projections()}
    if task_id not in projections:
        raise ValueError(f"unknown long task: {task_id}")
    return projections[task_id]


def _projection_from_record(record: LongTaskRecord) -> dict[str, Any]:
    payload = record.to_dict()
    payload["requires_human"] = record.status in {"paused", "blocked"}
    return payload


def _apply_control(payload: dict[str, Any], control: LongTaskControlRecord) -> None:
    payload["control_state"] = control.control
    payload["updated_at"] = control.created_at
    payload["control_reason"] = control.reason
    if control.control == "pause":
        payload["status"] = "paused"
        payload["requires_human"] = True
    elif control.control == "stop":
        payload["status"] = "stopped"
        payload["requires_human"] = False
    elif control.control in {"resume", "run"}:
        if payload.get("status") in {"paused", "stopped", "queued"}:
            payload["status"] = "queued"
        payload["requires_human"] = False


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payloads: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except JSONDecodeError as exc:
            raise ValueError(f"{label} line {line_number} is malformed") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{label} line {line_number} must be an object")
        payloads.append(payload)
    return payloads
