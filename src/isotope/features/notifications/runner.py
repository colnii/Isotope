"""CLI runner for the notification feature flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .flow import NotificationFlow


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope notification feature flow.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create one notification.")
    create_parser.add_argument("--root", required=True, help="Runtime root directory.")
    create_parser.add_argument("--type", required=True, help="Notification type.")
    create_parser.add_argument("--title", required=True, help="Notification title.")
    create_parser.add_argument(
        "--source-ref-json",
        help="Low-sensitive JSON object that links this notification to a source.",
    )
    create_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    list_parser = subparsers.add_parser("list", help="List notifications.")
    list_parser.add_argument("--root", required=True, help="Runtime root directory.")
    list_parser.add_argument("--type", help="Filter by notification type.")
    list_parser.add_argument("--unread", action="store_true", help="Only list unread notifications.")
    list_parser.add_argument("--read", action="store_true", help="Only list read notifications.")
    list_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    mark_parser = subparsers.add_parser("mark-read", help="Mark one notification as read.")
    mark_parser.add_argument("--root", required=True, help="Runtime root directory.")
    mark_parser.add_argument("--notification-id", required=True, help="Notification id.")
    mark_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        flow = NotificationFlow.in_process(Path(args.root))
        if args.command == "create":
            summary = flow.create_notification(
                notification_type=args.type,
                title=args.title,
                source_ref=_source_ref_from_json(args.source_ref_json),
            )
            payload = {"status": "ok", "notification": summary.to_dict()}
            if args.json:
                _print_json(payload)
            else:
                print(f"{summary.notification_id}: {summary.notification_type} unread")
            return 0
        if args.command == "list":
            if args.unread and args.read:
                raise ValueError("list cannot combine --unread and --read")
            unread = True if args.unread else False if args.read else None
            payload = {
                "status": "ok",
                "notifications": [
                    summary.to_dict()
                    for summary in flow.list_notifications(
                        unread=unread,
                        notification_type=args.type,
                    )
                ],
            }
            if args.json:
                _print_json(payload)
            else:
                for summary in flow.list_notifications(
                    unread=unread,
                    notification_type=args.type,
                ):
                    state = "unread" if summary.unread else "read"
                    print(f"{summary.notification_id}: {summary.notification_type} {state}")
            return 0
        if args.command == "mark-read":
            summary = flow.mark_read(args.notification_id)
            payload = {"status": "ok", "notification": summary.to_dict()}
            if args.json:
                _print_json(payload)
            else:
                print(f"{summary.notification_id}: read")
            return 0
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "notification_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


def _source_ref_from_json(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("source_ref_json must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("source_ref_json must be a JSON object")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
