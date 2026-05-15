"""CLI runner for the file feature flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .flow import FileFlow


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope file feature flow.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create one text file summary.")
    create_parser.add_argument("--root", required=True, help="Runtime root directory.")
    create_parser.add_argument("--name", required=True, help="File name.")
    create_parser.add_argument("--summary", required=True, help="File summary.")
    create_parser.add_argument("--content", help="Full file content.")
    create_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    get_parser = subparsers.add_parser("get", help="Read one file summary.")
    get_parser.add_argument("--root", required=True, help="Runtime root directory.")
    get_parser.add_argument("--file-id", help="File id.")
    get_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    list_parser = subparsers.add_parser("list", help="List file summaries.")
    list_parser.add_argument("--root", required=True, help="Runtime root directory.")
    list_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        flow = FileFlow.in_process(Path(args.root))
        if args.command == "create":
            if not args.content:
                raise ValueError("create requires --content")
            summary = flow.create_text_file(
                name=args.name,
                summary=args.summary,
                content=args.content,
            )
            payload = {"status": "ok", "file": summary.to_dict()}
            if args.json:
                _print_json(payload)
            else:
                print(f"{summary.file_id}: {summary.name}")
            return 0
        if args.command == "get":
            if not args.file_id:
                raise ValueError("get requires --file-id")
            summary = flow.get_file(args.file_id)
            payload = {"status": "ok", "file": summary.to_dict()}
            if args.json:
                _print_json(payload)
            else:
                print(f"{summary.file_id}: {summary.name}")
            return 0
        if args.command == "list":
            summaries = [summary.to_dict() for summary in flow.list_files()]
            payload = {"status": "ok", "files": summaries}
            if args.json:
                _print_json(payload)
            else:
                for summary in flow.list_files():
                    print(f"{summary.file_id}: {summary.name}")
            return 0
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "file_runner_error",
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
