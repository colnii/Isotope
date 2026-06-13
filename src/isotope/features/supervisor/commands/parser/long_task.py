"""Argument parser registration for Supervisor long-task commands."""

from __future__ import annotations

import argparse

from .common import add_state_root_arg


def add_long_task_command_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "long-task",
        help="Start, inspect, and control durable Supervisor long tasks.",
    )
    task_subparsers = parser.add_subparsers(
        dest="long_task_command",
        required=True,
    )

    start = task_subparsers.add_parser("start", help="Start one long task.")
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

    run = task_subparsers.add_parser(
        "run",
        help="Advance a long task by bounded ticks.",
    )
    add_state_root_arg(run)
    run.add_argument("--task-id", required=True)
    run.add_argument("--max-ticks", type=int, default=1)
    run.add_argument("--max-tokens", type=int, default=512)
    run.add_argument("--json", action="store_true", help="Print JSON output.")

    for command in ("pause", "resume", "stop"):
        control = task_subparsers.add_parser(command, help=f"{command.title()} one long task.")
        add_state_root_arg(control)
        control.add_argument("--task-id", required=True)
        control.add_argument("--reason", required=True)
        control.add_argument("--json", action="store_true", help="Print JSON output.")
