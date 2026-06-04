"""Shared parser argument groups for the Supervisor CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def add_state_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--state-root",
        dest="codex_home",
        default=str(Path.home() / ".codex"),
        help="Supervisor state root directory. Defaults to ~/.codex.",
    )
    parser.add_argument(
        "--codex-home",
        dest="codex_home",
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )


def add_goal_replenishment_args(
    parser: argparse.ArgumentParser,
    *,
    api: Any,
) -> None:
    parser.add_argument(
        "--goal-low-water",
        type=int,
        default=0,
        help=(
            "When active goals fall below this count, ask LLM to plan more goals "
            "from current docs. Default 0 disables."
        ),
    )
    parser.add_argument(
        "--goal-replenish-limit",
        type=int,
        default=api.DEFAULT_FANOUT_LIMIT,
        help="Maximum goals the LLM low-water planner may write in one loop.",
    )
    parser.add_argument(
        "--goal-replenish-prompt",
        help="Optional seed prompt for low-water goal planning.",
    )


def add_failure_retry_args(
    parser: argparse.ArgumentParser,
    *,
    api: Any,
) -> None:
    parser.add_argument(
        "--max-failure-retries",
        type=int,
        default=api.DEFAULT_MAX_FAILURE_RETRIES,
        help=(
            "Maximum repeated Supervisor failures before creating a decision "
            "request. Default 3."
        ),
    )


def add_webhook_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--webhook-url",
        help="HTTP endpoint for public Supervisor event POSTs.",
    )
    parser.add_argument(
        "--webhook-secret",
        help="Optional shared secret for X-Isotope-Signature HMAC headers.",
    )
