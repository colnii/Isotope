"""CLI runner for the web research feature."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .flow import ResearchFlow
from .providers import FakeResearchProvider


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope research feature flow.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    search_parser = subparsers.add_parser("search", help="Run delegated research.")
    search_parser.add_argument("--root", required=True, help="Runtime root directory.")
    search_parser.add_argument("--query", help="Research query.")
    search_parser.add_argument(
        "--provider",
        default="fake",
        choices=("fake",),
        help="Research provider. First implementation supports fake for tests.",
    )
    search_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            if not args.query:
                raise ValueError("research search requires --query")
            flow = ResearchFlow.in_process(
                Path(args.root),
                provider=FakeResearchProvider(),
            )
            payload = flow.search(args.query).to_dict()
            if args.json:
                _print_json(payload)
            else:
                _print_plain(payload)
            return 0
    except ValueError as exc:
        error = {
            "status": "error",
            "error": {"code": "research_runner_error", "message": str(exc)},
        }
        if getattr(args, "json", False):
            _print_json(error)
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


def _print_plain(payload: dict[str, Any]) -> None:
    research = payload.get("research") or {}
    print(f"status: {payload['status']}")
    print(f"query: {research.get('query', '')}")
    print(f"evidence: {research.get('evidence_status', '')}")
    for source in research.get("sources", []):
        print(f"- {source['title']} {source['url']}")


if __name__ == "__main__":
    raise SystemExit(main())
