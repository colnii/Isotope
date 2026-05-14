"""Thin capability runner shell over the low-sensitive capability catalog.

This module intentionally stays small: catalog metadata remains the source of
truth, and execution is limited to deterministic in-process demo scenarios.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from .capability_catalog import CapabilityCatalog
from .demo import run_demo


_CAPABILITY_SCENARIOS = {
    "approval.tool.runner": "approval-tool-runner",
    "artifact.review": "artifact-review",
    "external.snapshot.review": "external-snapshot-review",
}

_SUMMARY_KEYS = (
    "run_status",
    "memory_status",
    "event_count",
    "http_api_ok",
    "approval_ok",
    "artifact_content_policy_ok",
    "http_full_content_route_status",
    "external_ingestion_route_status",
    "external_observation_count",
    "conflict_diagnostic_count",
)


class CapabilityRunner:
    def __init__(self, *, catalog: CapabilityCatalog | None = None):
        self._catalog = catalog or CapabilityCatalog.default()

    def list_capabilities(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._catalog.list_capabilities(**kwargs)

    def describe_capability(self, capability_id: str) -> dict[str, Any]:
        return dict(self._lookup_capability(capability_id))

    def get_capability_status(
        self, capability_id: str, *, env: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        return self._catalog.get_capability_status(capability_id, env=env)

    def run_capability(
        self,
        capability_id: str,
        *,
        root_path: Path | str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        capability = self._lookup_capability(capability_id)
        shelf = capability["shelf"]
        if shelf in {"diagnostic", "experimental"}:
            raise PermissionError(f"{shelf} capability cannot run by default")

        status = self._catalog.get_capability_status(capability_id, env=env)
        if not status["ready"]:
            raise PermissionError(f"capability not ready: {status['status']}")

        try:
            scenario = _CAPABILITY_SCENARIOS[capability_id]
        except KeyError as exc:
            raise PermissionError(f"capability is not allowlisted: {capability_id}") from exc

        demo_result = run_demo(root_path=root_path, scenario=scenario)
        summary = {
            key: demo_result[key] for key in _SUMMARY_KEYS if key in demo_result
        }
        return {
            "kind": "capability_run_result",
            "capability_id": capability_id,
            "status": "completed",
            "scenario": scenario,
            "replay_ok": bool(demo_result.get("replay_ok")),
            "checkpoint_ok": bool(demo_result.get("checkpoint_ok")),
            "summary": summary,
        }

    def _lookup_capability(self, capability_id: str) -> dict[str, Any]:
        entries = self._catalog.list_capabilities(
            include_diagnostics=True,
            include_experimental=True,
        )
        for entry in entries:
            if entry["capability_id"] == capability_id:
                return entry
        raise ValueError(f"unknown capability: {capability_id}")


def default_runner() -> CapabilityRunner:
    return CapabilityRunner()


def list_capabilities(**kwargs: Any) -> list[dict[str, Any]]:
    return default_runner().list_capabilities(**kwargs)


def describe_capability(capability_id: str) -> dict[str, Any]:
    return default_runner().describe_capability(capability_id)


def get_capability_status(capability_id: str, **kwargs: Any) -> dict[str, Any]:
    return default_runner().get_capability_status(capability_id, **kwargs)


def run_capability(capability_id: str, **kwargs: Any) -> dict[str, Any]:
    return default_runner().run_capability(capability_id, **kwargs)


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
        prog="python -m isotope_kernel.capability_runner",
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

    run_parser = subparsers.add_parser("run", help="Run an allowlisted capability.")
    run_parser.add_argument("capability_id")
    run_parser.add_argument("--root", type=Path)
    run_parser.add_argument("--json", action="store_true", dest="as_json")

    return parser


def main(argv: list[str] | None = None) -> int:
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

        if args.command == "run":
            result = runner.run_capability(args.capability_id, root_path=args.root)
            if args.as_json:
                _print_json({"status": "ok", "run": result})
            else:
                print(f"{args.capability_id}: {result['status']}")
                print(f"scenario: {result['scenario']}")
                print(f"replay_ok: {str(result['replay_ok']).lower()}")
                print(f"checkpoint_ok: {str(result['checkpoint_ok']).lower()}")
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


if __name__ == "__main__":
    raise SystemExit(main())
