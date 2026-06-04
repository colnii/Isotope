"""CLI runner for the search feature flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .flow import SearchFlow


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope search feature flow.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search public summaries.")
    search_parser.add_argument("--root", required=True, help="Runtime root directory.")
    search_parser.add_argument("--query", help="Search query.")
    search_parser.add_argument(
        "--type",
        action="append",
        dest="result_types",
        help="Filter result type: project, task, or file.",
    )
    search_parser.add_argument("--limit", type=int, help="Maximum result count.")
    search_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        flow = SearchFlow.in_process(Path(args.root))
        if args.command == "search":
            if not args.query:
                raise ValueError("search requires --query")
            result_types = (
                tuple(args.result_types)
                if args.result_types is not None
                else None
            )
            results = [
                result.to_dict()
                for result in flow.search(
                    args.query,
                    result_types=result_types,
                    limit=args.limit,
                )
            ]
            payload = {"status": "ok", "results": results}
            if args.json:
                _print_json(payload)
            else:
                for result in results:
                    print(f"{result['result_type']}:{result['result_id']} {result['title']}")
            return 0
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "search_runner_error",
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
