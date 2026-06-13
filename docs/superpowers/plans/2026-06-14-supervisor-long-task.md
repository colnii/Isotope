# Supervisor Long Task Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the durable Supervisor long-task backend contract, CLI verification surface, bounded tick runner, and thin desktop status/control adapter.

**Architecture:** Add a focused `src/isotope/features/supervisor/long_task/` package. Task records are an append-only index/control ledger; run events and checkpoints remain the execution source of truth. CLI and desktop routes consume the same folded projection.

**Tech Stack:** Python 3.13, dataclasses, JSONL file storage, existing `InProcessServer`, existing agent-loop provider planner, pytest.

---

## File Structure

- Create `src/isotope/features/supervisor/long_task/__init__.py`: public exports.
- Create `src/isotope/features/supervisor/long_task/contracts.py`: dataclasses, status/control constants, raw-payload guard.
- Create `src/isotope/features/supervisor/long_task/store.py`: JSONL append/read and projection folding.
- Create `src/isotope/features/supervisor/long_task/runtime.py`: start/status/list/control/run operations over `InProcessServer`.
- Create `src/isotope/features/supervisor/long_task/provider.py`: pooled `.generate()` planner provider resolver for CLI long-task runs.
- Create `src/isotope/features/supervisor/commands/parser/long_task.py`: isolated parser registration.
- Create `src/isotope/features/supervisor/commands/handlers/long_task.py`: CLI handler and plain output.
- Modify `src/isotope/features/supervisor/commands/parser/__init__.py`: import and call `add_long_task_command_parser`.
- Modify `src/isotope/features/supervisor/commands/dispatch.py`: register `long-task` handler.
- Create `src/isotope/features/supervisor/web/routes/long_tasks.py`: desktop path and payload parsers.
- Create `src/isotope/features/supervisor/web/routes/long_tasks_dispatch.py`: thin HTTP dispatch.
- Modify `src/isotope/features/supervisor/web/_impl.py`: route GET/POST long-task endpoints.
- Modify `src/isotope/features/supervisor/desktop_snapshot.py`: include compact `longTasks` projection.
- Create `tests/unit/features/supervisor/long_task/test_long_task_store.py`.
- Create `tests/unit/features/supervisor/long_task/test_long_task_runtime.py`.
- Create `tests/integration/supervisor/test_supervisor_long_task_cli.py`.
- Create `tests/unit/features/supervisor/web/test_long_task_routes.py`.

## Task 1: Contracts And Store

**Files:**
- Create: `src/isotope/features/supervisor/long_task/__init__.py`
- Create: `src/isotope/features/supervisor/long_task/contracts.py`
- Create: `src/isotope/features/supervisor/long_task/store.py`
- Test: `tests/unit/features/supervisor/long_task/test_long_task_store.py`

- [ ] **Step 1: Write the failing store tests**

Create `tests/unit/features/supervisor/long_task/test_long_task_store.py`:

```python
from __future__ import annotations

import json

import pytest

from isotope.features.supervisor.long_task import (
    LongTaskRecord,
    LongTaskStore,
    append_long_task_control,
    append_long_task_record,
    long_task_projection,
)


def test_long_task_store_appends_and_folds_projection(tmp_path):
    store = LongTaskStore(tmp_path)
    append_long_task_record(
        store,
        LongTaskRecord(
            task_id="ltask_001",
            run_id="run_001",
            session_id="session_001",
            goal="Ship long tasks",
            status="queued",
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-14T00:00:00Z",
        ),
    )
    append_long_task_control(
        store,
        task_id="ltask_001",
        control="pause",
        reason="User paused from CLI.",
        created_at="2026-06-14T00:01:00Z",
    )

    projection = long_task_projection(store, "ltask_001")

    assert projection["task_id"] == "ltask_001"
    assert projection["status"] == "paused"
    assert projection["control_state"] == "pause"
    assert projection["requires_human"] is True
    assert projection["goal"] == "Ship long tasks"


def test_long_task_public_projection_rejects_raw_content(tmp_path):
    store = LongTaskStore(tmp_path)

    with pytest.raises(ValueError, match="raw long-task payload"):
        append_long_task_record(
            store,
            LongTaskRecord(
                task_id="ltask_raw",
                run_id="run_001",
                session_id="session_001",
                goal="bad",
                status="queued",
                created_at="2026-06-14T00:00:00Z",
                updated_at="2026-06-14T00:00:00Z",
                summary={"raw_content": "hidden"},
            ),
        )


def test_long_task_store_reports_malformed_json_line(tmp_path):
    store = LongTaskStore(tmp_path)
    store.tasks_path.parent.mkdir(parents=True, exist_ok=True)
    store.tasks_path.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tasks.jsonl line 1"):
        store.read_task_records()


def test_long_task_list_orders_latest_update_first(tmp_path):
    store = LongTaskStore(tmp_path)
    append_long_task_record(
        store,
        LongTaskRecord(
            task_id="ltask_old",
            run_id="run_old",
            session_id="session_old",
            goal="Old",
            status="queued",
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-14T00:00:00Z",
        ),
    )
    append_long_task_record(
        store,
        LongTaskRecord(
            task_id="ltask_new",
            run_id="run_new",
            session_id="session_new",
            goal="New",
            status="queued",
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-14T00:02:00Z",
        ),
    )

    assert [item["task_id"] for item in store.list_task_projections()] == [
        "ltask_new",
        "ltask_old",
    ]
    assert json.loads(store.tasks_path.read_text(encoding="utf-8").splitlines()[0])[
        "task_id"
    ] == "ltask_old"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task/test_long_task_store.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'isotope.features.supervisor.long_task'`.

- [ ] **Step 3: Implement contracts and store**

Create `src/isotope/features/supervisor/long_task/contracts.py`:

```python
"""Contracts for Supervisor long tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TASK_STATUSES = {
    "queued",
    "running",
    "paused",
    "stopping",
    "stopped",
    "completed",
    "failed",
    "blocked",
}
CONTROL_STATES = {"run", "pause", "resume", "stop"}
RAW_LONG_TASK_FIELDS = {
    "api_key",
    "artifact_content",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_artifact_content",
    "raw_content",
    "raw_prompt",
    "raw_provider_response",
    "raw_response",
    "secret",
    "stderr",
    "stdin",
    "stdout",
    "token",
}


@dataclass(frozen=True)
class LongTaskRecord:
    task_id: str
    run_id: str
    session_id: str
    goal: str
    status: str
    created_at: str
    updated_at: str
    last_event_id: str = ""
    last_checkpoint_event_id: str = ""
    heartbeat: dict[str, Any] = field(default_factory=dict)
    control_state: str = "run"
    summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.task_id, "task_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.session_id, "session_id")
        _require_text(self.goal, "goal")
        _require_choice(self.status, TASK_STATUSES, "status")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        _require_optional_text(self.last_event_id, "last_event_id")
        _require_optional_text(self.last_checkpoint_event_id, "last_checkpoint_event_id")
        _require_choice(self.control_state, CONTROL_STATES, "control_state")
        if not isinstance(self.heartbeat, dict):
            raise ValueError("heartbeat must be a dict")
        if not isinstance(self.summary, dict):
            raise ValueError("summary must be a dict")
        reject_raw_long_task_payload(self.heartbeat)
        reject_raw_long_task_payload(self.summary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_event_id": self.last_event_id,
            "last_checkpoint_event_id": self.last_checkpoint_event_id,
            "heartbeat": _copy_public_payload(self.heartbeat),
            "control_state": self.control_state,
            "summary": _copy_public_payload(self.summary),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LongTaskRecord":
        return cls(
            task_id=_dict_text(payload, "task_id"),
            run_id=_dict_text(payload, "run_id"),
            session_id=_dict_text(payload, "session_id"),
            goal=_dict_text(payload, "goal"),
            status=_dict_text(payload, "status"),
            created_at=_dict_text(payload, "created_at"),
            updated_at=_dict_text(payload, "updated_at"),
            last_event_id=str(payload.get("last_event_id") or ""),
            last_checkpoint_event_id=str(payload.get("last_checkpoint_event_id") or ""),
            heartbeat=_dict_payload(payload.get("heartbeat")),
            control_state=str(payload.get("control_state") or "run"),
            summary=_dict_payload(payload.get("summary")),
        )


@dataclass(frozen=True)
class LongTaskControlRecord:
    task_id: str
    control: str
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.task_id, "task_id")
        _require_choice(self.control, CONTROL_STATES, "control")
        _require_text(self.reason, "reason")
        _require_text(self.created_at, "created_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "control": self.control,
            "reason": self.reason,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LongTaskControlRecord":
        return cls(
            task_id=_dict_text(payload, "task_id"),
            control=_dict_text(payload, "control"),
            reason=_dict_text(payload, "reason"),
            created_at=_dict_text(payload, "created_at"),
        )


def reject_raw_long_task_payload(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = RAW_LONG_TASK_FIELDS.intersection(value)
        if forbidden:
            raise ValueError("raw long-task payload fields are not allowed")
        for nested in value.values():
            reject_raw_long_task_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_raw_long_task_payload(nested)


def _copy_public_payload(value: Any) -> Any:
    reject_raw_long_task_payload(value)
    if isinstance(value, dict):
        return {str(key): _copy_public_payload(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_copy_public_payload(nested) for nested in value]
    return value


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_optional_text(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")


def _require_choice(value: object, choices: set[str], field_name: str) -> str:
    if value not in choices:
        raise ValueError(f"{field_name} must be one of {sorted(choices)}")
    return str(value)


def _dict_text(payload: dict[str, Any], field_name: str) -> str:
    return _require_text(payload.get(field_name), field_name)


def _dict_payload(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("payload value must be a dict")
    reject_raw_long_task_payload(value)
    return dict(value)
```

Create `src/isotope/features/supervisor/long_task/store.py`:

```python
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

    def append_control_record(self, record: LongTaskControlRecord) -> LongTaskControlRecord:
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


def append_long_task_record(store: LongTaskStore, record: LongTaskRecord) -> LongTaskRecord:
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
    projections = {
        item["task_id"]: item
        for item in store.list_task_projections()
    }
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
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
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
```

Create `src/isotope/features/supervisor/long_task/__init__.py`:

```python
"""Supervisor long-task backend contract."""

from __future__ import annotations

from .contracts import LongTaskControlRecord, LongTaskRecord
from .store import (
    LongTaskStore,
    append_long_task_control,
    append_long_task_record,
    long_task_projection,
)

__all__ = [
    "LongTaskControlRecord",
    "LongTaskRecord",
    "LongTaskStore",
    "append_long_task_control",
    "append_long_task_record",
    "long_task_projection",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task/test_long_task_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/supervisor/long_task tests/unit/features/supervisor/long_task/test_long_task_store.py
git commit -m "feat(supervisor): add long task metadata store"
```

## Task 2: Runtime Start, Status, And Control

**Files:**
- Create: `src/isotope/features/supervisor/long_task/runtime.py`
- Modify: `src/isotope/features/supervisor/long_task/__init__.py`
- Test: `tests/unit/features/supervisor/long_task/test_long_task_runtime.py`

- [ ] **Step 1: Write the failing runtime tests**

Create `tests/unit/features/supervisor/long_task/test_long_task_runtime.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.long_task.runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    resume_long_task,
    status_long_task,
    stop_long_task,
)


def test_create_long_task_creates_run_and_queued_projection(tmp_path):
    result = create_long_task(tmp_path, goal="Run a long Supervisor task.")

    assert result["status"] == "ok"
    assert result["task"]["status"] == "queued"
    assert result["task"]["goal"] == "Run a long Supervisor task."
    assert result["task"]["run_id"].startswith("run_")
    assert result["task"]["session_id"].startswith("session_")

    status = status_long_task(tmp_path, result["task"]["task_id"])
    assert status["task"]["task_id"] == result["task"]["task_id"]
    assert status["task"]["run_status"] == "active"


def test_pause_resume_and_stop_long_task_update_projection(tmp_path):
    task_id = create_long_task(tmp_path, goal="Pause me.")["task"]["task_id"]

    paused = pause_long_task(tmp_path, task_id, reason="Need user review.")
    assert paused["task"]["status"] == "paused"
    assert paused["task"]["requires_human"] is True

    resumed = resume_long_task(tmp_path, task_id, reason="Continue.")
    assert resumed["task"]["status"] == "queued"
    assert resumed["task"]["control_state"] == "resume"

    stopped = stop_long_task(tmp_path, task_id, reason="User stopped.")
    assert stopped["task"]["status"] == "stopped"
    assert stopped["task"]["requires_human"] is False


def test_list_long_tasks_uses_same_projection(tmp_path):
    first = create_long_task(tmp_path, goal="First")["task"]["task_id"]
    second = create_long_task(tmp_path, goal="Second")["task"]["task_id"]
    pause_long_task(tmp_path, first, reason="Hold first.")

    listed = list_long_tasks(tmp_path)

    assert listed["summary"]["task_count"] == 2
    assert {task["task_id"] for task in listed["tasks"]} == {first, second}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task/test_long_task_runtime.py -q
```

Expected: FAIL because `isotope.features.supervisor.long_task.runtime` does not exist.

- [ ] **Step 3: Implement runtime start/status/control**

Create `src/isotope/features/supervisor/long_task/runtime.py`:

```python
"""Runtime operations for Supervisor long tasks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from isotope.platform.ids import new_id
from isotope.runtime.in_process import InProcessServer

from .contracts import LongTaskRecord
from .store import LongTaskStore, append_long_task_control


TERMINAL_RUN_STATUSES = {"completed", "failed", "denied"}


def create_long_task(root: Path | str, *, goal: str) -> dict[str, Any]:
    _require_text(goal, "goal")
    root_path = Path(root).expanduser()
    api = InProcessServer(root_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal=goal)
    state = api.get_run_state(run["run_id"])
    now = _now()
    record = LongTaskRecord(
        task_id=new_id("ltask"),
        run_id=run["run_id"],
        session_id=session["session_id"],
        goal=goal,
        status="queued",
        created_at=now,
        updated_at=now,
        last_event_id=state.last_event_id,
        summary={"phase": "created", "tick_count": 0},
    )
    store = LongTaskStore(root_path)
    store.append_task_record(record)
    return {"status": "ok", "task": _attach_run_status(root_path, record.to_dict())}


def status_long_task(root: Path | str, task_id: str) -> dict[str, Any]:
    store = LongTaskStore(root)
    return {"status": "ok", "task": _attach_run_status(Path(root).expanduser(), store.projection(task_id))}


def list_long_tasks(root: Path | str) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    tasks = [
        _attach_run_status(root_path, task)
        for task in LongTaskStore(root_path).list_task_projections()
    ]
    return {"status": "ok", "summary": {"task_count": len(tasks)}, "tasks": tasks}


def pause_long_task(root: Path | str, task_id: str, *, reason: str) -> dict[str, Any]:
    return _control_long_task(root, task_id, control="pause", reason=reason)


def resume_long_task(root: Path | str, task_id: str, *, reason: str) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    projection = _attach_run_status(root_path, LongTaskStore(root_path).projection(task_id))
    if projection.get("run_status") in TERMINAL_RUN_STATUSES:
        raise ValueError("terminal long task cannot be resumed")
    return _control_long_task(root_path, task_id, control="resume", reason=reason)


def stop_long_task(root: Path | str, task_id: str, *, reason: str) -> dict[str, Any]:
    return _control_long_task(root, task_id, control="stop", reason=reason)


def _control_long_task(root: Path | str, task_id: str, *, control: str, reason: str) -> dict[str, Any]:
    _require_text(task_id, "task_id")
    _require_text(reason, "reason")
    root_path = Path(root).expanduser()
    store = LongTaskStore(root_path)
    store.projection(task_id)
    append_long_task_control(
        store,
        task_id=task_id,
        control=control,
        reason=reason,
        created_at=_now(),
    )
    return {"status": "ok", "task": _attach_run_status(root_path, store.projection(task_id))}


def _attach_run_status(root: Path, projection: dict[str, Any]) -> dict[str, Any]:
    task = dict(projection)
    api = InProcessServer(root)
    run_state = api.get_run_state(str(task["run_id"]))
    task["run_status"] = run_state.status
    task["last_event_id"] = run_state.last_event_id or str(task.get("last_event_id", ""))
    return task


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
```

Modify `src/isotope/features/supervisor/long_task/__init__.py` to export runtime functions:

```python
from .runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    resume_long_task,
    status_long_task,
    stop_long_task,
)
```

Append those names to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task/test_long_task_store.py \
  tests/unit/features/supervisor/long_task/test_long_task_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/supervisor/long_task tests/unit/features/supervisor/long_task/test_long_task_runtime.py
git commit -m "feat(supervisor): add long task runtime controls"
```

## Task 3: CLI Start, Status, List, Pause, Resume, Stop

**Files:**
- Create: `src/isotope/features/supervisor/commands/parser/long_task.py`
- Create: `src/isotope/features/supervisor/commands/handlers/long_task.py`
- Modify: `src/isotope/features/supervisor/commands/parser/__init__.py`
- Modify: `src/isotope/features/supervisor/commands/dispatch.py`
- Test: `tests/integration/supervisor/test_supervisor_long_task_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

Create `tests/integration/supervisor/test_supervisor_long_task_cli.py`:

```python
from __future__ import annotations

import json

from isotope.features.supervisor import runner


def test_supervisor_long_task_start_status_and_list_cli(tmp_path, capsys):
    assert runner.main(
        [
            "long-task",
            "start",
            "--state-root",
            str(tmp_path),
            "--goal",
            "Run a durable task.",
            "--json",
        ]
    ) == 0
    started = json.loads(capsys.readouterr().out)
    task_id = started["task"]["task_id"]
    assert started["task"]["status"] == "queued"

    assert runner.main(
        [
            "long-task",
            "status",
            "--state-root",
            str(tmp_path),
            "--task-id",
            task_id,
            "--json",
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["task"]["task_id"] == task_id
    assert status["task"]["run_status"] == "active"

    assert runner.main(
        ["long-task", "list", "--state-root", str(tmp_path), "--json"]
    ) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["summary"]["task_count"] == 1


def test_supervisor_long_task_pause_resume_stop_cli(tmp_path, capsys):
    runner.main(
        [
            "long-task",
            "start",
            "--state-root",
            str(tmp_path),
            "--goal",
            "Control me.",
            "--json",
        ]
    )
    task_id = json.loads(capsys.readouterr().out)["task"]["task_id"]

    for command, expected_status in (
        ("pause", "paused"),
        ("resume", "queued"),
        ("stop", "stopped"),
    ):
        assert runner.main(
            [
                "long-task",
                command,
                "--state-root",
                str(tmp_path),
                "--task-id",
                task_id,
                "--reason",
                f"{command} from test",
                "--json",
            ]
        ) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["task"]["status"] == expected_status
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/integration/supervisor/test_supervisor_long_task_cli.py -q
```

Expected: FAIL with argparse rejecting `long-task`.

- [ ] **Step 3: Implement parser and handler**

Create `src/isotope/features/supervisor/commands/parser/long_task.py`:

```python
"""Long-task parser registration for the Supervisor CLI."""

from __future__ import annotations

import argparse

from .common import add_state_root_arg


def add_long_task_command_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "long-task",
        help="Start, inspect, and control durable Supervisor long tasks.",
    )
    task_subparsers = parser.add_subparsers(dest="long_task_command", required=True)

    start = task_subparsers.add_parser("start", help="Create a queued long task.")
    add_state_root_arg(start)
    start.add_argument("--goal", required=True)
    start.add_argument("--json", action="store_true", help="Print JSON output.")

    status = task_subparsers.add_parser("status", help="Inspect one long task.")
    add_state_root_arg(status)
    status.add_argument("--task-id", required=True)
    status.add_argument("--json", action="store_true", help="Print JSON output.")

    list_parser = task_subparsers.add_parser("list", help="List long tasks.")
    add_state_root_arg(list_parser)
    list_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    for command in ("pause", "resume", "stop"):
        control = task_subparsers.add_parser(command, help=f"{command.title()} one long task.")
        add_state_root_arg(control)
        control.add_argument("--task-id", required=True)
        control.add_argument("--reason", required=True)
        control.add_argument("--json", action="store_true", help="Print JSON output.")
```

Create `src/isotope/features/supervisor/commands/handlers/long_task.py`:

```python
"""Long-task CLI command handlers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.long_task.runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    resume_long_task,
    status_long_task,
    stop_long_task,
)


def handle_long_task_command(args: argparse.Namespace, *, api: Any) -> int:
    root = Path(args.codex_home)
    if args.long_task_command == "start":
        payload = create_long_task(root, goal=args.goal)
    elif args.long_task_command == "status":
        payload = status_long_task(root, args.task_id)
    elif args.long_task_command == "list":
        payload = list_long_tasks(root)
    elif args.long_task_command == "pause":
        payload = pause_long_task(root, args.task_id, reason=args.reason)
    elif args.long_task_command == "resume":
        payload = resume_long_task(root, args.task_id, reason=args.reason)
    elif args.long_task_command == "stop":
        payload = stop_long_task(root, args.task_id, reason=args.reason)
    else:
        raise ValueError(f"unsupported long-task command: {args.long_task_command}")
    return _print(payload, json_output=args.json, api=api)


def _print(payload: dict[str, Any], *, json_output: bool, api: Any) -> int:
    if json_output:
        api._print_json(payload)
    else:
        print_long_task_plain(payload)
    return 0


def print_long_task_plain(payload: dict[str, Any]) -> None:
    task = payload.get("task")
    if isinstance(task, dict):
        print("[Long task]")
        print(f"task: {task.get('task_id', '')}")
        print(f"status: {task.get('status', '')}")
        print(f"run: {task.get('run_id', '')}")
        print(f"goal: {task.get('goal', '')}")
        if task.get("control_reason"):
            print(f"reason: {task.get('control_reason')}")
        return
    summary = payload.get("summary")
    if isinstance(summary, dict):
        print("[Long tasks]")
        print(f"tasks: {summary.get('task_count', 0)}")
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        for item in tasks:
            if isinstance(item, dict):
                print(f"- {item.get('task_id', '')}: {item.get('status', '')} {item.get('goal', '')}")
```

Modify parser `src/isotope/features/supervisor/commands/parser/__init__.py`:

```python
from isotope.features.supervisor.commands.parser.long_task import (
    add_long_task_command_parser,
)
```

Call it near other grouped command parsers:

```python
add_agent_group_command_parser(subparsers)
add_long_task_command_parser(subparsers)
add_memory_command_parsers(subparsers)
```

Modify dispatch `src/isotope/features/supervisor/commands/dispatch.py`:

```python
from .handlers.long_task import handle_long_task_command as _handle_long_task_command
```

Add to `COMMAND_HANDLERS`:

```python
"long-task": _handle_long_task_command,
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task/test_long_task_store.py \
  tests/unit/features/supervisor/long_task/test_long_task_runtime.py \
  tests/integration/supervisor/test_supervisor_long_task_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/supervisor/commands src/isotope/features/supervisor/long_task tests/integration/supervisor/test_supervisor_long_task_cli.py
git commit -m "feat(supervisor): add long task cli controls"
```

## Task 4: Bounded Tick Runner

**Files:**
- Create: `src/isotope/features/supervisor/long_task/provider.py`
- Modify: `src/isotope/features/supervisor/long_task/runtime.py`
- Modify: `src/isotope/features/supervisor/commands/parser/long_task.py`
- Modify: `src/isotope/features/supervisor/commands/handlers/long_task.py`
- Test: `tests/unit/features/supervisor/long_task/test_long_task_runtime.py`
- Test: `tests/integration/supervisor/test_supervisor_long_task_cli.py`

- [ ] **Step 1: Write failing runtime tick tests**

Append to `tests/unit/features/supervisor/long_task/test_long_task_runtime.py`:

```python
import json
from typing import Any

from isotope.llm.provider import LLMResponse
from isotope.runtime.in_process import InProcessServer

from isotope.features.supervisor.long_task.runtime import run_long_task_ticks


class DeterministicLongTaskPlanner:
    provider = "deterministic_long_task"
    model = "stub-long-task-planner"

    def __init__(self, root):
        self.root = root
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages: list[dict[str, str]], *, max_tokens: int = 512) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        task_id = self.calls[-1].get("task_id", "ltask")
        run_id = self._run_id()
        control = InProcessServer(self.root).get_agent_loop_control(run_id)
        payload = {
            "planner_run_id": f"planner_{len(self.calls)}",
            "basis": {
                "run_id": run_id,
                "last_event_id": control["last_event_id"],
            },
            "decision": {
                "step": "record_turn_memory",
                "request": {
                    "summary": f"tick {len(self.calls)} summary",
                    "content": {
                        "kind": "long_task_tick",
                        "tick": len(self.calls),
                    },
                    "scope": "run",
                    "source_refs": [],
                    "quality": "candidate",
                },
            },
        }
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(payload),
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={"raw_response": "SHOULD_NOT_LEAK"},
        )

    def _run_id(self) -> str:
        tasks = (self.root / "long_tasks" / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
        return json.loads(tasks[-1])["run_id"]


def test_run_long_task_ticks_advances_bounded_ticks_without_raw_payload(tmp_path):
    task_id = create_long_task(tmp_path, goal="Run bounded ticks.")["task"]["task_id"]
    provider = DeterministicLongTaskPlanner(tmp_path)

    result = run_long_task_ticks(tmp_path, task_id, provider=provider, max_ticks=2)

    assert result["status"] == "ok"
    assert result["task"]["summary"]["tick_count"] == 2
    assert result["task"]["status"] in {"queued", "blocked", "completed"}
    assert len(result["ticks"]) == 2
    assert result["ticks"][0]["planner_summary"]["selected_step"] == "record_turn_memory"
    assert "raw_response" not in json.dumps(result)


def test_run_long_task_ticks_honors_pause_before_next_tick(tmp_path):
    task_id = create_long_task(tmp_path, goal="Pause before run.")["task"]["task_id"]
    pause_long_task(tmp_path, task_id, reason="Hold.")

    result = run_long_task_ticks(
        tmp_path,
        task_id,
        provider=DeterministicLongTaskPlanner(tmp_path),
        max_ticks=1,
    )

    assert result["task"]["status"] == "paused"
    assert result["ticks"] == []
    assert result["stop_reason"] == "user_paused"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task/test_long_task_runtime.py -q
```

Expected: FAIL because `run_long_task_ticks` is missing.

- [ ] **Step 3: Implement `run_long_task_ticks`**

Add to `src/isotope/features/supervisor/long_task/runtime.py`:

```python
def run_long_task_ticks(
    root: Path | str,
    task_id: str,
    *,
    provider: Any,
    max_ticks: int,
    max_tokens: int = 512,
) -> dict[str, Any]:
    if isinstance(max_ticks, bool) or not isinstance(max_ticks, int) or max_ticks <= 0:
        raise ValueError("max_ticks must be a positive integer")
    root_path = Path(root).expanduser()
    store = LongTaskStore(root_path)
    task = store.projection(task_id)
    if task.get("control_state") == "pause":
        return {
            "status": "ok",
            "task": _attach_run_status(root_path, task),
            "ticks": [],
            "stop_reason": "user_paused",
        }
    if task.get("control_state") == "stop":
        return {
            "status": "ok",
            "task": _attach_run_status(root_path, task),
            "ticks": [],
            "stop_reason": "stopped",
        }
    api = InProcessServer(root_path)
    ticks: list[dict[str, Any]] = []
    stop_reason = None
    for tick_index in range(max_ticks):
        tick = api.run_agent_loop_provider_planner_tick(
            str(task["run_id"]),
            provider=provider,
            agent_id="agent_long_task",
            tick_id=f"{task_id}_tick_{tick_index + 1}",
            decision_id=f"{task_id}_decision_{tick_index + 1}",
            tick_budget={
                "max_ticks": max_ticks,
                "ticks_used": tick_index,
                "budget_basis": f"long_task:{task_id}",
            },
            max_tokens=max_tokens,
        )
        public_tick = _public_tick_summary(task_id, tick_index, tick)
        ticks.append(public_tick)
        stop_reason = tick.get("stop_reason")
        api.save_checkpoint_for_run(str(task["run_id"]))
        if tick.get("tick_status") != "executed":
            break
    updated_state = api.get_run_state(str(task["run_id"]))
    now = _now()
    store.append_task_record(
        LongTaskRecord(
            task_id=str(task["task_id"]),
            run_id=str(task["run_id"]),
            session_id=str(task["session_id"]),
            goal=str(task["goal"]),
            status=_status_after_ticks(updated_state.status, stop_reason),
            created_at=str(task["created_at"]),
            updated_at=now,
            last_event_id=updated_state.last_event_id,
            last_checkpoint_event_id=updated_state.last_event_id,
            control_state="run",
            summary={
                "phase": "ticked",
                "tick_count": int(task.get("summary", {}).get("tick_count", 0)) + len(ticks)
                if isinstance(task.get("summary"), dict)
                else len(ticks),
                "last_selected_step": ticks[-1]["planner_summary"]["selected_step"] if ticks else None,
                "stop_reason": stop_reason,
            },
        )
    )
    return {
        "status": "ok",
        "task": _attach_run_status(root_path, store.projection(task_id)),
        "ticks": ticks,
        "stop_reason": stop_reason,
    }


def _public_tick_summary(task_id: str, tick_index: int, tick: dict[str, Any]) -> dict[str, Any]:
    provider_result = tick.get("provider_result") if isinstance(tick.get("provider_result"), dict) else {}
    planner_output = (
        provider_result.get("planner_output")
        if isinstance(provider_result.get("planner_output"), dict)
        else {}
    )
    contract = (
        tick.get("planner_contract_result")
        if isinstance(tick.get("planner_contract_result"), dict)
        else {}
    )
    planner_result = (
        contract.get("planner_result")
        if isinstance(contract.get("planner_result"), dict)
        else {}
    )
    return {
        "task_id": task_id,
        "tick_index": tick_index,
        "tick_status": tick.get("tick_status"),
        "stop_reason": tick.get("stop_reason"),
        "before_policy": tick.get("before_policy"),
        "after_policy": tick.get("after_policy"),
        "planner_summary": {
            "selected_step": planner_output.get("selected_step")
            or planner_result.get("selected_step"),
            "provider": provider_result.get("provider"),
            "model": provider_result.get("model"),
        },
        "step_summary": {
            "planner_status": planner_result.get("planner_status"),
            "selected_step": planner_result.get("selected_step"),
        },
    }


def _status_after_ticks(run_status: str, stop_reason: object) -> str:
    if run_status in TERMINAL_RUN_STATUSES:
        return "completed" if run_status == "completed" else "failed"
    if stop_reason == "awaiting_approval":
        return "blocked"
    return "queued"
```

Export `run_long_task_ticks` from `__init__.py`.

- [ ] **Step 4: Add pooled long-task planner provider resolver**

Create `src/isotope/features/supervisor/long_task/provider.py`:

```python
"""Provider resolver for long-task planner ticks."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from isotope.llm.pool import PoolEntry, resolve_pool_entries_from_env
from isotope.llm.provider import LLMResponse, Transport, create_chat_provider_from_pool_entry


class PooledLongTaskPlannerProvider:
    provider = "pooled"
    model = "pooled"

    def __init__(
        self,
        *,
        entries: tuple[PoolEntry, ...],
        timeout: int = 60,
        transport: Transport | None = None,
        codex_process_runner: Callable[..., Any] = subprocess.run,
        codex_executable_resolver: Callable[[str], str | None] = shutil.which,
    ) -> None:
        if not entries:
            raise ValueError("entries must not be empty")
        self._entries = entries
        self._timeout = timeout
        self._transport = transport
        self._codex_process_runner = codex_process_runner
        self._codex_executable_resolver = codex_executable_resolver

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        failures: list[str] = []
        for entry in self._entries:
            try:
                provider = create_chat_provider_from_pool_entry(
                    entry,
                    timeout=self._timeout,
                    transport=self._transport,
                    codex_process_runner=self._codex_process_runner,
                    codex_executable_resolver=self._codex_executable_resolver,
                )
                return provider.generate(messages, max_tokens=entry.max_tokens or max_tokens)
            except Exception as exc:
                failures.append(f"{entry.provider}:{type(exc).__name__}")
        raise ValueError("All long-task planner pool entries failed: " + ", ".join(failures))


def resolve_long_task_planner_provider_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    timeout: int | None = None,
    transport: Transport | None = None,
    codex_process_runner: Callable[..., Any] = subprocess.run,
    codex_executable_resolver: Callable[[str], str | None] = shutil.which,
) -> PooledLongTaskPlannerProvider:
    env = os.environ if environ is None else environ
    entries = resolve_pool_entries_from_env(
        env,
        env_var="SUPERVISOR_LLM_POOL_TOML_FILES",
        default_paths=(Path(__file__).resolve().parents[1] / "supervisor_llm_pool.toml",),
    )
    if not entries:
        raise ValueError(
            "No long-task planner LLM pool entries found. "
            "Check SUPERVISOR_LLM_POOL_TOML_FILES or supervisor_llm_pool.toml."
        )
    return PooledLongTaskPlannerProvider(
        entries=entries,
        timeout=timeout or 60,
        transport=transport,
        codex_process_runner=codex_process_runner,
        codex_executable_resolver=codex_executable_resolver,
    )
```

- [ ] **Step 5: Add CLI `run` parser and handler**

Modify `src/isotope/features/supervisor/commands/parser/long_task.py`:

```python
run = task_subparsers.add_parser("run", help="Advance a long task by bounded ticks.")
add_state_root_arg(run)
run.add_argument("--task-id", required=True)
run.add_argument("--max-ticks", type=int, default=1)
run.add_argument("--max-tokens", type=int, default=512)
run.add_argument("--json", action="store_true", help="Print JSON output.")
```

Modify `src/isotope/features/supervisor/commands/handlers/long_task.py`:

```python
from isotope.features.supervisor.long_task.provider import (
    resolve_long_task_planner_provider_from_env,
)
from isotope.features.supervisor.long_task.runtime import run_long_task_ticks
```

Add branch:

```python
elif args.long_task_command == "run":
    payload = run_long_task_ticks(
        root,
        args.task_id,
        provider=resolve_long_task_planner_provider_from_env(),
        max_ticks=args.max_ticks,
        max_tokens=args.max_tokens,
    )
```

Tests monkeypatch `isotope.features.supervisor.commands.handlers.long_task.resolve_long_task_planner_provider_from_env`.

- [ ] **Step 6: Write CLI run integration test**

Append to `tests/integration/supervisor/test_supervisor_long_task_cli.py`:

```python
from isotope.llm.provider import LLMResponse
from isotope.runtime.in_process import InProcessServer


class CliDeterministicPlanner:
    provider = "cli_deterministic_long_task"
    model = "stub-cli-long-task"

    def __init__(self, root):
        self.root = root
        self.calls = 0

    def generate(self, messages, *, max_tokens=512):
        self.calls += 1
        task_line = (self.root / "long_tasks" / "tasks.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        run_id = json.loads(task_line)["run_id"]
        control = InProcessServer(self.root).get_agent_loop_control(run_id)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(
                {
                    "planner_run_id": f"planner_cli_{self.calls}",
                    "basis": {
                        "run_id": run_id,
                        "last_event_id": control["last_event_id"],
                    },
                    "decision": {
                        "step": "record_turn_memory",
                        "request": {
                            "summary": "cli tick",
                            "content": {"kind": "long_task_cli_tick"},
                            "scope": "run",
                            "source_refs": [],
                            "quality": "candidate",
                        },
                    },
                }
            ),
            finish_reason="stop",
            usage={},
            raw={"raw_response": "SHOULD_NOT_LEAK"},
        )


def test_supervisor_long_task_run_cli_uses_bounded_ticks(tmp_path, capsys, monkeypatch):
    planner = CliDeterministicPlanner(tmp_path)
    monkeypatch.setattr(
        "isotope.features.supervisor.commands.handlers.long_task.resolve_long_task_planner_provider_from_env",
        lambda: planner,
    )
    runner.main(
        [
            "long-task",
            "start",
            "--state-root",
            str(tmp_path),
            "--goal",
            "Run through CLI.",
            "--json",
        ]
    )
    task_id = json.loads(capsys.readouterr().out)["task"]["task_id"]

    assert runner.main(
        [
            "long-task",
            "run",
            "--state-root",
            str(tmp_path),
            "--task-id",
            task_id,
            "--max-ticks",
            "1",
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["task"]["summary"]["tick_count"] == 1
    assert payload["ticks"][0]["planner_summary"]["selected_step"] == "record_turn_memory"
    assert "raw_response" not in json.dumps(payload)
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task/test_long_task_runtime.py \
  tests/integration/supervisor/test_supervisor_long_task_cli.py \
  tests/unit/agents/loop/test_agent_loop_provider_planner.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/isotope/features/supervisor/long_task src/isotope/features/supervisor/commands tests/unit/features/supervisor/long_task tests/integration/supervisor/test_supervisor_long_task_cli.py
git commit -m "feat(supervisor): run bounded long task ticks"
```

## Task 5: Desktop Thin Adapter

**Files:**
- Create: `src/isotope/features/supervisor/web/routes/long_tasks.py`
- Create: `src/isotope/features/supervisor/web/routes/long_tasks_dispatch.py`
- Modify: `src/isotope/features/supervisor/web/_impl.py`
- Modify: `src/isotope/features/supervisor/desktop_snapshot.py`
- Test: `tests/unit/features/supervisor/web/test_long_task_routes.py`
- Test: `tests/unit/features/supervisor/test_supervisor_web_route_split.py`
- Test: `tests/integration/supervisor/desktop/test_supervisor_desktop_snapshot.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/unit/features/supervisor/web/test_long_task_routes.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.supervisor.long_task.runtime import create_long_task
from isotope.features.supervisor.web.routes.long_tasks import (
    desktop_long_task_control_id_from_path,
    desktop_long_task_id_from_path,
    parse_long_task_control_payload,
    parse_long_task_create_payload,
)
from isotope.features.supervisor.desktop_snapshot import build_desktop_snapshot


def test_long_task_route_helpers_parse_paths_and_payloads():
    assert desktop_long_task_id_from_path("/desktop/long-tasks/ltask%201") == "ltask 1"
    assert desktop_long_task_id_from_path("/desktop/long-tasks/bad%2Fid") is None
    assert (
        desktop_long_task_control_id_from_path("/desktop/long-tasks/ltask%201/control")
        == "ltask 1"
    )
    assert parse_long_task_create_payload({"goal": "  Run long task  "}) == {
        "goal": "Run long task"
    }
    assert parse_long_task_control_payload(
        {"control": "pause", "reason": "Need review."}
    ) == {
        "control": "pause",
        "reason": "Need review.",
    }
    with pytest.raises(ValueError, match="control must be pause, resume, or stop"):
        parse_long_task_control_payload({"control": "delete", "reason": "bad"})


def test_desktop_snapshot_includes_long_task_projection(tmp_path):
    task = create_long_task(tmp_path, goal="Visible in desktop.")["task"]

    snapshot = build_desktop_snapshot(state_root=tmp_path)

    assert snapshot["longTasks"]["summary"]["task_count"] == 1
    assert snapshot["longTasks"]["tasks"][0]["task_id"] == task["task_id"]
```

Append to `tests/integration/supervisor/desktop/test_supervisor_desktop_snapshot.py`:

```python
def test_desktop_long_task_endpoints_create_status_and_control(tmp_path):
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/desktop/long-tasks",
            body=json.dumps({"goal": "Run desktop long task."}),
            headers={"content-type": "application/json"},
        )
        create_response = conn.getresponse()
        create_payload = json.loads(create_response.read().decode("utf-8"))
        task_id = create_payload["task"]["task_id"]

        conn.request("GET", f"/desktop/long-tasks/{task_id}")
        status_response = conn.getresponse()
        status_payload = json.loads(status_response.read().decode("utf-8"))

        conn.request(
            "POST",
            f"/desktop/long-tasks/{task_id}/control",
            body=json.dumps({"control": "pause", "reason": "Need operator review."}),
            headers={"content-type": "application/json"},
        )
        control_response = conn.getresponse()
        control_payload = json.loads(control_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert create_response.status == 200
    assert status_response.status == 200
    assert control_response.status == 200
    assert create_payload["status"] == "ok"
    assert status_payload["task"]["task_id"] == task_id
    assert control_payload["task"]["status"] == "paused"
    assert control_payload["task"]["control_reason"] == "Need operator review."
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/web/test_long_task_routes.py \
  tests/integration/supervisor/desktop/test_supervisor_desktop_snapshot.py::test_desktop_long_task_endpoints_create_status_and_control -q
```

Expected: FAIL because route helpers do not exist.

- [ ] **Step 3: Implement route helpers and snapshot projection**

Create `src/isotope/features/supervisor/web/routes/long_tasks.py`:

```python
"""Desktop long-task route helpers."""

from __future__ import annotations

from urllib.parse import unquote


LONG_TASK_PREFIX = "/desktop/long-tasks/"


def desktop_long_task_id_from_path(path: str) -> str | None:
    if not path.startswith(LONG_TASK_PREFIX):
        return None
    task_id = unquote(path[len(LONG_TASK_PREFIX) :])
    if "/" in task_id or not task_id:
        return None
    return task_id


def desktop_long_task_control_id_from_path(path: str) -> str | None:
    suffix = "/control"
    if not path.startswith(LONG_TASK_PREFIX) or not path.endswith(suffix):
        return None
    task_id = unquote(path[len(LONG_TASK_PREFIX) : -len(suffix)])
    if "/" in task_id or not task_id:
        return None
    return task_id


def parse_long_task_create_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    goal = _required_string(value.get("goal"), "goal")
    return {"goal": goal}


def parse_long_task_control_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    control = _required_string(value.get("control"), "control")
    reason = _required_string(value.get("reason"), "reason")
    if control not in {"pause", "resume", "stop"}:
        raise ValueError("control must be pause, resume, or stop")
    return {"control": control, "reason": reason}


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
```

Create `src/isotope/features/supervisor/web/routes/long_tasks_dispatch.py`:

```python
"""Thin HTTP dispatch helpers for desktop long-task endpoints."""

from __future__ import annotations

from typing import Any

from isotope.features.supervisor.long_task.runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    resume_long_task,
    status_long_task,
    stop_long_task,
)

from . import long_tasks as routes


def handle_long_task_get(handler: Any, *, path: str) -> bool:
    if path == "/desktop/long-tasks":
        handler._send_json(list_long_tasks(handler.server.codex_home))
        return True
    task_id = routes.desktop_long_task_id_from_path(path)
    if task_id is not None:
        try:
            handler._send_json(status_long_task(handler.server.codex_home, task_id))
        except ValueError as exc:
            _send_error(handler, str(exc), status_code=404)
        return True
    return False


def handle_long_task_post(handler: Any, *, path: str) -> bool:
    if path == "/desktop/long-tasks":
        try:
            payload = routes.parse_long_task_create_payload(handler._read_json_body())
            handler._send_json(create_long_task(handler.server.codex_home, goal=payload["goal"]))
        except ValueError as exc:
            _send_error(handler, str(exc), status_code=400)
        return True
    task_id = routes.desktop_long_task_control_id_from_path(path)
    if task_id is not None:
        try:
            payload = routes.parse_long_task_control_payload(handler._read_json_body())
            if payload["control"] == "pause":
                result = pause_long_task(handler.server.codex_home, task_id, reason=payload["reason"])
            elif payload["control"] == "resume":
                result = resume_long_task(handler.server.codex_home, task_id, reason=payload["reason"])
            else:
                result = stop_long_task(handler.server.codex_home, task_id, reason=payload["reason"])
            handler._send_json(result)
        except ValueError as exc:
            _send_error(handler, str(exc), status_code=400)
        return True
    return False


def _send_error(handler: Any, message: str, *, status_code: int) -> None:
    handler._send_json(
        {
            "status": "error",
            "error": {
                "code": "codex_supervisor_web_error",
                "message": message,
            },
        },
        status_code=status_code,
    )
```

Modify `src/isotope/features/supervisor/desktop_snapshot.py`:

```python
from isotope.features.supervisor.long_task.runtime import list_long_tasks
```

Add inside `snapshot` before return:

```python
snapshot["longTasks"] = list_long_tasks(root)
```

Modify `src/isotope/features/supervisor/web/_impl.py`:

```python
from .routes.long_tasks_dispatch import handle_long_task_get, handle_long_task_post
```

Add to `do_GET` before agent-group specific routes:

```python
if handle_long_task_get(self, path=path):
    return
```

Add to `do_POST` after desktop chat:

```python
if handle_long_task_post(self, path=path):
    return
```

- [ ] **Step 4: Run route tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/web/test_long_task_routes.py \
  tests/unit/features/supervisor/test_supervisor_web_route_split.py \
  tests/integration/supervisor/desktop/test_supervisor_desktop_snapshot.py::test_desktop_long_task_endpoints_create_status_and_control -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/supervisor/web src/isotope/features/supervisor/desktop_snapshot.py tests/unit/features/supervisor/web/test_long_task_routes.py tests/integration/supervisor/desktop/test_supervisor_desktop_snapshot.py
git commit -m "feat(supervisor): expose long tasks to desktop"
```

## Task 6: Verification, Dev-Eval Gate, And Push

**Files:**
- Modify only if needed: `docs/current/refactoring-debt.md`

- [ ] **Step 1: Run targeted long-task suite**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task \
  tests/integration/supervisor/test_supervisor_long_task_cli.py \
  tests/unit/features/supervisor/web/test_long_task_routes.py \
  tests/unit/agents/loop/test_agent_loop_provider_planner.py \
  tests/integration/agent/test_agent_loop_planner_restart_pause_spike.py -q
```

Expected: PASS.

- [ ] **Step 2: Run repository diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Run changed-surface dev-eval gate**

Run:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

Expected: JSON result. If `eval_required` is `false`, record that in final. If `eval_required` is `true`, run the returned `recommended_smoke.full_command`.

- [ ] **Step 4: Inspect generated reviewer prompts when eval is required**

When `eval_required=true`, run:

```bash
find .dev-eval-runs -path '*/state/dev-evals/reviewer-prompts/*.md' -type f -print
```

Open each generated reviewer prompt listed by the command and report hard gates, scores, findings, and follow-up changes.

- [ ] **Step 5: Record refactoring debt only if implementation touches large-file debt**

If the implementation adds substantial new logic to an existing file already over 500 lines, add one focused entry to `docs/current/refactoring-debt.md` explaining the file, reason, and next split. If all new logic stays in focused new modules and existing large files only receive imports/dispatch lines, skip this edit.

- [ ] **Step 6: Final commit if verification changes docs or fixes**

If Step 5 or eval follow-up changes files, commit them:

```bash
git add docs/current/refactoring-debt.md src tests
git commit -m "chore(supervisor): finish long task verification"
```

- [ ] **Step 7: Push review branch**

Run:

```bash
git push -u origin feature/supervisor-long-task
```

Expected: branch pushed.

- [ ] **Step 8: Final status report**

Run:

```bash
git status --short --branch
git log --oneline --max-count=6
```

Report:

- branch name and pushed remote;
- changed entry points;
- test commands and outcomes;
- dev-eval result and required smoke outcome;
- whether any refactoring debt was recorded.
