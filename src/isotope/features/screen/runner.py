"""Manual smoke runner for screen observe/control."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from isotope.execution.screen_windows_backend import WindowsScreenBackend
from isotope.runtime.in_process import InProcessServer


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _target_selector_from_args(
    *,
    app: str | None,
    title_contains: str | None,
    window_id: str | None,
) -> dict[str, Any]:
    selector: dict[str, Any] = {}
    if app:
        selector["app"] = app
    if title_contains:
        selector["title_contains"] = title_contains
    if window_id:
        selector["window_id"] = window_id
    if not selector:
        raise ValueError("target selector requires --app, --title-contains, or --window-id")
    return {
        "kind": "window",
        "selector": selector,
    }


def _default_smoke_matrix() -> list[dict[str, str]]:
    return [
        {
            "category": "basic_desktop_app",
            "sample": "notepad.exe or another simple text editor",
            "observe": "metadata,screenshot",
            "control": "dry_run click/key plan",
        },
        {
            "category": "browser_or_web_app",
            "sample": "browser tab with a non-sensitive local page",
            "observe": "metadata,screenshot",
            "control": "dry_run click/wheel plan",
        },
        {
            "category": "graphics_or_game_window",
            "sample": "windowed game/tool sample with no account or payment flow",
            "observe": "metadata,screenshot",
            "control": "manual approval only",
        },
    ]


def _build_observe_intent(
    *,
    target_selector: dict[str, Any],
    capture: list[str],
) -> dict[str, Any]:
    return {
        "action": "call_tool",
        "tool": "screen_observe",
        "target_selector": target_selector,
        "mode": "non_intrusive",
        "capture": list(capture),
        "summary": "manual screen observe smoke",
    }


def _build_control_intent(
    *,
    target_selector: dict[str, Any],
    actions: list[dict[str, Any]],
    execution_mode: str,
) -> dict[str, Any]:
    return {
        "action": "call_tool",
        "tool": "screen_control",
        "target_selector": target_selector,
        "mode": "interactive",
        "execution_mode": execution_mode,
        "actions": list(actions),
        "summary": "manual screen control smoke",
    }


def _build_click_action(*, x: int, y: int, button: str) -> dict[str, Any]:
    return {
        "type": "click",
        "button": button,
        "x": x,
        "y": y,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run manual screen observe/control smoke checks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    observe_parser = subparsers.add_parser("observe", help="Observe one target window.")
    _add_runtime_args(observe_parser)
    _add_target_args(observe_parser)
    observe_parser.add_argument(
        "--capture",
        action="append",
        choices=["metadata", "screenshot"],
        default=None,
        help="Capture kind. Can be repeated.",
    )

    control_parser = subparsers.add_parser("control", help="Plan or execute one target action sequence.")
    _add_runtime_args(control_parser)
    _add_target_args(control_parser)
    control_parser.add_argument(
        "--action-json",
        required=True,
        help="JSON list of screen actions, for example '[{\"type\":\"click\",\"button\":\"left\",\"x\":1,\"y\":2}]'.",
    )
    control_parser.add_argument(
        "--approve-execute",
        action="store_true",
        help="Request approval and execute after immediate local approval.",
    )

    click_parser = subparsers.add_parser(
        "control-click",
        help="Plan or execute one click without writing action JSON.",
    )
    _add_runtime_args(click_parser)
    _add_target_args(click_parser)
    click_parser.add_argument("--x", type=int, required=True, help="Screen x coordinate.")
    click_parser.add_argument("--y", type=int, required=True, help="Screen y coordinate.")
    click_parser.add_argument(
        "--button",
        choices=["left", "middle", "right", "x1", "x2"],
        default="left",
        help="Mouse button.",
    )
    click_parser.add_argument(
        "--approve-execute",
        action="store_true",
        help="Request approval and execute after immediate local approval.",
    )

    matrix_parser = subparsers.add_parser("smoke-matrix", help="Print the manual smoke matrix.")
    matrix_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def _add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", required=True, help="Runtime root directory.")
    parser.add_argument("--goal", default="screen smoke", help="Run goal label.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")


def _add_target_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app", help="Target process name, for example notepad.exe.")
    parser.add_argument("--title-contains", help="Substring expected in the target window title.")
    parser.add_argument("--window-id", help="Native window id from a prior metadata observation.")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "smoke-matrix":
            payload = {"status": "ok", "matrix": _default_smoke_matrix()}
            if args.json:
                _print_json(payload)
            else:
                for entry in payload["matrix"]:
                    print(
                        "{category}: sample={sample}; observe={observe}; control={control}".format(
                            **entry
                        )
                    )
            return 0

        target_selector = _target_selector_from_args(
            app=args.app,
            title_contains=args.title_contains,
            window_id=args.window_id,
        )
        api = _new_server(Path(args.root))
        session = api.create_session()
        run = api.create_run(session["session_id"], goal=args.goal)
        run_id = run["run_id"]

        if args.command == "observe":
            capture = args.capture or ["metadata", "screenshot"]
            result = api.submit_action(
                run_id,
                _build_observe_intent(target_selector=target_selector, capture=capture),
            )
        elif args.command == "control":
            actions = _actions_from_json(args.action_json)
            execution_mode = "execute" if args.approve_execute else "dry_run"
            pending_or_result = api.submit_action(
                run_id,
                _build_control_intent(
                    target_selector=target_selector,
                    actions=actions,
                    execution_mode=execution_mode,
                ),
                requires_approval=args.approve_execute,
            )
            if args.approve_execute and pending_or_result["status"] == "pending_user_approval":
                result = api.resolve_approval(
                    pending_or_result["approval_id"],
                    {
                        "resolution": "approved",
                        "reason": "screen smoke execute approved",
                        "resolver": "local_operator",
                    },
                )
            else:
                result = pending_or_result
        elif args.command == "control-click":
            execution_mode = "execute" if args.approve_execute else "dry_run"
            pending_or_result = api.submit_action(
                run_id,
                _build_control_intent(
                    target_selector=target_selector,
                    actions=[_build_click_action(x=args.x, y=args.y, button=args.button)],
                    execution_mode=execution_mode,
                ),
                requires_approval=args.approve_execute,
            )
            if args.approve_execute and pending_or_result["status"] == "pending_user_approval":
                result = api.resolve_approval(
                    pending_or_result["approval_id"],
                    {
                        "resolution": "approved",
                        "reason": "screen smoke click execute approved",
                        "resolver": "local_operator",
                    },
                )
            else:
                result = pending_or_result
        else:
            parser.error(f"unknown command: {args.command}")
            return 2

        payload = {
            "status": result["status"],
            "run_id": run_id,
            "execution_id": result.get("execution_id"),
            "artifact_ref": _ref_to_dict(result.get("artifact_ref")),
        }
        if args.json:
            _print_json(payload)
        else:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "screen_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}")
        return 2


def _new_server(root: Path) -> InProcessServer:
    return InProcessServer(
        root,
        screen_backend=WindowsScreenBackend(),
        screen_backend_config={
            "backend_id": "windows_screen",
            "backend_version": "0.1",
        },
    )


def _actions_from_json(value: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("action-json must be valid JSON") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("action-json must be a non-empty JSON list")
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"action-json[{index}] must be an object")
    return parsed


def _ref_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(value, dict):
        return dict(value)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
