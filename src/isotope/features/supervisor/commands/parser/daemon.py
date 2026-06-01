"""Daemon parser registration for the Supervisor CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.commands.parser.common import (
    add_failure_retry_args,
    add_goal_replenishment_args,
    add_state_root_arg,
    add_webhook_args,
)


def add_daemon_command_parser(
    subparsers: argparse._SubParsersAction,
    *,
    api: Any,
) -> None:
    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Start, inspect, or stop the background Supervisor loop.",
    )
    daemon_subparsers = daemon_parser.add_subparsers(
        dest="daemon_command",
        required=True,
    )
    daemon_start_parser = daemon_subparsers.add_parser(
        "start",
        help="Start the Supervisor loop in the background.",
    )
    add_state_root_arg(daemon_start_parser)
    daemon_start_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum sessions.",
    )
    daemon_start_parser.add_argument(
        "--stale-after",
        type=int,
        default=600,
        help="Seconds without events before marking a session stale.",
    )
    daemon_start_parser.add_argument(
        "--active-within",
        type=int,
        default=180,
        help="Seconds with recent events before marking a session working.",
    )
    daemon_start_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between loop reports.",
    )
    daemon_start_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=api.DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating send_status/send_continue for the same lane.",
    )
    daemon_start_parser.add_argument(
        "--max-continue-count",
        type=int,
        default=api.DEFAULT_MAX_CONTINUE_COUNT,
        help="Maximum consecutive send_continue prompts for the same lane status. Default 0 disables.",
    )
    daemon_start_parser.add_argument(
        "--max-context-requests",
        type=int,
        default=api.DEFAULT_MAX_CONTEXT_REQUESTS,
        help="Maximum request_context executions per loop iteration. Default 0 disables.",
    )
    daemon_start_parser.add_argument(
        "--decision-timeout",
        type=int,
        default=api.DEFAULT_DECISION_TIMEOUT_SECONDS,
        help="Seconds before an active decision request raises a timeout alert.",
    )
    add_failure_retry_args(daemon_start_parser, api=api)
    daemon_start_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=api.DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
    )
    daemon_start_parser.add_argument(
        "--max-fanout-launches",
        type=int,
        default=api.DEFAULT_FANOUT_LIMIT,
        help="Maximum launch_session actions fanout may execute in one loop iteration.",
    )
    add_goal_replenishment_args(daemon_start_parser, api=api)
    daemon_start_parser.add_argument(
        "--worker-profile",
        choices=api.WORKER_PROFILE_CHOICES,
        default=api.DEFAULT_WORKER_PROFILE,
        help="Worker profile for Codex workers launched by the daemon loop.",
    )
    daemon_start_parser.add_argument(
        "--worker-codex-model",
        help="Pass -m/--model to Codex workers launched by the daemon loop.",
    )
    daemon_start_parser.add_argument(
        "--worker-codex-config",
        action="append",
        default=None,
        help="Pass one -c key=value override to Codex workers. Repeatable.",
    )
    daemon_start_parser.add_argument(
        "--name",
        help="Target one managed lane. Omit to rotate across active lanes.",
    )
    daemon_start_parser.add_argument(
        "--goal",
        help="User goal for the LLM planner when it may need to launch a new worker.",
    )
    daemon_start_parser.add_argument(
        "--llm-summary",
        action="store_true",
        help="Use configured LLM to add a compact Chinese summary.",
    )
    add_webhook_args(daemon_start_parser)
    daemon_start_parser.add_argument(
        "--no-auto-adopt",
        action="store_false",
        dest="auto_adopt",
        help="Disable automatic adoption of discovered Codex-like tmux sessions.",
    )
    daemon_start_parser.add_argument(
        "--merge-dispatch-execute",
        action="store_true",
        help="Let the daemon loop launch merge-dispatch workers.",
    )
    daemon_start_parser.add_argument(
        "--auto-merge-promote",
        action="store_true",
        help="Let the daemon loop promote or repair merge-dispatch workers.",
    )
    daemon_start_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    daemon_start_parser.set_defaults(auto_adopt=True)
    for daemon_command in ("status", "stop", "watchdog"):
        daemon_command_parser = daemon_subparsers.add_parser(
            daemon_command,
            help=f"{daemon_command.title()} the background Supervisor loop.",
        )
        add_state_root_arg(daemon_command_parser)
        daemon_command_parser.add_argument(
            "--json",
            action="store_true",
            help="Print JSON output.",
        )
    watcher_parser = daemon_subparsers.add_parser(
        "watcher",
        help="Manage the background periodic watchdog.",
    )
    watcher_subparsers = watcher_parser.add_subparsers(
        dest="watcher_command",
        required=True,
    )
    watcher_start_parser = watcher_subparsers.add_parser(
        "start",
        help="Start the periodic watchdog in the background.",
    )
    add_state_root_arg(watcher_start_parser)
    watcher_start_parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between watchdog checks.",
    )
    watcher_start_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    watcher_run_parser = watcher_subparsers.add_parser(
        "run",
        help="Run watchdog checks in the foreground.",
    )
    add_state_root_arg(watcher_run_parser)
    watcher_run_parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between watchdog checks.",
    )
    watcher_run_parser.add_argument(
        "--iterations",
        type=int,
        help="Stop after this many checks. Omit to run until interrupted.",
    )
    watcher_run_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    for watcher_command in ("status", "stop"):
        watcher_command_parser = watcher_subparsers.add_parser(
            watcher_command,
            help=f"{watcher_command.title()} the periodic watchdog.",
        )
        add_state_root_arg(watcher_command_parser)
        watcher_command_parser.add_argument(
            "--json",
            action="store_true",
            help="Print JSON output.",
        )
