"""QQ command registration and dispatch for the social CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from typing import Any


QQHandler = Callable[[argparse.Namespace], dict[str, Any]]


def register_qq_commands(subparsers: argparse._SubParsersAction) -> None:
    qq_parser = subparsers.add_parser("qq", help="QQ group bot operations.")
    qq_subparsers = qq_parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("dry-run", "Process one QQ event without sending."),
        ("run", "Process one QQ event; sends only with --send."),
    ):
        command = qq_subparsers.add_parser(name, help=help_text)
        _add_config_state_args(command)
        command.add_argument("--event-json", required=True, help="OneBot event JSON file.")
        command.add_argument("--send", action="store_true", help="Allow sending for qq run.")
        command.add_argument("--json", action="store_true", help="Print JSON output.")

    live_run = qq_subparsers.add_parser(
        "live-run",
        help="Connect to a OneBot WebSocket endpoint and process QQ events.",
    )
    _add_config_state_args(live_run)
    live_run.add_argument("--websocket-url", required=True, help="NapCat OneBot WebSocket URL.")
    live_run.add_argument("--access-token", help="Optional OneBot access token.")
    live_run.add_argument(
        "--max-events",
        type=int,
        default=1,
        help="Stop after this many received events; 0 means health-only.",
    )
    live_run.add_argument(
        "--receive-timeout-seconds",
        type=float,
        default=30.0,
        help="Stop cleanly when no event arrives within this many seconds.",
    )
    live_run.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=5.0,
        help="Timeout for OneBot API responses.",
    )
    live_run.add_argument("--send", action="store_true", help="Allow real sends.")
    live_run.add_argument("--json", action="store_true", help="Print JSON output.")

    init_beta = qq_subparsers.add_parser(
        "init-beta",
        help="Create a controlled QQ beta config and script pack.",
    )
    init_beta.add_argument("--output-dir", required=True, help="Directory to create.")
    init_beta.add_argument("--group", required=True, help="Controlled QQ group id.")
    init_beta.add_argument("--operator", required=True, help="Operator QQ user id.")
    init_beta.add_argument("--bot-user-id", required=True, help="Bot QQ user id.")
    init_beta.add_argument("--websocket-url", required=True, help="NapCat OneBot WebSocket URL.")
    init_beta.add_argument(
        "--max-events",
        type=int,
        default=10,
        help="Default event count for dry-run and send scripts.",
    )
    init_beta.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files in an existing beta pack directory.",
    )
    init_beta.add_argument("--json", action="store_true", help="Print JSON output.")

    init_profile = qq_subparsers.add_parser(
        "init-profile",
        help="Create editable QQ role-card and sticker-library files.",
    )
    init_profile.add_argument("--output-dir", required=True, help="Profile directory to create.")
    init_profile.add_argument("--group", required=True, help="Controlled QQ group id.")
    init_profile.add_argument("--name", required=True, help="Role name for the character card.")
    init_profile.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files in an existing profile directory.",
    )
    init_profile.add_argument("--json", action="store_true", help="Print JSON output.")

    apply_profile = qq_subparsers.add_parser(
        "apply-profile",
        help="Apply editable QQ role-card and sticker-library files to a beta pack.",
    )
    apply_profile.add_argument("--pack-dir", required=True, help="Generated beta pack directory.")
    apply_profile.add_argument("--profile-dir", required=True, help="Profile pack directory.")
    apply_profile.add_argument("--json", action="store_true", help="Print JSON output.")

    init_replay = qq_subparsers.add_parser(
        "init-replay",
        help="Create an editable QQ replay event file.",
    )
    init_replay.add_argument("--output", required=True, help="Replay JSON file to write.")
    init_replay.add_argument("--group", required=True, help="Controlled QQ group id.")
    init_replay.add_argument("--bot-user-id", required=True, help="Bot QQ user id.")
    init_replay.add_argument("--json", action="store_true", help="Print JSON output.")

    replay = qq_subparsers.add_parser(
        "replay",
        help="Replay captured QQ events through the configured social runtime.",
    )
    _add_config_state_args(replay)
    replay.add_argument("--replay-json", required=True, help="Replay JSON file.")
    replay.add_argument("--output", required=True, help="Replay report JSON file.")
    replay.add_argument("--json", action="store_true", help="Print JSON output.")

    beta_check = qq_subparsers.add_parser(
        "beta-check",
        help="Verify a generated QQ beta pack before operator use.",
    )
    beta_check.add_argument("--pack-dir", required=True, help="Generated beta pack directory.")
    beta_check.add_argument("--json", action="store_true", help="Print JSON output.")

    startup_check = qq_subparsers.add_parser(
        "startup-check",
        help="Verify QQ beta startup readiness before generated live scripts run.",
    )
    startup_check.add_argument("--pack-dir", required=True, help="Generated beta pack directory.")
    startup_check.add_argument("--replay-report", required=True, help="Replay report JSON file.")
    startup_check.add_argument(
        "--min-sticker-candidates",
        type=int,
        default=1,
        help="Minimum replay sticker candidates required for startup readiness.",
    )
    startup_check.add_argument("--json", action="store_true", help="Print JSON output.")

    review_dry_run = qq_subparsers.add_parser(
        "review-dry-run",
        help="Write an operator review report from recorded QQ dry-run decisions.",
    )
    review_dry_run.add_argument("--state-root", required=True, help="State root directory.")
    review_dry_run.add_argument("--group", required=True, help="QQ group id.")
    review_dry_run.add_argument("--output", required=True, help="Review report JSON file.")
    review_dry_run.add_argument("--json", action="store_true", help="Print JSON output.")

    beta_day_report = qq_subparsers.add_parser(
        "beta-day-report",
        help="Write a QQ beta day report from review, audit log, and failure records.",
    )
    beta_day_report.add_argument("--date", required=True, help="Beta day date, usually YYYY-MM-DD.")
    beta_day_report.add_argument("--group", required=True, help="QQ group id.")
    beta_day_report.add_argument(
        "--dry-run-review",
        required=True,
        help="Dry-run review report JSON file.",
    )
    beta_day_report.add_argument("--export-log", required=True, help="Exported audit log JSON file.")
    beta_day_report.add_argument(
        "--failures-json",
        help="Operator-maintained failure records JSON file.",
    )
    beta_day_report.add_argument("--output", required=True, help="Beta day report JSON file.")
    beta_day_report.add_argument("--json", action="store_true", help="Print JSON output.")

    regression_intake = qq_subparsers.add_parser(
        "regression-intake",
        help="Create QQ replay drafts from open beta failure records.",
    )
    regression_intake.add_argument("--group", required=True, help="QQ group id.")
    regression_intake.add_argument("--bot-user-id", required=True, help="Bot QQ user id.")
    regression_intake.add_argument(
        "--failures-json",
        required=True,
        help="Operator-maintained failure records JSON file.",
    )
    regression_intake.add_argument("--output-dir", required=True, help="Replay draft directory.")
    regression_intake.add_argument(
        "--index-output",
        required=True,
        help="Regression intake index JSON file.",
    )
    regression_intake.add_argument("--json", action="store_true", help="Print JSON output.")

    for name, help_text in (
        ("pause", "Pause one QQ group."),
        ("resume", "Resume one QQ group."),
    ):
        command = qq_subparsers.add_parser(name, help=help_text)
        _add_config_state_args(command)
        command.add_argument("--group", required=True, help="QQ group id.")
        command.add_argument("--operator", required=True, help="Operator QQ user id.")
        command.add_argument("--json", action="store_true", help="Print JSON output.")

    inspect = qq_subparsers.add_parser("inspect", help="Inspect configured bot assets.")
    inspect.add_argument(
        "target",
        choices=("role", "lorebook", "stickers"),
        help="Asset to inspect.",
    )
    inspect.add_argument("--config-json", required=True, help="QQ runtime config JSON.")
    inspect.add_argument("--json", action="store_true", help="Print JSON output.")

    health = qq_subparsers.add_parser("health", help="Show QQ operations health.")
    _add_config_state_args(health)
    health.add_argument("--json", action="store_true", help="Print JSON output.")

    export = qq_subparsers.add_parser("export-log", help="Export group audit log.")
    export.add_argument("--state-root", required=True, help="State root directory.")
    export.add_argument("--group", required=True, help="QQ group id.")
    export.add_argument("--output", required=True, help="Output JSON file.")
    export.add_argument("--json", action="store_true", help="Print JSON output.")


def handle_qq_command(
    args: argparse.Namespace,
    handlers: Mapping[str, QQHandler],
) -> dict[str, Any]:
    handler_key = _handler_key(args.command)
    handler = handlers.get(handler_key)
    if handler is None:
        raise ValueError(f"unknown qq command: {args.command}")
    return handler(args)


def _handler_key(command: str) -> str:
    if command in {"dry-run", "run"}:
        return "run"
    if command in {"pause", "resume"}:
        return "pause_resume"
    return command.replace("-", "_")


def _add_config_state_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config-json", required=True, help="QQ runtime config JSON.")
    parser.add_argument("--state-root", required=True, help="State root directory.")
