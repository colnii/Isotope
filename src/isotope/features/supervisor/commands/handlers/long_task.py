"""Long-task command handlers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.long_task.provider import (
    resolve_long_task_planner_provider_from_env,
)
from isotope.features.supervisor.long_task.runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    resume_long_task,
    run_long_task_ticks,
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
    elif args.long_task_command == "run":
        payload = run_long_task_ticks(
            root,
            args.task_id,
            provider=resolve_long_task_planner_provider_from_env(),
            max_ticks=args.max_ticks,
            max_tokens=args.max_tokens,
        )
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
    task = payload.get("task") if isinstance(payload.get("task"), dict) else None
    if task is not None:
        print("[Supervisor long task]")
        print(f"task: {task.get('task_id', '')}")
        print(f"status: {task.get('status', '')}")
        print(f"run: {task.get('run_id', '')} / {task.get('run_status', '')}")
        print(f"goal: {task.get('goal', '')}")
        if task.get("control_reason"):
            print(f"reason: {task.get('control_reason')}")
        return

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    print("[Supervisor long tasks]")
    print(f"tasks: {summary.get('task_count', 0)}")
    print(f"requires_human: {summary.get('requires_human_count', 0)}")
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        for item in tasks:
            if isinstance(item, dict):
                print(
                    "- {task_id}: {status} / {goal}".format(
                        task_id=item.get("task_id", ""),
                        status=item.get("status", ""),
                        goal=item.get("goal", ""),
                    )
                )
