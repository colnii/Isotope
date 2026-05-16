"""CLI runner for the read-only Codex supervisor."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .flow import CodexSupervisorFlow, render_plain_report
from .llm_summary import generate_llm_summary, resolve_summary_provider_from_env
from .registry import launch_managed_codex, send_to_managed_codex


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch local Codex sessions.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("scan", "Print one Codex supervisor report."),
        ("watch", "Print reports repeatedly."),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument(
            "--codex-home",
            default=str(Path.home() / ".codex"),
            help="Codex home directory. Defaults to ~/.codex.",
        )
        subparser.add_argument("--limit", type=int, default=10, help="Maximum sessions.")
        subparser.add_argument(
            "--stale-after",
            type=int,
            default=600,
            help="Seconds without events before marking a session stale.",
        )
        subparser.add_argument(
            "--active-within",
            type=int,
            default=180,
            help="Seconds with recent events before marking a session working.",
        )
        subparser.add_argument("--json", action="store_true", help="Print JSON output.")
        subparser.add_argument(
            "--llm-summary",
            action="store_true",
            help="Use configured LLM to add a compact Chinese summary.",
        )
    watch_parser = subparsers.choices["watch"]
    watch_parser.add_argument(
        "--interval",
        type=int,
        default=180,
        help="Seconds between reports.",
    )
    watch_parser.add_argument(
        "--iterations",
        type=int,
        help="Stop after this many reports. Omit to watch until interrupted.",
    )
    watch_parser.add_argument(
        "--changes-only",
        action="store_true",
        help="In watch mode, print only when session state changes.",
    )
    launch_parser = subparsers.add_parser("launch", help="Launch and register a Codex process.")
    launch_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    launch_parser.add_argument("--cwd", required=True, help="Workspace directory for Codex.")
    launch_parser.add_argument("--name", required=True, help="Managed lane name.")
    launch_parser.add_argument("--prompt", required=True, help="Initial Codex prompt.")
    launch_parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable name or path.",
    )
    launch_parser.add_argument(
        "--backend",
        choices=("process", "tmux"),
        default="process",
        help="Launch backend.",
    )
    launch_parser.add_argument(
        "--tmux-session",
        help="tmux session name when --backend tmux is used. Defaults to --name.",
    )
    launch_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    send_parser = subparsers.add_parser(
        "send", help="Send one line to a tmux-managed Codex process."
    )
    send_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    send_parser.add_argument("--name", required=True, help="Managed lane name.")
    send_parser.add_argument("--text", required=True, help="Text to send.")
    send_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            _print_report(args)
            return 0
        if args.command == "watch":
            if args.interval <= 0:
                raise ValueError("interval must be positive")
            if args.iterations is not None and args.iterations <= 0:
                raise ValueError("iterations must be positive")
            iterations = args.iterations
            count = 0
            previous_fingerprint: tuple[object, ...] | None = None
            while iterations is None or count < iterations:
                printed, previous_fingerprint = _print_report(
                    args, previous_fingerprint=previous_fingerprint
                )
                if printed and iterations is not None and count + 1 < iterations:
                    print()
                count += 1
                if iterations is None or count < iterations:
                    time.sleep(args.interval)
            return 0
        if args.command == "launch":
            record = launch_managed_codex(
                codex_home=Path(args.codex_home),
                cwd=Path(args.cwd),
                name=args.name,
                prompt=args.prompt,
                codex_bin=args.codex_bin,
                backend=args.backend,
                tmux_session=args.tmux_session,
                popen=subprocess.Popen,
                run=subprocess.run,
            )
            if args.json:
                _print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已启动托管 Codex：{record.name}")
                print(f"pid：{record.pid}")
                print(f"日志：{record.log_path}")
            return 0
        if args.command == "send":
            result = send_to_managed_codex(
                codex_home=Path(args.codex_home),
                name=args.name,
                text=args.text,
                run=subprocess.run,
            )
            if args.json:
                _print_json(
                    {
                        "status": "ok",
                        "text": result.text,
                        "managed": {
                            "name": result.record.name,
                            "record_id": result.record.record_id,
                            "tmux_session": result.record.tmux_session,
                        },
                    }
                )
            else:
                print(f"已发送到托管 Codex：{result.record.name}")
                print(f"tmux：{result.record.tmux_session}")
                print(f"内容：{result.text}")
            return 0
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


def _print_report(
    args: argparse.Namespace,
    *,
    previous_fingerprint: tuple[object, ...] | None = None,
) -> tuple[bool, tuple[object, ...]]:
    flow = CodexSupervisorFlow(codex_home=Path(args.codex_home))
    report = flow.scan(
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )
    fingerprint = _report_fingerprint(report)
    if getattr(args, "changes_only", False) and previous_fingerprint == fingerprint:
        return False, fingerprint
    if args.json:
        payload = report.to_dict()
        if args.llm_summary:
            payload["llm_summary"] = _summarize_with_llm(report)
        _print_json(payload)
    else:
        print(render_plain_report(report))
        if args.llm_summary:
            print()
            print("[LLM 摘要]")
            print(_summarize_with_llm(report))
    return True, fingerprint


def _report_fingerprint(report: Any) -> tuple[object, ...]:
    """生成变化指纹；忽略 generated_at，避免空转也被当作变化。"""
    return tuple(
        (
            session.session_id,
            session.cwd,
            session.git_branch,
            session.source_path,
            session.last_event_at,
            session.status,
            session.reason,
            session.last_user_message,
            session.last_assistant_message,
        )
        for session in report.sessions
    )


def _summarize_with_llm(report: Any) -> str:
    provider = resolve_summary_provider_from_env(agent_name="supervisor")
    return generate_llm_summary(report, provider)


if __name__ == "__main__":
    raise SystemExit(main())
