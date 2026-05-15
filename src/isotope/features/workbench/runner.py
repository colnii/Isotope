"""CLI runner for the workbench feature flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .flow import WorkbenchFlow


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope workbench flow.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show", help="Show the workbench summary.")
    show_parser.add_argument("--root", required=True, help="Runtime root directory.")
    show_parser.add_argument("--query", help="Optional search query.")
    show_parser.add_argument(
        "--type",
        action="append",
        dest="search_types",
        help="Filter search result type: project, task, or file.",
    )
    show_parser.add_argument("--limit", type=int, help="Maximum search result count.")
    show_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        flow = WorkbenchFlow.in_process(Path(args.root))
        if args.command == "show":
            search_types = (
                tuple(args.search_types)
                if args.search_types is not None
                else None
            )
            view = flow.summary(
                query=args.query,
                search_types=search_types,
                search_limit=args.limit,
            )
            payload = {"status": "ok", "workbench": view.to_dict()}
            if args.json:
                _print_json(payload)
            else:
                view_dict = view.to_dict()
                counts = view_dict["counts"]
                print(
                    "projects={projects} tasks={tasks} files={files} search_results={search_results}".format(
                        **counts
                    )
                )
                print(
                    "empty={empty} updated_at={updated_at}".format(
                        empty=str(view_dict["empty_state"] is not None).lower(),
                        updated_at=view_dict["updated_at"] or "none",
                    )
                )
            return 0
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "workbench_runner_error",
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
