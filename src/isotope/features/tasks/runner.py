"""CLI runner for the task feature flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .flow import TaskFlow


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope task feature flow.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Create and run one task.")
    run_parser.add_argument("--root", required=True, help="Runtime root directory.")
    run_parser.add_argument("--goal", required=True, help="Task goal.")
    run_parser.add_argument("--message", help="First user message for the task.")
    run_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            if not args.message:
                raise ValueError("run requires --message")
            summary = TaskFlow.in_process(Path(args.root)).create_task(
                goal=args.goal,
                first_message=args.message,
            )
            payload = {"status": "ok", "task": summary.to_dict()}
            if args.json:
                _print_json(payload)
            else:
                print(f"{summary.task_id}: {summary.status}")
            return 0
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "task_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
