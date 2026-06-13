"""Supervisor long-task backend contract."""

from __future__ import annotations

from .contracts import LongTaskControlRecord, LongTaskRecord
from .runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    resume_long_task,
    run_long_task_ticks,
    status_long_task,
    stop_long_task,
)
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
    "create_long_task",
    "list_long_tasks",
    "long_task_projection",
    "pause_long_task",
    "resume_long_task",
    "run_long_task_ticks",
    "status_long_task",
    "stop_long_task",
]
