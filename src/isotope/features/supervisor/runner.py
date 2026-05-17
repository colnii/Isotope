"""CLI runner for the read-only Codex supervisor."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from .flow import CodexSupervisorFlow, _tmux_capture_pane, render_plain_report
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
from .registry import adopt_tmux_session, launch_managed_codex, send_to_managed_codex

EXECUTABLE_ADVICE_KINDS = {"send_status", "send_continue"}
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
            "--execute",
            help="Execute one generated send suggestion. Supports send_status or send_continue.",
        )
        subparsers.choices[command].add_argument(
            "--llm-action",
            action="store_true",
            help="Ask configured LLM to choose one whitelist action without executing it.",
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
    subparsers.choices["supervise"].add_argument(
        "--auto-execute",
        action="store_true",
        help="Use the rule-based auto policy to execute one whitelist action per loop.",
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
        if args.command == "dashboard":
            _print_dashboard(args)
            return 0
        if args.command == "advise":
            _print_advice(args)
            return 0
        if args.command == "supervise":
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


def _run_supervise(args: argparse.Namespace) -> None:
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    if args.iterations is not None and args.iterations <= 0:
        raise ValueError("iterations must be positive")
    if args.execute and args.auto_execute:
        raise ValueError("execute and auto_execute cannot be used together")
    iterations = args.iterations
    count = 0
    previous_fingerprint: tuple[object, ...] | None = None
    while iterations is None or count < iterations:
        report = _scan_report(args)
        fingerprint = _report_fingerprint(report)
        should_print = not args.changes_only or previous_fingerprint != fingerprint
        if should_print:
            payload = _supervise_payload(args, report, iteration=count + 1)
            if args.json:
                _print_json(payload)
            else:
                _print_supervise_plain(payload, report)
            if iterations is not None and count + 1 < iterations:
                print()
        previous_fingerprint = fingerprint
        count += 1
        if iterations is None or count < iterations:
            time.sleep(args.interval)


def _scan_report(args: argparse.Namespace) -> Any:
    needs_tmux_pane = getattr(args, "command", None) == "dashboard" or bool(
        getattr(args, "auto_execute", False)
    )
    flow = CodexSupervisorFlow(
        codex_home=Path(args.codex_home),
        tmux_pane_reader=_tmux_capture_pane if needs_tmux_pane else None,
    )
    return flow.scan(
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )


def _supervise_payload(
    args: argparse.Namespace,
    report: Any,
    *,
    iteration: int,
) -> dict[str, Any]:
    payload = _advice_payload(report)
    payload["iteration"] = iteration
    payload["report"] = report.to_dict()
    if args.llm_summary:
        payload["llm_summary"] = _summarize_with_llm(report)
    if args.llm_action:
        payload["llm_action"] = _decide_action_with_llm(report, payload)
    if args.auto_execute:
        auto_action = _auto_execute_action(report)
        payload["auto_action"] = auto_action
        if auto_action["kind"] in EXECUTABLE_ADVICE_KINDS:
            payload["executed"] = _execute_advice(args, report, payload, kind=auto_action["kind"])
        else:
            payload["executed"] = {
                "kind": auto_action["kind"],
                "skipped": True,
                "reason": auto_action["reason"],
            }
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
    for session, linked_session in _dashboard_display_sessions(report.sessions):
        groups[_dashboard_group_for(session, linked_session=linked_session)].append(
            _dashboard_item(session, linked_session=linked_session)
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


def _dashboard_display_sessions(sessions: Any) -> list[tuple[Any, Any | None]]:
    linkable_sessions: list[Any] = []
    for session in sessions:
        if session.managed:
            continue
        if session.status == "exited":
            continue
        if session.status == "stale" and not session.supervisor_status:
            continue
        linkable_sessions.append(session)

    managed_sessions = [session for session in sessions if session.managed]
    linked_by_managed_id = _best_linked_sessions_for_managed_lanes(
        managed_sessions,
        linkable_sessions,
    )
    consumed_linked_ids = {
        candidate.session_id for candidate in linked_by_managed_id.values()
    }

    display_sessions: list[tuple[Any, Any | None]] = []
    for session in sessions:
        if session.session_id in consumed_linked_ids:
            continue
        display_sessions.append(
            (session, linked_by_managed_id.get(session.session_id))
        )
    return display_sessions


def _best_linked_sessions_for_managed_lanes(
    managed_sessions: list[Any],
    candidates: list[Any],
) -> dict[str, Any]:
    scored_pairs: list[tuple[int, int, int, Any, Any]] = []
    for managed_index, managed_session in enumerate(managed_sessions):
        for candidate_index, candidate in enumerate(candidates):
            score = _managed_link_score(managed_session, candidate)
            if score <= 0:
                continue
            scored_pairs.append(
                (score, managed_index, candidate_index, managed_session, candidate)
            )
    scored_pairs.sort(key=lambda item: (-item[0], item[1], item[2]))

    linked_by_managed_id: dict[str, Any] = {}
    consumed_linked_ids: set[str] = set()
    for _score, _managed_index, _candidate_index, managed_session, candidate in scored_pairs:
        if managed_session.session_id in linked_by_managed_id:
            continue
        if candidate.session_id in consumed_linked_ids:
            continue
        linked_by_managed_id[managed_session.session_id] = candidate
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
    score = 0
    pane_text = _normalize_match_text(
        getattr(managed_session, "managed_terminal_excerpt", None)
    )
    if pane_text:
        if _text_contains(pane_text, getattr(candidate, "session_id", None)):
            score += 300
        if _candidate_text_matches(pane_text, candidate):
            score += 100
    if getattr(managed_session, "managed_name", None):
        name_text = _normalize_match_text(managed_session.managed_name)
        if _candidate_text_matches(name_text, candidate):
            score += 20
    return score


def _candidate_text_matches(haystack: str, candidate: Any) -> bool:
    fields = (
        getattr(candidate, "thread_name", None),
        getattr(candidate, "initial_user_title", None),
        getattr(candidate, "last_user_message", None),
        getattr(candidate, "last_assistant_message", None),
    )
    return any(_text_contains(haystack, field) for field in fields)


def _text_contains(haystack: str, value: Any) -> bool:
    needle = _normalize_match_text(value)
    return len(needle) >= 4 and needle in haystack


def _normalize_match_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().split())


def _dashboard_item(session: Any, *, linked_session: Any | None = None) -> dict[str, Any]:
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
        "managed_bell": session.managed_bell,
        "managed_bell_event_at": session.managed_bell_event_at,
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
            status = item["supervisor_status"] or item["status_label"]
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
    print(render_plain_report(report))
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
    payload = _advice_payload(report)
    if args.llm_action:
        payload["llm_action"] = _decide_action_with_llm(report, payload)
    if args.execute:
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


def _advice_payload(report: Any) -> dict[str, Any]:
    recommendation = report.recommendation
    suggestions = _command_suggestions(report)
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


def _command_suggestions(report: Any) -> list[dict[str, str]]:
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
    ]


def _watch_command_suggestion() -> dict[str, str]:
    return {
        "kind": "watch_changes",
        "label": "继续监控变化",
        "command": "isotope-supervisor watch --interval 180 --changes-only",
    }


def _first_managed_tmux_session(report: Any) -> Any | None:
    for session in report.sessions:
        if session.managed_tmux_session:
            return session
    return None


def _execute_advice(
    args: argparse.Namespace,
    report: Any,
    payload: dict[str, Any],
    *,
    kind: str | None = None,
) -> dict[str, Any]:
    kind = str(kind or args.execute)
    if kind not in EXECUTABLE_ADVICE_KINDS:
        supported = ", ".join(sorted(EXECUTABLE_ADVICE_KINDS))
        raise ValueError(f"execute supports only: {supported}")
    suggestion = _suggestion_by_kind(payload["command_suggestions"], kind)
    if suggestion is None:
        raise ValueError(f"no generated command suggestion for: {kind}")
    target = _target_session(report, report.recommendation.target_session_id)
    if target is None or not target.managed_name:
        target = _first_managed_tmux_session(report)
    if target is None or not target.managed_name:
        raise ValueError(f"no managed tmux target for: {kind}")
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


def _auto_execute_action(report: Any) -> dict[str, str]:
    managed = _first_managed_tmux_session(report)
    if managed is None:
        return {
            "kind": "monitor",
            "reason": "no managed tmux lane",
        }
    status_source = _auto_status_source(report, managed)
    supervisor_status = (status_source.supervisor_status or "").lower()
    if supervisor_status in {"blocked", "needs_user"}:
        return {
            "kind": "monitor",
            "reason": "lane needs human attention",
        }
    if supervisor_status == "done":
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
        return {
            "kind": "send_continue",
            "reason": "managed lane reported done",
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
            "kind": "send_status",
            "reason": "managed lane has no supervisor status protocol yet",
        }
    return {
        "kind": "monitor",
        "reason": "lane is still working",
    }


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
            session.status_evidence,
            session.last_user_message,
            session.last_assistant_message,
            session.managed_bell,
            session.managed_bell_event_at,
            session.supervisor_status,
            session.supervisor_summary,
            session.supervisor_next,
        )
        for session in report.sessions
    )


def _summarize_with_llm(report: Any) -> str:
    provider = resolve_summary_provider_from_env(agent_name="supervisor")
    return generate_llm_summary(report, provider)


def _decide_action_with_llm(report: Any, payload: dict[str, Any]) -> dict[str, Any]:
    provider = resolve_summary_provider_from_env(agent_name="supervisor")
    return generate_llm_action_decision(report, payload["command_suggestions"], provider)


if __name__ == "__main__":
    raise SystemExit(main())
