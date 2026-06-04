"""Loop and up parser registration for the Supervisor CLI."""

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


def add_loop_command_parsers(
    subparsers: argparse._SubParsersAction,
    *,
    api: Any,
) -> None:
    loop_parser = subparsers.add_parser(
        "loop",
        help="Run the daily managed Supervisor loop with safe defaults.",
    )
    add_state_root_arg(loop_parser)
    loop_parser.add_argument("--limit", type=int, default=10, help="Maximum sessions.")
    loop_parser.add_argument(
        "--stale-after",
        type=int,
        default=600,
        help="Seconds without events before marking a session stale.",
    )
    loop_parser.add_argument(
        "--active-within",
        type=int,
        default=180,
        help="Seconds with recent events before marking a session working.",
    )
    loop_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    loop_parser.add_argument(
        "--llm-summary",
        action="store_true",
        help="Use configured LLM to add a compact Chinese summary.",
    )
    loop_parser.add_argument(
        "--workspace-root",
        help="Limit LLM/action candidates to this workspace. Defaults to cwd.",
    )
    loop_parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Let LLM/action candidates span every discovered workspace.",
    )
    add_webhook_args(loop_parser)
    loop_parser.add_argument(
        "--name",
        help="Target one managed lane by name. Omit to rotate across active lanes.",
    )
    loop_parser.add_argument(
        "--goal",
        help="User goal for the LLM planner when it may need to launch a new worker.",
    )
    loop_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=api.DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating send_status/send_continue for the same lane.",
    )
    loop_parser.add_argument(
        "--max-continue-count",
        type=int,
        default=api.DEFAULT_MAX_CONTINUE_COUNT,
        help="Maximum consecutive send_continue prompts for the same lane status. Default 0 disables.",
    )
    loop_parser.add_argument(
        "--max-context-requests",
        type=int,
        default=api.DEFAULT_MAX_CONTEXT_REQUESTS,
        help="Maximum request_context executions per loop iteration. Default 0 disables.",
    )
    loop_parser.add_argument(
        "--decision-timeout",
        type=int,
        default=api.DEFAULT_DECISION_TIMEOUT_SECONDS,
        help="Seconds before an active decision request raises a timeout alert.",
    )
    add_failure_retry_args(loop_parser, api=api)
    loop_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=api.DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
    )
    loop_parser.add_argument(
        "--max-fanout-launches",
        type=int,
        default=api.DEFAULT_FANOUT_LIMIT,
        help="Maximum launch_session actions fanout may execute in one loop iteration.",
    )
    loop_parser.add_argument(
        "--max-worker-retry-count",
        type=int,
        default=api.DEFAULT_MAX_WORKER_RETRY_COUNT,
        help="Maximum automatic restarts for an exited process worker. Default 2.",
    )
    add_goal_replenishment_args(loop_parser, api=api)
    loop_parser.add_argument(
        "--worker-profile",
        choices=api.WORKER_PROFILE_CHOICES,
        default=api.DEFAULT_WORKER_PROFILE,
        help="Worker profile for Codex workers launched by the loop.",
    )
    loop_parser.add_argument(
        "--worker-codex-model",
        help="Pass -m/--model to Codex workers launched by the loop.",
    )
    loop_parser.add_argument(
        "--worker-codex-config",
        action="append",
        default=None,
        help="Pass one -c key=value override to Codex workers. Repeatable.",
    )
    loop_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between reports.",
    )
    loop_parser.add_argument(
        "--iterations",
        type=int,
        help="Stop after this many reports. Omit to loop until interrupted.",
    )
    loop_parser.add_argument(
        "--no-auto-adopt",
        action="store_false",
        dest="auto_adopt",
        help="Disable automatic adoption of discovered Codex-like tmux sessions.",
    )
    loop_parser.add_argument(
        "--rule-execute",
        action="store_true",
        help="Use the old rule-based executor instead of the LLM planner.",
    )
    loop_parser.add_argument(
        "--capacity-decisions",
        action="store_true",
        help=(
            "Plan one capacity decision for the current goal each iteration and "
            "pass it to the LLM planner."
        ),
    )
    loop_parser.add_argument(
        "--merge-dispatch-execute",
        action="store_true",
        help=(
            "Actually launch merge-dispatch workers from ready_to_integrate. "
            "Default loop only reports the launch action."
        ),
    )
    loop_parser.add_argument(
        "--lifecycle-cleanup-execute",
        action="store_true",
        help=(
            "Execute program-owned archive/delete cleanup lifecycle plans. "
            "Default loop only reports cleanup plans."
        ),
    )
    loop_parser.add_argument(
        "--auto-merge-promote",
        action="store_true",
        help=(
            "After merge-dispatch workers finish or block, automatically continue "
            "the merge promotion or repair flow."
        ),
    )
    loop_parser.set_defaults(
        auto_execute=False,
        auto_adopt=True,
        changes_only=True,
        bell=True,
        execute=None,
        llm_action=False,
        llm_execute=True,
    )

    up_parser = subparsers.add_parser(
        "up",
        help="Start the daily Supervisor daemon if needed, then print status.",
    )
    add_state_root_arg(up_parser)
    up_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum sessions.",
    )
    up_parser.add_argument(
        "--stale-after",
        type=int,
        default=600,
        help="Seconds without events before marking a session stale.",
    )
    up_parser.add_argument(
        "--active-within",
        type=int,
        default=180,
        help="Seconds with recent events before marking a session working.",
    )
    up_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between loop reports.",
    )
    up_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=api.DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating send_status/send_continue for the same lane.",
    )
    up_parser.add_argument(
        "--max-continue-count",
        type=int,
        default=api.DEFAULT_MAX_CONTINUE_COUNT,
        help="Maximum consecutive send_continue prompts for the same lane status. Default 0 disables.",
    )
    up_parser.add_argument(
        "--max-context-requests",
        type=int,
        default=api.DEFAULT_MAX_CONTEXT_REQUESTS,
        help="Maximum request_context executions per loop iteration. Default 0 disables.",
    )
    up_parser.add_argument(
        "--decision-timeout",
        type=int,
        default=api.DEFAULT_DECISION_TIMEOUT_SECONDS,
        help="Seconds before an active decision request raises a timeout alert.",
    )
    add_failure_retry_args(up_parser, api=api)
    up_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=api.DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
    )
    up_parser.add_argument(
        "--max-fanout-launches",
        type=int,
        default=api.DEFAULT_FANOUT_LIMIT,
        help="Maximum launch_session actions fanout may execute in one loop iteration.",
    )
    add_goal_replenishment_args(up_parser, api=api)
    up_parser.add_argument(
        "--worker-profile",
        choices=api.WORKER_PROFILE_CHOICES,
        default=api.DEFAULT_WORKER_PROFILE,
        help="Worker profile for Codex workers launched by the daemon loop.",
    )
    up_parser.add_argument(
        "--worker-codex-model",
        help="Pass -m/--model to Codex workers launched by the daemon loop.",
    )
    up_parser.add_argument(
        "--worker-codex-config",
        action="append",
        default=None,
        help="Pass one -c key=value override to Codex workers. Repeatable.",
    )
    up_parser.add_argument(
        "--name",
        help="Target one managed lane. Omit to rotate across active lanes.",
    )
    up_parser.add_argument(
        "--goal",
        help="User goal for the LLM planner when it may need to launch a new worker.",
    )
    up_parser.add_argument(
        "--llm-summary",
        action="store_true",
        help="Use configured LLM to add a compact Chinese summary.",
    )
    add_webhook_args(up_parser)
    up_parser.add_argument(
        "--no-auto-adopt",
        action="store_false",
        dest="auto_adopt",
        help="Disable automatic adoption of discovered Codex-like tmux sessions.",
    )
    up_parser.add_argument(
        "--merge-dispatch-execute",
        action="store_true",
        help="Let the daemon loop launch merge-dispatch workers.",
    )
    up_parser.add_argument(
        "--auto-merge-promote",
        action="store_true",
        help="Let the daemon loop promote or repair merge-dispatch workers.",
    )
    up_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    up_parser.set_defaults(auto_adopt=True)
