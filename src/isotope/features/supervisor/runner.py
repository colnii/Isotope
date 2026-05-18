"""CLI runner for the read-only Codex supervisor."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .flow import (
    CodexSupervisorFlow,
    _terminal_has_active_work_marker,
    _tmux_capture_pane,
    render_plain_report,
)
from .lane_state import (
    DEFAULT_PROMPT_COOLDOWN_SECONDS,
    prompt_cooldown_state,
    record_lane_prompt,
)
from .llm_summary import (
    generate_llm_action_decision,
    generate_llm_summary,
    resolve_summary_provider_from_env,
)
from .registry import (
    adopt_tmux_session,
    archive_managed_codex,
    default_registry_path,
    launch_managed_codex,
    read_managed_record_events,
    repair_tmux_bell_hooks,
    send_to_managed_codex,
)
from .tmux_discovery import discover_tmux_adopt_candidates

EXECUTABLE_ADVICE_KINDS = {"send_status", "send_continue"}
TERMINAL_DONE_NEXT_MARKERS = (
    "可结束",
    "可以结束",
    "任务结束",
    "可归档",
    "可以归档",
    "等待归档",
    "等待 supervisor 归档",
    "归档或下发新任务",
    "无需继续",
    "不需要继续",
    "不用继续",
)
STATUS_REPORT_REQUEST = "\n".join(
    [
        "请汇报当前状态，回复时严格输出三行：",
        "第一行 `SUPERVISOR_STATUS: working|done|blocked|needs_user`；",
        "第二行 `SUPERVISOR_SUMMARY: 用一句中文说明当前进展`；",
        "第三行 `SUPERVISOR_NEXT: 用一句中文说明建议下一步`。",
    ]
)
EXECUTABLE_ADVICE_TEXT = {
    "send_status": " ".join(STATUS_REPORT_REQUEST.splitlines()),
    "send_continue": " ".join(
        [
            "继续推进当前任务。",
            "完成或遇到阻塞后，严格输出三行：",
            "第一行 `SUPERVISOR_STATUS: working|done|blocked|needs_user`；",
            "第二行 `SUPERVISOR_SUMMARY: 用一句中文说明当前进展`；",
            "第三行 `SUPERVISOR_NEXT: 用一句中文说明建议下一步`。",
        ]
    ),
}
LAUNCH_TMUX_HINT = (
    "isotope-supervisor launch --backend tmux --name <name> --cwd <repo> --prompt '<task>'"
)
ADOPT_TMUX_HINT = (
    "isotope-supervisor adopt --name <name> --cwd <repo> --tmux-session <session>"
)
DASHBOARD_GROUP_LABELS = {
    "needs_attention": "需要看",
    "done": "已完成",
    "working": "工作中",
}


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch local Codex sessions.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("scan", "Print one Codex supervisor report."),
        ("dashboard", "Print one grouped supervisor dashboard."),
        ("watch", "Print reports repeatedly."),
        ("advise", "Print one compact next-action suggestion."),
        ("supervise", "Run repeated reports with advice, optional LLM summary, and send execution."),
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
    for command in ("advise", "supervise"):
        subparsers.choices[command].add_argument(
            "--name",
            help="Target one managed lane by name for suggestions or execution.",
        )
        subparsers.choices[command].add_argument(
            "--execute",
            help="Execute one generated send suggestion. Supports send_status or send_continue.",
        )
        subparsers.choices[command].add_argument(
            "--llm-action",
            action="store_true",
            help="Ask configured LLM to choose one whitelist action without executing it.",
        )
        subparsers.choices[command].add_argument(
            "--llm-execute",
            action="store_true",
            help="Execute one LLM-chosen whitelist send action, or skip monitor.",
        )
        subparsers.choices[command].add_argument(
            "--prompt-cooldown",
            type=int,
            default=DEFAULT_PROMPT_COOLDOWN_SECONDS,
            help="Seconds before repeating send_status/send_continue for the same lane.",
        )
    for command in ("watch", "supervise"):
        command_parser = subparsers.choices[command]
        command_parser.add_argument(
            "--interval",
            type=int,
            default=180,
            help="Seconds between reports.",
        )
        command_parser.add_argument(
            "--iterations",
            type=int,
            help="Stop after this many reports. Omit to watch until interrupted.",
        )
        command_parser.add_argument(
            "--changes-only",
            action="store_true",
            help="Print only when session state changes.",
        )
    subparsers.choices["watch"].add_argument(
        "--bell",
        action="store_true",
        help="Write a terminal bell when a printed report needs attention.",
    )
    subparsers.choices["supervise"].add_argument(
        "--auto-execute",
        action="store_true",
        help="Use the rule-based auto policy to execute one whitelist action per loop.",
    )
    subparsers.choices["supervise"].add_argument(
        "--auto-adopt",
        action="store_true",
        help="Automatically adopt newly discovered Codex-like tmux sessions before each loop.",
    )
    subparsers.choices["supervise"].add_argument(
        "--bell",
        action="store_true",
        help="Write a terminal bell when a supervise iteration still needs human attention.",
    )
    loop_parser = subparsers.add_parser(
        "loop",
        help="Run the daily managed Supervisor loop with safe defaults.",
    )
    loop_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    loop_parser.add_argument("--limit", type=int, default=10, help="Maximum sessions.")
    loop_parser.add_argument(
        "--stale-after",
        type=int,
        default=600,
        help="Seconds without events before marking a session stale.",
    )
    loop_parser.add_argument(
        "--active-within",
        type=int,
        default=180,
        help="Seconds with recent events before marking a session working.",
    )
    loop_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    loop_parser.add_argument(
        "--llm-summary",
        action="store_true",
        help="Use configured LLM to add a compact Chinese summary.",
    )
    loop_parser.add_argument(
        "--name",
        help="Target one managed lane by name. Omit to rotate across active lanes.",
    )
    loop_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating send_status/send_continue for the same lane.",
    )
    loop_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between reports.",
    )
    loop_parser.add_argument(
        "--iterations",
        type=int,
        help="Stop after this many reports. Omit to loop until interrupted.",
    )
    loop_parser.add_argument(
        "--no-auto-adopt",
        action="store_false",
        dest="auto_adopt",
        help="Disable automatic adoption of discovered Codex-like tmux sessions.",
    )
    loop_parser.set_defaults(
        auto_execute=True,
        auto_adopt=True,
        changes_only=True,
        bell=True,
        execute=None,
        llm_action=False,
        llm_execute=False,
    )
    web_parser = subparsers.add_parser("web", help="Serve a local Supervisor dashboard page.")
    web_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    web_parser.add_argument("--limit", type=int, default=10, help="Maximum sessions.")
    web_parser.add_argument(
        "--stale-after",
        type=int,
        default=600,
        help="Seconds without events before marking a session stale.",
    )
    web_parser.add_argument(
        "--active-within",
        type=int,
        default=180,
        help="Seconds with recent events before marking a session working.",
    )
    web_parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    web_parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    web_parser.add_argument(
        "--print-url",
        action="store_true",
        help="Print the local URL and exit without starting the server.",
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
    adopt_parser = subparsers.add_parser(
        "adopt", help="Register an existing tmux session as a managed Codex lane."
    )
    adopt_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    adopt_parser.add_argument("--cwd", required=True, help="Workspace directory.")
    adopt_parser.add_argument("--name", required=True, help="Managed lane name.")
    adopt_parser.add_argument("--tmux-session", required=True, help="Existing tmux session.")
    adopt_parser.add_argument(
        "--prompt",
        default="接管已有 tmux 会话",
        help="Short note stored in the managed registry.",
    )
    adopt_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    discover_parser = subparsers.add_parser(
        "discover", help="List existing tmux sessions that can be adopted."
    )
    discover_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    discover_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory used in generated adopt commands.",
    )
    discover_parser.add_argument(
        "--adopt-index",
        type=int,
        help="Adopt the 1-based candidate index from the discovery result.",
    )
    discover_parser.add_argument(
        "--adopt-first",
        action="store_true",
        help="Adopt the first discovered Codex-like tmux session.",
    )
    discover_parser.add_argument(
        "--name",
        help="Managed lane name when adopting. Defaults to the suggested candidate name.",
    )
    discover_parser.add_argument(
        "--prompt",
        default="接管已有 tmux 会话",
        help="Short note stored in the managed registry when adopting.",
    )
    discover_parser.add_argument(
        "--include-all",
        action="store_true",
        help="Include tmux sessions whose pane text does not look like Codex.",
    )
    discover_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    archive_parser = subparsers.add_parser(
        "archive", help="Archive a managed Codex lane so it stops appearing as active."
    )
    archive_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    archive_parser.add_argument("--name", required=True, help="Managed lane name.")
    archive_parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
    repair_parser = subparsers.add_parser(
        "repair-hooks",
        help="Repair tmux bell hooks for registered managed Codex lanes.",
    )
    repair_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    repair_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    guide_parser = subparsers.add_parser(
        "guide", help="Print a ready-to-run Supervisor workflow."
    )
    guide_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory. Defaults to the current directory.",
    )
    guide_parser.add_argument(
        "--name",
        default="lane-a",
        help="Managed lane name used in generated commands.",
    )
    guide_parser.add_argument(
        "--tmux-session",
        help="tmux session name. Defaults to --name.",
    )
    guide_parser.add_argument(
        "--prompt",
        default="继续推进当前任务，并在完成或阻塞时按 SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。",
        help="Prompt used by the launch command.",
    )
    guide_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Supervise loop interval seconds.",
    )
    guide_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            _print_report(args)
            return 0
        if args.command == "dashboard":
            _print_dashboard(args)
            return 0
        if args.command == "advise":
            _validate_execution_modes(args)
            _print_advice(args)
            return 0
        if args.command == "supervise":
            _validate_execution_modes(args)
            _run_supervise(args)
            return 0
        if args.command == "loop":
            _validate_execution_modes(args)
            _run_supervise(args)
            return 0
        if args.command == "watch":
            if args.interval <= 0:
                raise ValueError("interval must be positive")
            if args.iterations is not None and args.iterations <= 0:
                raise ValueError("iterations must be positive")
            iterations = args.iterations
            count = 0
            previous_fingerprint: tuple[object, ...] | None = None
            previous_bell_fingerprint: tuple[object, ...] | None = None
            while iterations is None or count < iterations:
                printed, previous_fingerprint, previous_bell_fingerprint = _print_report(
                    args,
                    previous_fingerprint=previous_fingerprint,
                    previous_bell_fingerprint=previous_bell_fingerprint,
                )
                if printed and iterations is not None and count + 1 < iterations:
                    print()
                count += 1
                if iterations is None or count < iterations:
                    _sleep(args.interval)
            return 0
        if args.command == "web":
            _run_web(args)
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
        if args.command == "adopt":
            record = adopt_tmux_session(
                codex_home=Path(args.codex_home),
                cwd=Path(args.cwd),
                name=args.name,
                tmux_session=args.tmux_session,
                prompt=args.prompt,
                run=subprocess.run,
            )
            if args.json:
                _print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已接管 tmux 会话：{record.name}")
                print(f"tmux：{record.tmux_session}")
            return 0
        if args.command == "discover":
            payload = _discover_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_discover_plain(payload)
            return 0
        if args.command == "archive":
            record = archive_managed_codex(
                codex_home=Path(args.codex_home),
                name=args.name,
            )
            if args.json:
                _print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已归档托管 Codex：{record.name}")
                if record.tmux_session:
                    print(f"tmux：{record.tmux_session}")
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
        if args.command == "repair-hooks":
            repairs = repair_tmux_bell_hooks(
                codex_home=Path(args.codex_home),
                run=subprocess.run,
            )
            if args.json:
                _print_json(
                    {
                        "status": "ok",
                        "repairs": [repair.to_dict() for repair in repairs],
                    }
                )
            else:
                if not repairs:
                    print("没有需要修复的托管 tmux 会话。")
                for repair in repairs:
                    print(
                        f"{repair.tmux_session} / {repair.name}: {repair.status}"
                        + (f" / {repair.message}" if repair.message else "")
                    )
            return 0
        if args.command == "guide":
            payload = _guide_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_guide_plain(payload)
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
    previous_bell_fingerprint: tuple[object, ...] | None = None,
) -> tuple[bool, tuple[object, ...], tuple[object, ...] | None]:
    flow = CodexSupervisorFlow(codex_home=Path(args.codex_home))
    report = flow.scan(
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )
    fingerprint = _report_fingerprint(report)
    if getattr(args, "changes_only", False) and previous_fingerprint == fingerprint:
        return False, fingerprint, previous_bell_fingerprint
    bell_fingerprint = _attention_bell_fingerprint(report)
    if (
        getattr(args, "bell", False)
        and bell_fingerprint is not None
        and bell_fingerprint != previous_bell_fingerprint
    ):
        _emit_terminal_bell()
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
    return True, fingerprint, bell_fingerprint


def _run_supervise(args: argparse.Namespace) -> None:
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    if args.iterations is not None and args.iterations <= 0:
        raise ValueError("iterations must be positive")
    iterations = args.iterations
    count = 0
    previous_fingerprint: tuple[object, ...] | None = None
    previous_bell_fingerprint: tuple[object, ...] | None = None
    while iterations is None or count < iterations:
        auto_adopted = _auto_adopt_discovered_tmux_sessions(args)
        report = _scan_report(args)
        fingerprint = _report_fingerprint(report)
        report_changed = previous_fingerprint != fingerprint
        precomputed_auto_action: dict[str, Any] | None = None
        precomputed_executed: dict[str, Any] | None = None
        force_print = False
        if args.changes_only and not report_changed and args.auto_execute:
            precomputed_auto_action = _auto_execute_action(
                report,
                target_name=args.name,
                codex_home=Path(args.codex_home),
                prompt_cooldown_seconds=args.prompt_cooldown,
            )
            precomputed_executed = _execute_auto_action(
                args,
                report,
                precomputed_auto_action,
            )
            force_print = _executed_action_forces_print(precomputed_executed)
        should_print = (
            not args.changes_only
            or report_changed
            or force_print
            or bool(auto_adopted)
        )
        if should_print:
            payload = _supervise_payload(
                args,
                report,
                iteration=count + 1,
                auto_adopted=auto_adopted,
                precomputed_auto_action=precomputed_auto_action,
                precomputed_executed=precomputed_executed,
            )
            bell_fingerprint = _supervise_bell_fingerprint(report, payload)
            if (
                args.bell
                and bell_fingerprint is not None
                and bell_fingerprint != previous_bell_fingerprint
            ):
                _emit_terminal_bell()
            if args.json:
                _print_json(payload)
            else:
                _print_supervise_plain(payload, report)
            if iterations is not None and count + 1 < iterations:
                print()
            previous_bell_fingerprint = bell_fingerprint
        previous_fingerprint = fingerprint
        count += 1
        if iterations is None or count < iterations:
            _sleep(args.interval)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _auto_adopt_discovered_tmux_sessions(args: argparse.Namespace) -> list[dict[str, str]]:
    if not getattr(args, "auto_adopt", False):
        return []
    known_tmux = _known_managed_tmux_sessions(Path(args.codex_home))
    candidates = discover_tmux_adopt_candidates(
        cwd=Path.cwd(),
        include_all=False,
        run=subprocess.run,
    )
    adopted: list[dict[str, str]] = []
    for candidate in candidates:
        if candidate.tmux_session in known_tmux:
            continue
        record = adopt_tmux_session(
            codex_home=Path(args.codex_home),
            cwd=Path(candidate.cwd),
            name=candidate.suggested_name,
            tmux_session=candidate.tmux_session,
            run=subprocess.run,
        )
        known_tmux.add(candidate.tmux_session)
        adopted.append(
            {
                "name": record.name,
                "tmux_session": record.tmux_session or candidate.tmux_session,
                "cwd": record.cwd,
                "status": record.status,
            }
        )
    return adopted


def _known_managed_tmux_sessions(codex_home: Path) -> set[str]:
    return {
        record.tmux_session
        for record in read_managed_record_events(default_registry_path(codex_home))
        if record.tmux_session
    }


def _scan_report(args: argparse.Namespace) -> Any:
    needs_tmux_pane = (
        getattr(args, "command", None) == "dashboard"
        or bool(getattr(args, "auto_execute", False))
        or bool(getattr(args, "llm_action", False))
        or bool(getattr(args, "llm_execute", False))
    )
    command = getattr(args, "command", None)
    needs_bell_hook_health = command in {"scan", "dashboard", "watch"}
    flow = CodexSupervisorFlow(
        codex_home=Path(args.codex_home),
        tmux_bell_hook_checker=None
        if needs_bell_hook_health
        else _unknown_tmux_bell_hook,
        tmux_pane_reader=_tmux_capture_pane if needs_tmux_pane else None,
    )
    return flow.scan(
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )


def _unknown_tmux_bell_hook(_session: str) -> None:
    return None


def _guide_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    cwd = str(Path(args.cwd).expanduser())
    tmux_session = args.tmux_session or args.name
    commands = {
        "launch": shlex.join(
            [
                "isotope-supervisor",
                "launch",
                "--backend",
                "tmux",
                "--name",
                args.name,
                "--tmux-session",
                tmux_session,
                "--cwd",
                cwd,
                "--prompt",
                args.prompt,
            ]
        ),
        "adopt": shlex.join(
            [
                "isotope-supervisor",
                "adopt",
                "--name",
                args.name,
                "--cwd",
                cwd,
                "--tmux-session",
                tmux_session,
            ]
        ),
        "supervise": shlex.join(
            [
                "isotope-supervisor",
                "loop",
                "--interval",
                str(args.interval),
            ]
        ),
        "web": shlex.join(["isotope-supervisor", "web"]),
        "attach": shlex.join(["tmux", "attach", "-t", tmux_session]),
        "archive": shlex.join(["isotope-supervisor", "archive", "--name", args.name]),
    }
    return {
        "status": "ok",
        "workflow": {
            "cwd": cwd,
            "lane_name": args.name,
            "tmux_session": tmux_session,
            "prompt": args.prompt,
            "interval": args.interval,
        },
        "commands": commands,
    }


def _print_guide_plain(payload: dict[str, Any]) -> None:
    workflow = payload["workflow"]
    commands = payload["commands"]
    print("[Codex Supervisor 使用入口]")
    print(f"工作目录：{workflow['cwd']}")
    print(f"托管名：{workflow['lane_name']}")
    print(f"tmux：{workflow['tmux_session']}")
    print()
    print("1. 新开一个托管 Codex 窗口：")
    print(commands["launch"])
    print()
    print("2. 如果窗口已经存在，改用接管命令：")
    print(commands["adopt"])
    print()
    print("3. 启动自动监督循环：")
    print(commands["supervise"])
    print()
    print("4. 需要观察细节时：")
    print(commands["web"])
    print(commands["attach"])
    print()
    print("5. 窗口不用再跟进时归档：")
    print(commands["archive"])


def _discover_payload(args: argparse.Namespace) -> dict[str, Any]:
    cwd = str(Path(args.cwd).expanduser())
    candidates = discover_tmux_adopt_candidates(
        cwd=cwd,
        include_all=args.include_all,
        run=subprocess.run,
    )
    payload = {
        "status": "ok",
        "cwd": cwd,
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    selected = _selected_discover_candidate(args, candidates)
    if selected is None:
        return payload
    lane_name = args.name or selected.suggested_name
    record = adopt_tmux_session(
        codex_home=Path(args.codex_home),
        cwd=Path(selected.cwd),
        name=lane_name,
        tmux_session=selected.tmux_session,
        prompt=args.prompt,
        run=subprocess.run,
    )
    payload["adopted_candidate"] = selected.to_dict()
    payload["managed"] = record.to_dict()
    payload["next_commands"] = {
        "attach": selected.attach_command,
        "loop": "isotope-supervisor loop --interval 30",
        "archive": shlex.join(["isotope-supervisor", "archive", "--name", record.name]),
    }
    return payload


def _selected_discover_candidate(
    args: argparse.Namespace,
    candidates: tuple[Any, ...],
) -> Any | None:
    if args.adopt_index is not None and args.adopt_first:
        raise ValueError("adopt-index and adopt-first cannot be used together")
    if args.adopt_first:
        if not candidates:
            raise ValueError("no discover candidate to adopt")
        return candidates[0]
    if args.adopt_index is None:
        return None
    if args.adopt_index <= 0:
        raise ValueError("adopt-index must be positive")
    index = args.adopt_index - 1
    if index >= len(candidates):
        raise ValueError(
            f"adopt-index out of range: {args.adopt_index} > {len(candidates)}"
        )
    return candidates[index]


def _print_discover_plain(payload: dict[str, Any]) -> None:
    print("[Codex Supervisor tmux 发现]")
    print(f"工作目录：{payload['cwd']}")
    if managed := payload.get("managed"):
        candidate = payload["adopted_candidate"]
        print(f"已接管：{managed['name']} / tmux={candidate['tmux_session']}")
        next_commands = payload["next_commands"]
        print(f"打开：{next_commands['attach']}")
        print(f"监督：{next_commands['loop']}")
        print(f"归档：{next_commands['archive']}")
        return
    candidates = payload["candidates"]
    if not candidates:
        print("没有发现可接管的 Codex tmux 窗口。")
        return
    for index, item in enumerate(candidates, start=1):
        marker = "Codex" if item["looks_like_codex"] else "普通 tmux"
        print(
            f"{index}. {item['tmux_session']} / {marker} / 建议名：{item['suggested_name']}"
        )
        print(f"  接管：{item['adopt_command']}")
        print(f"  打开：{item['attach_command']}")


def _validate_execution_modes(args: argparse.Namespace) -> None:
    modes = [
        name
        for name, enabled in (
            ("execute", bool(args.execute)),
            ("auto_execute", bool(getattr(args, "auto_execute", False))),
            ("llm_execute", bool(args.llm_execute)),
        )
        if enabled
    ]
    if len(modes) > 1:
        raise ValueError("execute, auto_execute, and llm_execute cannot be used together")


def _supervise_payload(
    args: argparse.Namespace,
    report: Any,
    *,
    iteration: int,
    auto_adopted: list[dict[str, str]] | None = None,
    precomputed_auto_action: dict[str, Any] | None = None,
    precomputed_executed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _advice_payload(
        report,
        target_name=args.name,
        include_all_managed=args.llm_action or args.llm_execute,
    )
    payload["iteration"] = iteration
    payload["report"] = report.to_dict()
    payload["automation"] = _automation_status(report)
    payload["auto_adopted"] = auto_adopted or []
    if args.llm_summary:
        payload["llm_summary"] = _summarize_with_llm(report)
    if args.llm_action or args.llm_execute:
        payload["llm_action"] = _decide_action_with_llm(report, payload)
    if args.llm_execute:
        payload["executed"] = _execute_llm_action(args, report, payload)
    elif args.auto_execute:
        auto_action = precomputed_auto_action or _auto_execute_action(
            report,
            target_name=args.name,
            codex_home=Path(args.codex_home),
            prompt_cooldown_seconds=args.prompt_cooldown,
        )
        payload["auto_action"] = auto_action
        payload["executed"] = precomputed_executed or _execute_auto_action(
            args,
            report,
            auto_action,
        )
    elif args.execute:
        payload["executed"] = _execute_advice(args, report, payload)
    return payload


def _run_web(args: argparse.Namespace) -> None:
    if args.limit <= 0:
        raise ValueError("limit must be positive")
    if args.stale_after <= 0:
        raise ValueError("stale_after must be positive")
    if args.active_within <= 0:
        raise ValueError("active_within must be positive")
    if args.port < 0:
        raise ValueError("port must be zero or positive")
    url = f"http://{args.host}:{args.port}/"
    if args.print_url:
        print(url)
        return
    from .web import create_dashboard_server

    server = create_dashboard_server(
        codex_home=Path(args.codex_home),
        host=args.host,
        port=args.port,
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )
    actual_host, actual_port = server.server_address
    print(f"Codex Supervisor web: http://{actual_host}:{actual_port}/")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _print_dashboard(args: argparse.Namespace) -> None:
    report = _scan_report(args)
    payload = _dashboard_payload(report)
    if args.json:
        _print_json(payload)
        return
    _print_dashboard_plain(payload)


def _dashboard_payload(report: Any) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {
        "needs_attention": [],
        "done": [],
        "working": [],
    }
    for session, linked_session, linked_match in _dashboard_display_sessions(report.sessions):
        groups[_dashboard_group_for(session, linked_session=linked_session)].append(
            _dashboard_item(
                session,
                linked_session=linked_session,
                linked_match=linked_match,
            )
        )
    return {
        "status": "ok",
        "generated_at": report.generated_at,
        "recommendation": report.recommendation.to_dict(),
        "counts": {key: len(value) for key, value in groups.items()},
        "groups": groups,
    }


def _dashboard_group_for(session: Any, *, linked_session: Any | None = None) -> str:
    status_source = _dashboard_status_source(session, linked_session)
    supervisor_status = (status_source.supervisor_status or "").lower()
    if supervisor_status in {"blocked", "needs_user"}:
        return "needs_attention"
    if supervisor_status == "done":
        return "done"
    if status_source.status in {"needs_user", "error", "stale"}:
        return "needs_attention"
    if session.managed_bell:
        return "needs_attention"
    return "working"


def _dashboard_display_sessions(sessions: Any) -> list[tuple[Any, Any | None, dict[str, Any] | None]]:
    linkable_sessions: list[Any] = []
    for session in sessions:
        if session.managed:
            continue
        if session.status == "exited":
            continue
        linkable_sessions.append(session)

    managed_sessions = [
        session
        for session in sessions
        if session.managed and session.status != "exited"
    ]
    linked_by_managed_id = _best_linked_sessions_for_managed_lanes(
        managed_sessions,
        linkable_sessions,
    )
    consumed_linked_ids = {
        candidate.session_id
        for candidate, _match in linked_by_managed_id.values()
    }

    display_sessions: list[tuple[Any, Any | None, dict[str, Any] | None]] = []
    for session in sessions:
        if session.managed and session.status == "exited":
            continue
        if session.session_id in consumed_linked_ids:
            continue
        linked = linked_by_managed_id.get(session.session_id)
        linked_session = linked[0] if linked else None
        linked_match = linked[1] if linked else None
        display_sessions.append(
            (session, linked_session, linked_match)
        )
    return display_sessions


def _attention_bell_fingerprint(report: Any) -> tuple[object, ...] | None:
    recommendation = report.recommendation
    if recommendation.action == "monitor":
        return None
    return (
        recommendation.action,
        recommendation.priority,
        recommendation.target_session_id,
        recommendation.target_name,
    )


def _supervise_bell_fingerprint(
    report: Any, payload: dict[str, Any]
) -> tuple[object, ...] | None:
    executed = payload.get("executed")
    if not executed:
        return _attention_bell_fingerprint(report)
    if executed.get("kind") in EXECUTABLE_ADVICE_KINDS:
        return None
    if (
        executed.get("kind") == "monitor"
        and executed.get("reason") == "lane needs human attention"
    ):
        auto_action = payload.get("auto_action") or {}
        return (
            "supervise",
            executed.get("kind"),
            executed.get("reason"),
            auto_action.get("target_name"),
        )
    return None


def _emit_terminal_bell() -> None:
    sys.stderr.write("\a")
    sys.stderr.flush()


def _best_linked_sessions_for_managed_lanes(
    managed_sessions: list[Any],
    candidates: list[Any],
) -> dict[str, tuple[Any, dict[str, Any]]]:
    scored_pairs: list[tuple[int, int, int, Any, Any, dict[str, Any]]] = []
    for managed_index, managed_session in enumerate(managed_sessions):
        for candidate_index, candidate in enumerate(candidates):
            match = _managed_link_analysis(managed_session, candidate)
            score = match["score"]
            if score <= 0:
                continue
            scored_pairs.append(
                (score, managed_index, candidate_index, managed_session, candidate, match)
            )
    scored_pairs.sort(key=lambda item: (-item[0], item[1], item[2]))

    linked_by_managed_id: dict[str, tuple[Any, dict[str, Any]]] = {}
    consumed_linked_ids: set[str] = set()
    for (
        _score,
        _managed_index,
        _candidate_index,
        managed_session,
        candidate,
        match,
    ) in scored_pairs:
        if managed_session.session_id in linked_by_managed_id:
            continue
        if candidate.session_id in consumed_linked_ids:
            continue
        linked_by_managed_id[managed_session.session_id] = (candidate, match)
        consumed_linked_ids.add(candidate.session_id)
    return linked_by_managed_id


def _best_linked_session_for_managed(
    managed_session: Any,
    candidates: list[Any],
    consumed_linked_ids: set[str],
) -> Any | None:
    available = [
        candidate
        for candidate in candidates
        if candidate.session_id not in consumed_linked_ids
    ]
    if not available:
        return None
    scored = [
        (
            _managed_link_score(managed_session, candidate),
            index,
            candidate,
        )
        for index, candidate in enumerate(available)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score, _index, candidate = scored[0]
    return candidate if best_score > 0 else None


def _managed_link_score(managed_session: Any, candidate: Any) -> int:
    return _managed_link_analysis(managed_session, candidate)["score"]


def _managed_link_analysis(managed_session: Any, candidate: Any) -> dict[str, Any]:
    score = 0
    reasons: list[dict[str, Any]] = []
    raw_pane_text = getattr(managed_session, "managed_terminal_excerpt", None)
    pane_text = _normalize_match_text(raw_pane_text)
    active_pane_text = _active_terminal_match_text(raw_pane_text)
    active_scope = "active_terminal" if active_pane_text != pane_text else "terminal"

    def add_reason(kind: str, label: str, weight: int) -> None:
        nonlocal score
        score += weight
        reasons.append({"kind": kind, "label": label, "weight": weight})

    if _managed_prompt_matches_candidate(managed_session, candidate):
        add_reason("managed_prompt", "托管登记 prompt 命中真实 session", 320)
    if pane_text:
        if _text_contains(active_pane_text, getattr(candidate, "session_id", None)):
            add_reason("session_id", "活跃终端片段命中真实 session id", 40)
        thread_marker_matched = _candidate_thread_marker_matches(
            active_pane_text, candidate
        )
        if thread_marker_matched:
            add_reason("thread_marker", "活跃终端片段命中 Thread renamed 标题", 250)
        elif _candidate_text_matches(active_pane_text, candidate):
            add_reason("title_or_message", "活跃终端片段命中标题或最近消息", 40)
        if _candidate_snippet_matches(active_pane_text, candidate):
            add_reason("message_snippet", "活跃终端片段命中最近消息片段", 160)
    if getattr(managed_session, "managed_name", None):
        name_text = _normalize_match_text(managed_session.managed_name)
        if _candidate_text_matches(name_text, candidate):
            add_reason("managed_name", "托管名命中真实 session 标题或消息", 20)
    has_active_reason = any(
        reason["kind"]
        in {
            "session_id",
            "thread_marker",
            "title_or_message",
            "message_snippet",
        }
        for reason in reasons
    )
    has_managed_prompt_reason = any(
        reason["kind"] == "managed_prompt" for reason in reasons
    )
    if has_active_reason:
        scope = active_scope
    elif has_managed_prompt_reason:
        scope = "managed_prompt"
    else:
        scope = "managed_name"
    return {
        "score": score,
        "scope": scope,
        "reasons": reasons,
        "label": _linked_match_label(scope, reasons),
    }


def _linked_match_label(scope: str, reasons: list[dict[str, Any]]) -> str:
    if not reasons:
        return "无正分匹配"
    active_parts = [
        {
            "session_id": "真实 session id",
            "thread_marker": "Thread renamed 标题",
            "title_or_message": "标题或最近消息",
            "message_snippet": "最近消息片段",
        }[reason["kind"]]
        for reason in reasons
        if reason["kind"] in {
            "session_id",
            "thread_marker",
            "title_or_message",
            "message_snippet",
        }
    ]
    if active_parts:
        prefix = "活跃终端片段" if scope == "active_terminal" else "终端片段"
        return f"{prefix}命中 " + "、".join(active_parts)
    if any(reason["kind"] == "managed_prompt" for reason in reasons):
        return "托管登记 prompt 命中真实 session"
    return "托管名命中真实 session 标题或消息"


def _managed_prompt_matches_candidate(managed_session: Any, candidate: Any) -> bool:
    prompt = _normalize_match_text(getattr(managed_session, "last_user_message", None))
    if _is_generic_managed_prompt(prompt):
        return False
    for field in (
        getattr(candidate, "initial_user_title", None),
        getattr(candidate, "last_user_message", None),
        getattr(candidate, "thread_name", None),
    ):
        text = _normalize_match_text(field)
        if len(text) < 16:
            continue
        if prompt in text or text in prompt:
            return True
    return False


def _is_generic_managed_prompt(text: str) -> bool:
    return (
        len(text) < 16
        or text in {"接管已有 tmux 会话", "等待输入"}
        or _is_generic_supervisor_status_prompt(text)
    )


def _active_terminal_match_text(value: Any) -> str:
    text = _normalize_match_text(value)
    if not text:
        return ""
    marker_positions = [
        text.rfind(marker)
        for marker in (
            "thread renamed to",
            ">_ openai codex",
            "openai codex",
            "tip: use /copy",
        )
    ]
    start = max(marker_positions)
    return text[start:] if start >= 0 else text


def _candidate_thread_marker_matches(haystack: str, candidate: Any) -> bool:
    for field in (
        getattr(candidate, "thread_name", None),
        getattr(candidate, "initial_user_title", None),
    ):
        title = _normalize_match_text(field)
        if len(title) < 2:
            continue
        if f"thread renamed to {title}" in haystack:
            return True
        if f"codex resume '{title}'" in haystack:
            return True
        if f'codex resume "{title}"' in haystack:
            return True
    return False


def _candidate_snippet_matches(haystack: str, candidate: Any) -> bool:
    for field in (
        getattr(candidate, "initial_user_title", None),
        getattr(candidate, "last_user_message", None),
        getattr(candidate, "last_assistant_message", None),
    ):
        text = _normalize_match_text(field)
        if _is_generic_supervisor_status_prompt(text):
            continue
        if len(text) < 16:
            continue
        for snippet in (text[:32], text[-32:]):
            if _text_contains(haystack, snippet):
                return True
    return False


def _is_generic_supervisor_status_prompt(text: str) -> bool:
    return (
        "请汇报当前状态" in text
        and "supervisor_status" in text
        and "supervisor_summary" in text
    )


def _candidate_text_matches(haystack: str, candidate: Any) -> bool:
    fields = (
        getattr(candidate, "thread_name", None),
        getattr(candidate, "initial_user_title", None),
        getattr(candidate, "last_user_message", None),
        getattr(candidate, "last_assistant_message", None),
    )
    for field in fields:
        text = _normalize_match_text(field)
        if _is_generic_supervisor_status_prompt(text):
            continue
        if _text_contains_positive(haystack, text):
            return True
    return False


def _text_contains(haystack: str, value: Any) -> bool:
    needle = _normalize_match_text(value)
    return len(needle) >= 4 and needle in haystack


def _text_contains_positive(haystack: str, value: Any) -> bool:
    needle = _normalize_match_text(value)
    if len(needle) < 4 or needle not in haystack:
        return False
    negative_phrases = (
        f"不要继续 {needle}",
        f"不要再继续 {needle}",
        f"不继续 {needle}",
        f"别继续 {needle}",
    )
    return not any(phrase in haystack for phrase in negative_phrases)


def _normalize_match_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().split())


def _dashboard_item(
    session: Any,
    *,
    linked_session: Any | None = None,
    linked_match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    display_source = linked_session or session
    resume_session = linked_session or session
    status_source = _dashboard_status_source(session, linked_session)
    return {
        "session_id": session.session_id,
        "short_session_id": display_source.short_session_id,
        "display_title": display_source.display_title,
        "resume_command": f"codex resume {resume_session.session_id}",
        "linked_session_id": linked_session.session_id if linked_session else None,
        "linked_short_session_id": linked_session.short_session_id
        if linked_session
        else None,
        "linked_resume_command": f"codex resume {linked_session.session_id}"
        if linked_session
        else None,
        "linked_match": linked_match if linked_session else None,
        "managed_display_title": session.display_title if linked_session else None,
        "name": session.managed_name,
        "thread_name": display_source.thread_name,
        "thread_id": display_source.thread_id,
        "initial_user_title": display_source.initial_user_title,
        "agent_nickname": display_source.agent_nickname,
        "agent_role": display_source.agent_role,
        "cwd": session.cwd,
        "git_branch": display_source.git_branch or session.git_branch,
        "status": status_source.status,
        "status_label": status_source.status_label,
        "status_evidence": status_source.status_evidence,
        "supervisor_status": status_source.supervisor_status,
        "supervisor_summary": status_source.supervisor_summary,
        "supervisor_next": status_source.supervisor_next,
        "managed": session.managed,
        "managed_backend": session.managed_backend,
        "managed_tmux_session": session.managed_tmux_session,
        "managed_terminal_excerpt": session.managed_terminal_excerpt,
        "managed_terminal_ready": session.managed_terminal_ready,
        "managed_bell": session.managed_bell,
        "managed_bell_event_at": session.managed_bell_event_at,
        "managed_bell_hook_installed": session.managed_bell_hook_installed,
        "control_commands": _managed_tmux_command_suggestions(session)
        if session.managed_tmux_session
        else [],
        "reason": status_source.reason,
        "age_seconds": status_source.age_seconds,
    }


def _dashboard_status_source(session: Any, linked_session: Any | None) -> Any:
    if linked_session is not None and linked_session.supervisor_status:
        return linked_session
    return session


def _print_dashboard_plain(payload: dict[str, Any]) -> None:
    print("[Codex Supervisor dashboard]")
    print(f"生成时间：{payload['generated_at']}")
    print(f"建议：{payload['recommendation']['label']}")
    for group_key, label in DASHBOARD_GROUP_LABELS.items():
        items = payload["groups"][group_key]
        print(f"{label}：{len(items)}")
        for item in items:
            title = item["display_title"]
            status = item["status_label"]
            detail = item["supervisor_summary"] or item["reason"]
            suffix = _dashboard_item_suffix(item)
            print(f"- {title} {status} / {detail}{suffix}")
            if item["status_evidence"]:
                evidence = item["status_evidence"]
                print(f"  依据：{evidence['label']} - {evidence['detail']}")


def _dashboard_item_suffix(item: dict[str, Any]) -> str:
    parts: list[str] = []
    if item["git_branch"]:
        parts.append(f"分支={item['git_branch']}")
    if item["managed_tmux_session"]:
        parts.append(f"tmux={item['managed_tmux_session']}")
    if item["managed_bell_event_at"]:
        parts.append(f"bell={item['managed_bell_event_at']}")
    return f" ({', '.join(parts)})" if parts else ""


def _print_supervise_plain(payload: dict[str, Any], report: Any) -> None:
    print("[Codex Supervisor supervise]")
    _print_dashboard_plain(_dashboard_payload(report))
    automation = payload["automation"]
    print()
    print("[托管自动化]")
    print(automation["reason"])
    if auto_adopted := payload.get("auto_adopted"):
        for item in auto_adopted:
            print(
                f"自动接管：{item['name']} tmux={item['tmux_session']} cwd={item['cwd']}"
            )
    if not automation["ready"]:
        print(f"启动：{automation['launch_hint']}")
        print(f"接管：{automation['adopt_hint']}")
    if llm_summary := payload.get("llm_summary"):
        print()
        print("[LLM 摘要]")
        print(llm_summary)
    if llm_action := payload.get("llm_action"):
        print()
        print("[LLM 白名单动作]")
        print(f"{llm_action['kind']} / {llm_action['reason']}")
    if auto_action := payload.get("auto_action"):
        print()
        print("[自动策略]")
        print(f"{auto_action['kind']} / {auto_action['reason']}")
    recommendation = payload["recommendation"]
    print()
    print("[建议]")
    print(f"{recommendation['label']} action={recommendation['action']}")
    if executed := payload.get("executed"):
        _print_executed_plain(executed)


def _print_advice(args: argparse.Namespace) -> None:
    report = _scan_report(args)
    payload = _advice_payload(
        report,
        target_name=args.name,
        include_all_managed=args.llm_action or args.llm_execute,
    )
    if args.llm_action or args.llm_execute:
        payload["llm_action"] = _decide_action_with_llm(report, payload)
    if args.llm_execute:
        payload["executed"] = _execute_llm_action(args, report, payload)
    elif args.execute:
        payload["executed"] = _execute_advice(args, report, payload)
    if args.json:
        _print_json(payload)
        return
    recommendation = payload["recommendation"]
    command_suggestion = payload["command_suggestion"]
    print("[Codex Supervisor 建议]")
    print(f"建议：{recommendation['label']}")
    print(f"动作：{recommendation['action']}")
    print(f"优先级：{recommendation['priority']}")
    if recommendation["target_session_id"]:
        print(f"目标：{recommendation['target_session_id']}")
    if llm_action := payload.get("llm_action"):
        print(f"LLM 动作：{llm_action['kind']}")
        print(f"LLM 原因：{llm_action['reason']}")
    if command_suggestion is None:
        print("命令：暂无可安全生成的命令草案。")
    else:
        print(f"命令：{command_suggestion['command']}")
    if executed := payload.get("executed"):
        _print_executed_plain(executed)


def _automation_status(report: Any) -> dict[str, Any]:
    lanes = [session for session in report.sessions if _is_active_managed_tmux_session(session)]
    names = [session.managed_name for session in lanes if session.managed_name]
    if lanes:
        return {
            "ready": True,
            "managed_tmux_count": len(lanes),
            "managed_names": names,
            "reason": f"当前有 {len(lanes)} 个可控托管 tmux lane。",
            "launch_hint": LAUNCH_TMUX_HINT,
            "adopt_hint": ADOPT_TMUX_HINT,
        }
    return {
        "ready": False,
        "managed_tmux_count": 0,
        "managed_names": [],
        "reason": "当前没有可控的托管 tmux lane，自动发送不会生效。",
        "launch_hint": LAUNCH_TMUX_HINT,
        "adopt_hint": ADOPT_TMUX_HINT,
    }


def _advice_payload(
    report: Any,
    *,
    target_name: str | None = None,
    include_all_managed: bool = False,
) -> dict[str, Any]:
    recommendation = report.recommendation
    suggestions = _command_suggestions(
        report,
        target_name=target_name,
        include_all_managed=include_all_managed,
    )
    return {
        "status": "ok",
        "generated_at": report.generated_at,
        "recommendation": recommendation.to_dict(),
        "command_suggestion": suggestions[0] if suggestions else None,
        "command_suggestions": suggestions,
    }


def _print_executed_plain(executed: dict[str, Any]) -> None:
    if executed.get("skipped"):
        print(f"已跳过：{executed['reason']}")
        return
    print(f"已执行：{executed['command']}")


def _command_suggestions(
    report: Any,
    *,
    target_name: str | None = None,
    include_all_managed: bool = False,
) -> list[dict[str, str]]:
    if target_name:
        managed_tmux = _managed_tmux_session_by_name(report, target_name)
        if managed_tmux is not None:
            return _managed_tmux_command_suggestions(managed_tmux) + [
                _watch_command_suggestion()
            ]
        return [_watch_command_suggestion()]
    if include_all_managed:
        suggestions: list[dict[str, str]] = []
        for session in report.sessions:
            if _is_active_managed_tmux_session(session):
                suggestions.extend(_managed_tmux_command_suggestions(session))
        if suggestions:
            suggestions.append(_watch_command_suggestion())
            return suggestions
    recommendation = report.recommendation
    target = _target_session(report, recommendation.target_session_id)
    if target is not None and target.managed_tmux_session:
        return _managed_tmux_command_suggestions(target)
    managed_tmux = _first_managed_tmux_session(report)
    if managed_tmux is not None:
        return _managed_tmux_command_suggestions(managed_tmux) + [_watch_command_suggestion()]
    if recommendation.action == "monitor":
        return [_watch_command_suggestion()]
    return []


def _managed_tmux_command_suggestions(session: Any) -> list[dict[str, str]]:
    if not session.managed_name or not session.managed_tmux_session:
        return []
    return [
        {
            "kind": "tmux_attach",
            "label": "打开托管 tmux 窗口",
            "command": shlex.join(["tmux", "attach", "-t", session.managed_tmux_session]),
        },
        {
            "kind": "send_status",
            "label": "让托管 Codex 汇报状态",
            "command": shlex.join(
                [
                    "isotope-supervisor",
                    "send",
                    "--name",
                    session.managed_name,
                    "--text",
                    EXECUTABLE_ADVICE_TEXT["send_status"],
                ]
            ),
        },
        {
            "kind": "send_continue",
            "label": "让托管 Codex 继续推进",
            "command": shlex.join(
                [
                    "isotope-supervisor",
                    "send",
                    "--name",
                    session.managed_name,
                    "--text",
                    EXECUTABLE_ADVICE_TEXT["send_continue"],
                ]
            ),
        },
        {
            "kind": "archive",
            "label": "归档托管记录",
            "command": shlex.join(
                [
                    "isotope-supervisor",
                    "archive",
                    "--name",
                    session.managed_name,
                ]
            ),
        },
    ]


def _watch_command_suggestion() -> dict[str, str]:
    return {
        "kind": "watch_changes",
        "label": "继续监控变化",
        "command": "isotope-supervisor watch --interval 180 --changes-only",
    }


def _managed_tmux_session_by_name(report: Any, name: str) -> Any | None:
    for session in report.sessions:
        if _is_active_managed_tmux_session(session) and session.managed_name == name:
            return session
    return None


def _first_managed_tmux_session(report: Any) -> Any | None:
    for session in report.sessions:
        if _is_active_managed_tmux_session(session):
            return session
    return None


def _is_active_managed_tmux_session(session: Any) -> bool:
    return bool(session.managed_tmux_session) and session.status != "exited"


def _execute_advice(
    args: argparse.Namespace,
    report: Any,
    payload: dict[str, Any],
    *,
    kind: str | None = None,
    target_name: str | None = None,
) -> dict[str, Any]:
    kind = str(kind or args.execute)
    if kind not in EXECUTABLE_ADVICE_KINDS:
        supported = ", ".join(sorted(EXECUTABLE_ADVICE_KINDS))
        raise ValueError(f"execute supports only: {supported}")
    explicit_target_name = target_name or args.name
    if explicit_target_name:
        target = _managed_tmux_session_by_name(report, explicit_target_name)
        if target is None:
            raise ValueError(f"managed lane not found: {explicit_target_name}")
    else:
        target = _target_session(report, report.recommendation.target_session_id)
        if target is None or not target.managed_name:
            target = _first_managed_tmux_session(report)
    if target is None or not target.managed_name:
        target = _first_managed_tmux_session(report)
    if target is None or not target.managed_name:
        raise ValueError(f"no managed tmux target for: {kind}")
    suggestion = _suggestion_by_kind(_managed_tmux_command_suggestions(target), kind)
    if suggestion is None:
        raise ValueError(f"no generated command suggestion for: {kind}")
    if cooldown_state := prompt_cooldown_state(
        codex_home=Path(args.codex_home),
        name=target.managed_name,
        cooldown_seconds=args.prompt_cooldown,
    ):
        return {
            "kind": kind,
            "command": suggestion["command"],
            "skipped": True,
            "reason": "lane prompt cooldown active",
            "lane_state": cooldown_state.to_dict(),
        }
    result = send_to_managed_codex(
        codex_home=Path(args.codex_home),
        name=target.managed_name,
        text=EXECUTABLE_ADVICE_TEXT[kind],
        run=subprocess.run,
    )
    record_lane_prompt(
        codex_home=Path(args.codex_home),
        name=result.record.name,
        tmux_session=result.record.tmux_session,
        status=target.supervisor_status or target.status,
    )
    return {
        "kind": kind,
        "command": suggestion["command"],
        "text": result.text,
        "managed": {
            "name": result.record.name,
            "record_id": result.record.record_id,
            "tmux_session": result.record.tmux_session,
        },
    }


def _execute_llm_action(
    args: argparse.Namespace,
    report: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    action = payload["llm_action"]
    kind = action["kind"]
    if kind == "monitor":
        return {
            "kind": kind,
            "skipped": True,
            "reason": action["reason"],
        }
    return _execute_advice(
        args,
        report,
        payload,
        kind=kind,
        target_name=action.get("target_name"),
    )


def _execute_auto_action(
    args: argparse.Namespace,
    report: Any,
    auto_action: dict[str, Any],
) -> dict[str, Any]:
    if auto_action["kind"] in EXECUTABLE_ADVICE_KINDS:
        return _execute_advice(
            args,
            report,
            {},
            kind=auto_action["kind"],
            target_name=auto_action.get("target_name"),
        )
    return {
        "kind": auto_action["kind"],
        "skipped": True,
        "reason": auto_action["reason"],
    }


def _executed_action_forces_print(executed: dict[str, Any]) -> bool:
    return executed.get("kind") in EXECUTABLE_ADVICE_KINDS and not executed.get("skipped")


def _auto_execute_action(
    report: Any,
    *,
    target_name: str | None = None,
    codex_home: Path | None = None,
    prompt_cooldown_seconds: int = DEFAULT_PROMPT_COOLDOWN_SECONDS,
) -> dict[str, str]:
    if target_name:
        managed = _managed_tmux_session_by_name(report, target_name)
        if managed is None:
            return {
                "kind": "monitor",
                "reason": f"managed lane not found: {target_name}",
            }
        return _auto_execute_action_for_managed(report, managed)
    managed_lanes = [
        session for session in report.sessions if _is_active_managed_tmux_session(session)
    ]
    if not managed_lanes:
        return {
            "kind": "monitor",
            "reason": "no managed tmux lane",
        }
    include_target_name = len(managed_lanes) > 1
    candidates: list[tuple[dict[str, str], Any]] = []
    for managed in managed_lanes:
        action = _auto_execute_action_for_managed(report, managed)
        if include_target_name and managed.managed_name:
            action = {**action, "target_name": managed.managed_name}
        candidates.append((action, managed))
    cooldown_candidates: list[dict[str, str]] = []
    for action, managed in candidates:
        if action["kind"] not in EXECUTABLE_ADVICE_KINDS:
            continue
        if _auto_action_in_prompt_cooldown(
            codex_home=codex_home,
            managed=managed,
            prompt_cooldown_seconds=prompt_cooldown_seconds,
        ):
            cooldown_candidates.append(action)
            continue
        return action
    for action, _managed in candidates:
        if action["reason"] == "lane needs human attention":
            return action
    if cooldown_candidates:
        return cooldown_candidates[0]
    return candidates[0][0]


def _auto_action_in_prompt_cooldown(
    *,
    codex_home: Path | None,
    managed: Any,
    prompt_cooldown_seconds: int,
) -> bool:
    if codex_home is None or not managed.managed_name:
        return False
    return (
        prompt_cooldown_state(
            codex_home=codex_home,
            name=managed.managed_name,
            cooldown_seconds=prompt_cooldown_seconds,
        )
        is not None
    )


def _auto_execute_action_for_managed(report: Any, managed: Any) -> dict[str, str]:
    if _managed_terminal_looks_busy(managed):
        return {
            "kind": "monitor",
            "reason": "managed lane is running without ready signal",
        }
    status_source = _auto_status_source(report, managed)
    supervisor_status = (status_source.supervisor_status or "").lower()
    if supervisor_status in {"blocked", "needs_user"}:
        return {
            "kind": "monitor",
            "reason": "lane needs human attention",
        }
    if supervisor_status == "done":
        if _supervisor_next_marks_terminal_done(status_source):
            return {
                "kind": "monitor",
                "reason": "managed lane reported terminal done",
            }
        return {
            "kind": "send_continue",
            "reason": "managed lane reported done",
        }
    recommendation = report.recommendation
    target_ids = {managed.session_id, status_source.session_id}
    recommendation_targets_lane = recommendation.target_session_id in target_ids
    if (
        recommendation_targets_lane
        and recommendation.action in {"inspect_blocked", "review_user_prompt", "inspect_error"}
    ):
        return {
            "kind": "monitor",
            "reason": "lane needs human attention",
        }
    if recommendation_targets_lane and recommendation.action == "review_done":
        if _supervisor_next_marks_terminal_done(status_source):
            return {
                "kind": "monitor",
                "reason": "managed lane reported terminal done",
            }
        return {
            "kind": "send_continue",
            "reason": "managed lane reported done",
        }
    if status_source.managed_terminal_ready or managed.managed_terminal_ready:
        return {
            "kind": "send_status",
            "reason": "managed terminal is ready for input",
        }
    if (
        status_source.managed_bell
        or managed.managed_bell
        or status_source.status == "stale"
        or (
            recommendation_targets_lane
            and recommendation.action in {"inspect_bell", "inspect_stale"}
        )
    ):
        return {
            "kind": "send_status",
            "reason": f"recommendation is {recommendation.action}",
        }
    if not status_source.supervisor_status:
        return {
            "kind": "monitor",
            "reason": "managed lane is running without ready signal",
        }
    return {
        "kind": "monitor",
        "reason": "lane is still working",
    }


def _supervisor_next_marks_terminal_done(session: Any) -> bool:
    next_text = _normalize_match_text(getattr(session, "supervisor_next", None))
    return any(marker in next_text for marker in TERMINAL_DONE_NEXT_MARKERS)


def _managed_terminal_looks_busy(session: Any) -> bool:
    text = getattr(session, "managed_terminal_excerpt", None)
    if not isinstance(text, str):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return _terminal_has_active_work_marker(lines[-8:])


def _auto_status_source(report: Any, managed: Any) -> Any:
    candidates = [
        session
        for session in report.sessions
        if not session.managed
        and (session.status not in {"stale", "exited"} or session.supervisor_status)
    ]
    return _best_linked_session_for_managed(managed, candidates, set()) or managed


def _suggestion_by_kind(
    suggestions: list[dict[str, str]], kind: str
) -> dict[str, str] | None:
    for suggestion in suggestions:
        if suggestion["kind"] == kind:
            return suggestion
    return None


def _target_session(report: Any, session_id: str | None) -> Any | None:
    if session_id is None:
        return None
    for session in report.sessions:
        if session.session_id == session_id:
            return session
    return None


def _report_fingerprint(report: Any) -> tuple[object, ...]:
    """生成变化指纹；忽略生成时间和纯计时文案，避免空转被当作变化。"""
    return tuple(
        (
            session.session_id,
            session.cwd,
            session.git_branch,
            session.source_path,
            session.last_event_at,
            session.status,
            session.reason,
            _status_evidence_fingerprint(session.status_evidence),
            session.last_user_message,
            session.last_assistant_message,
            session.managed_bell,
            session.managed_bell_event_at,
            session.managed_bell_hook_installed,
            session.managed_terminal_ready,
            session.supervisor_status,
            session.supervisor_summary,
            session.supervisor_next,
        )
        for session in report.sessions
    )


def _status_evidence_fingerprint(
    evidence: dict[str, str] | None,
) -> tuple[str | None, str | None] | None:
    if evidence is None:
        return None
    return (evidence.get("source"), evidence.get("label"))


def _summarize_with_llm(report: Any) -> str:
    provider = resolve_summary_provider_from_env(agent_name="supervisor")
    return generate_llm_summary(report, provider)


def _decide_action_with_llm(report: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if not _has_llm_action_target(report):
        return generate_llm_action_decision(
            report,
            payload["command_suggestions"],
            _UnavailableSummaryProvider(),
        )
    provider = resolve_summary_provider_from_env(agent_name="supervisor")
    return generate_llm_action_decision(report, payload["command_suggestions"], provider)


class _UnavailableSummaryProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        raise AssertionError("LLM provider should not be called without managed targets")


def _has_llm_action_target(report: Any) -> bool:
    return any(
        session.managed_name and session.managed_tmux_session
        for session in report.sessions
    )


if __name__ == "__main__":
    raise SystemExit(main())
