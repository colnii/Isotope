"""CLI runner for social bot operations."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .qq_handlers import qq_handlers
from .qq_runner import handle_qq_command, register_qq_commands


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Isotope social bot operations.")
    subparsers = parser.add_subparsers(dest="surface", required=True)
    register_qq_commands(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.surface != "qq":
            raise ValueError(f"unknown social surface: {args.surface}")
        payload = handle_qq_command(args, qq_handlers())
        exit_code = int(payload.pop("_exit_code", 0))
        if getattr(args, "json", False):
            _print_json(payload)
        else:
            _print_plain(payload)
        return exit_code
    except (FileNotFoundError, RuntimeError, TimeoutError, ValueError) as exc:
        payload = {
            "status": "error",
            "error": {"code": "social_runner_error", "message": str(exc)},
        }
        if getattr(args, "json", False):
            _print_json(payload)
        else:
            print(f"error: {exc}")
        return 2


def _print_plain(payload: dict[str, Any]) -> None:
    print(f"status: {payload['status']}")


if __name__ == "__main__":
    raise SystemExit(main())
