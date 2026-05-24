"""Command-line interface for the capability runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


def _json_object_argument(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid input JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("input JSON must be an object")
    return payload


def _print_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _print_capability_list(capabilities: list[dict[str, Any]]) -> None:
    for capability in capabilities:
        print(f"{capability['capability_id']}: {capability['shelf']}")


def _print_mapping(prefix: str, payload: Mapping[str, Any]) -> None:
    print(prefix)
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            continue
        print(f"{key}: {value}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m isotope.capabilities.runner",
        description="Run the small, allowlisted Isotope capability runner.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List visible capabilities.")
    list_parser.add_argument("--json", action="store_true", dest="as_json")
    list_parser.add_argument("--include-diagnostics", action="store_true")
    list_parser.add_argument("--include-experimental", action="store_true")
    list_parser.add_argument("--shelf")

    describe_parser = subparsers.add_parser("describe", help="Describe one capability.")
    describe_parser.add_argument("capability_id")
    describe_parser.add_argument("--json", action="store_true", dest="as_json")

    status_parser = subparsers.add_parser("status", help="Check one capability status.")
    status_parser.add_argument("capability_id")
    status_parser.add_argument("--json", action="store_true", dest="as_json")

    search_parser = subparsers.add_parser("search", help="Search visible capabilities.")
    search_parser.add_argument("query", nargs="?", default="")
    search_parser.add_argument("--json", action="store_true", dest="as_json")
    search_parser.add_argument("--include-diagnostics", action="store_true")
    search_parser.add_argument("--include-experimental", action="store_true")
    search_parser.add_argument("--shelf")

    plan_parser = subparsers.add_parser("plan", help="Plan one capability run.")
    plan_parser.add_argument("capability_id")
    plan_parser.add_argument("--input-json")
    plan_parser.add_argument("--json", action="store_true", dest="as_json")

    run_parser = subparsers.add_parser("run", help="Run an allowlisted capability.")
    run_parser.add_argument("capability_id")
    run_parser.add_argument("--root", type=Path)
    run_parser.add_argument("--input-json")
    run_parser.add_argument("--json", action="store_true", dest="as_json")

    return parser


def main(argv: list[str] | None = None) -> int:
    from .runner import CapabilityRunner

    parser = _build_parser()
    args = parser.parse_args(argv)
    runner = CapabilityRunner()
    try:
        if args.command == "list":
            capabilities = runner.list_capabilities(
                shelf=args.shelf,
                include_diagnostics=args.include_diagnostics,
                include_experimental=args.include_experimental,
            )
            if args.as_json:
                _print_json({"status": "ok", "capabilities": capabilities})
            else:
                _print_capability_list(capabilities)
            return 0

        if args.command == "describe":
            capability = runner.describe_capability(args.capability_id)
            if args.as_json:
                _print_json({"status": "ok", "capability": capability})
            else:
                _print_mapping(args.capability_id, capability)
            return 0

        if args.command == "status":
            status = runner.get_capability_status(args.capability_id)
            if args.as_json:
                _print_json({"status": "ok", "capability_status": status})
            else:
                print(f"{args.capability_id}: {status['status']}")
                if status.get("missing_env"):
                    print("missing_env: " + ", ".join(status["missing_env"]))
            return 0

        if args.command == "search":
            result = runner.search_capabilities(
                query=args.query,
                shelf=args.shelf,
                include_diagnostics=args.include_diagnostics,
                include_experimental=args.include_experimental,
            )
            if args.as_json:
                _print_json({"status": "ok", "search": result})
            else:
                _print_capability_list(result["capabilities"])
            return 0

        if args.command == "plan":
            inputs = _json_object_argument(args.input_json)
            plan = runner.plan_capability_run(args.capability_id, inputs=inputs)
            if args.as_json:
                _print_json({"status": "ok", "plan": plan})
            else:
                _print_mapping(args.capability_id, plan)
            return 0

        if args.command == "run":
            inputs = _json_object_argument(args.input_json)
            result = runner.run_capability(
                args.capability_id,
                root_path=args.root,
                inputs=inputs,
            )
            if args.as_json:
                _print_json({"status": "ok", "run": result})
            else:
                print(f"{args.capability_id}: {result['status']}")
                if "scenario" in result:
                    print(f"scenario: {result['scenario']}")
                    print(f"replay_ok: {str(result['replay_ok']).lower()}")
                    print(f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}")
                elif "runner_kind" in result:
                    print(f"runner_kind: {result['runner_kind']}")
            return 0
    except (KeyError, PermissionError, ValueError) as exc:
        if getattr(args, "as_json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "capability_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"unsupported command: {args.command}")
    return 2
