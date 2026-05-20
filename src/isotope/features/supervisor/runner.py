"""CLI runner for the read-only Codex supervisor."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from isotope.features.notifications.flow import NotificationFlow

from .daemon import (
    run_supervisor_watcher,
    start_supervisor_daemon,
    start_supervisor_watcher,
    stop_supervisor_daemon,
    stop_supervisor_watcher,
    supervisor_daemon_status,
    supervisor_watcher_status,
    watchdog_supervisor_daemon,
)
from .context import (
    read_recent_context_results,
    request_project_context,
)
from .current_batch import build_current_batch_view
from .decision_requests import (
    archive_decision_request,
    read_active_decision_requests,
    read_recent_decision_answers,
    record_decision_answer,
    record_decision_request,
)
from .flow import (
    CodexSupervisorReport,
    CodexSupervisorFlow,
    _managed_process_log_excerpt,
    _pid_is_running,
    _supervisor_protocol_from_text,
    _terminal_has_active_work_marker,
    _tmux_capture_pane,
    render_plain_report,
)
from .fanout import DEFAULT_FANOUT_LIMIT, build_fanout_launch_plan
from .goal_queue import (
    archive_supervisor_goal,
    read_latest_supervisor_goal_statuses,
    read_active_supervisor_goals,
    record_supervisor_goal,
    record_supervisor_goal_status,
)
from .goal_planner import plan_supervisor_goals
from .integration_review import (
    collect_integration_reviews,
    render_integration_review_plain,
)
from .lane_state import (
    DEFAULT_MAX_CONTINUE_COUNT,
    DEFAULT_PROMPT_COOLDOWN_SECONDS,
    continue_budget_state,
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
    read_managed_records,
    read_managed_record_events,
    repair_tmux_bell_hooks,
    resume_managed_codex,
    send_to_managed_codex,
)
from .replan import build_supervisor_replan, render_supervisor_replan_plain
from .tmux_discovery import discover_tmux_adopt_candidates
from .worker_review import collect_worker_reviews, render_worker_review_plain
from .work_order_builder import build_launch_work_order_prompt

EXECUTABLE_ADVICE_KINDS = {"send_status", "send_continue"}
DEFAULT_MAX_CONTEXT_REQUESTS = 0
DEFAULT_MAX_RUN_MINUTES = 0
DEFAULT_WORKER_CODEX_MODEL = "gpt-5.5"
DEFAULT_WORKER_CODEX_CONFIG = ('model_reasoning_effort="high"',)
DEFAULT_WORKER_PROFILE = "coding"
WORKER_PROFILE_DEFAULTS = {
    "coding": {
        "model": DEFAULT_WORKER_CODEX_MODEL,
        "config": DEFAULT_WORKER_CODEX_CONFIG,
    },
    "light": {
        "model": DEFAULT_WORKER_CODEX_MODEL,
        "config": ('model_reasoning_effort="low"',),
    },
}
WORKER_PROFILE_CHOICES = tuple(WORKER_PROFILE_DEFAULTS)
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
LAUNCH_PROCESS_HINT = (
    "isotope-supervisor launch --name <name> --cwd <repo> --prompt '<task>'"
)
ADOPT_TMUX_HINT = (
    "isotope-supervisor adopt --name <name> --cwd <repo> --tmux-session <session>"
)
DEFAULT_CONTEXT_QUERY = "Supervisor 当前状态 下一步开发方向 AGENTS.md docs/current/status.md"
DEFAULT_LAUNCH_PROMPT = " ".join(
    [
        "请阅读 AGENTS.md 和 docs/current/status.md，",
        "根据当前项目状态自行判断并继续推进 Supervisor 下一步。",
        "不要停下来等待用户发号施令；只有满足拍板条件才请求用户确认。",
        "完成或遇到阻塞后，严格输出三行：",
        "第一行 `SUPERVISOR_STATUS: working|done|blocked|needs_user`；",
        "第二行 `SUPERVISOR_SUMMARY: 用一句中文说明当前进展`；",
        "第三行 `SUPERVISOR_NEXT: 用一句中文说明建议下一步`。",
    ]
)
IDLE_LOOP_REASON = "当前没有可控的 Supervisor 目标，先继续监控。"
DASHBOARD_GROUP_LABELS = {
    "needs_attention": "需要看",
    "done": "已完成",
    "working": "工作中",
}
ARCHIVABLE_SUPERVISOR_STATUSES = {"done"}


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
        subparser.add_argument(
            "--workspace-root",
            help="Limit LLM/action candidates to this workspace. Defaults to cwd.",
        )
        subparser.add_argument(
            "--all-workspaces",
            action="store_true",
            help="Let LLM/action candidates span every discovered workspace.",
        )
    for command in ("advise", "supervise"):
        subparsers.choices[command].add_argument(
            "--name",
            help="Target one managed lane by name for suggestions or execution.",
        )
        subparsers.choices[command].add_argument(
            "--goal",
            help="User goal for the LLM planner when it may need to launch a new worker.",
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
        subparsers.choices[command].add_argument(
            "--max-continue-count",
            type=int,
            default=DEFAULT_MAX_CONTINUE_COUNT,
            help="Maximum consecutive send_continue prompts for the same lane status. Default 0 disables.",
        )
        subparsers.choices[command].add_argument(
            "--max-context-requests",
            type=int,
            default=DEFAULT_MAX_CONTEXT_REQUESTS,
            help="Maximum request_context executions per supervise iteration. Default 0 disables.",
        )
        subparsers.choices[command].add_argument(
            "--max-run-minutes",
            type=int,
            default=DEFAULT_MAX_RUN_MINUTES,
            help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
        )
        subparsers.choices[command].add_argument(
            "--max-fanout-launches",
            type=int,
            default=DEFAULT_FANOUT_LIMIT,
            help="Maximum launch_session actions fanout may execute in one iteration.",
        )
        subparsers.choices[command].add_argument(
            "--worker-profile",
            choices=WORKER_PROFILE_CHOICES,
            default=DEFAULT_WORKER_PROFILE,
            help="Worker profile for launched Codex workers.",
        )
        subparsers.choices[command].add_argument(
            "--worker-codex-model",
            help="Pass -m/--model to Codex workers launched by LLM execution.",
        )
        subparsers.choices[command].add_argument(
            "--worker-codex-config",
            action="append",
            default=None,
            help="Pass one -c key=value override to Codex workers. Repeatable.",
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
        "--workspace-root",
        help="Limit LLM/action candidates to this workspace. Defaults to cwd.",
    )
    loop_parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Let LLM/action candidates span every discovered workspace.",
    )
    loop_parser.add_argument(
        "--name",
        help="Target one managed lane by name. Omit to rotate across active lanes.",
    )
    loop_parser.add_argument(
        "--goal",
        help="User goal for the LLM planner when it may need to launch a new worker.",
    )
    loop_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating send_status/send_continue for the same lane.",
    )
    loop_parser.add_argument(
        "--max-continue-count",
        type=int,
        default=DEFAULT_MAX_CONTINUE_COUNT,
        help="Maximum consecutive send_continue prompts for the same lane status. Default 0 disables.",
    )
    loop_parser.add_argument(
        "--max-context-requests",
        type=int,
        default=DEFAULT_MAX_CONTEXT_REQUESTS,
        help="Maximum request_context executions per loop iteration. Default 0 disables.",
    )
    loop_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
    )
    loop_parser.add_argument(
        "--max-fanout-launches",
        type=int,
        default=DEFAULT_FANOUT_LIMIT,
        help="Maximum launch_session actions fanout may execute in one loop iteration.",
    )
    loop_parser.add_argument(
        "--worker-profile",
        choices=WORKER_PROFILE_CHOICES,
        default=DEFAULT_WORKER_PROFILE,
        help="Worker profile for Codex workers launched by the loop.",
    )
    loop_parser.add_argument(
        "--worker-codex-model",
        help="Pass -m/--model to Codex workers launched by the loop.",
    )
    loop_parser.add_argument(
        "--worker-codex-config",
        action="append",
        default=None,
        help="Pass one -c key=value override to Codex workers. Repeatable.",
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
    loop_parser.add_argument(
        "--rule-execute",
        action="store_true",
        help="Use the old rule-based executor instead of the LLM planner.",
    )
    loop_parser.set_defaults(
        auto_execute=False,
        auto_adopt=True,
        changes_only=True,
        bell=True,
        execute=None,
        llm_action=False,
        llm_execute=True,
    )
    up_parser = subparsers.add_parser(
        "up",
        help="Start the daily Supervisor daemon if needed, then print status.",
    )
    up_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    up_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum sessions.",
    )
    up_parser.add_argument(
        "--stale-after",
        type=int,
        default=600,
        help="Seconds without events before marking a session stale.",
    )
    up_parser.add_argument(
        "--active-within",
        type=int,
        default=180,
        help="Seconds with recent events before marking a session working.",
    )
    up_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between loop reports.",
    )
    up_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating send_status/send_continue for the same lane.",
    )
    up_parser.add_argument(
        "--max-continue-count",
        type=int,
        default=DEFAULT_MAX_CONTINUE_COUNT,
        help="Maximum consecutive send_continue prompts for the same lane status. Default 0 disables.",
    )
    up_parser.add_argument(
        "--max-context-requests",
        type=int,
        default=DEFAULT_MAX_CONTEXT_REQUESTS,
        help="Maximum request_context executions per loop iteration. Default 0 disables.",
    )
    up_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
    )
    up_parser.add_argument(
        "--worker-profile",
        choices=WORKER_PROFILE_CHOICES,
        default=DEFAULT_WORKER_PROFILE,
        help="Worker profile for Codex workers launched by the daemon loop.",
    )
    up_parser.add_argument(
        "--worker-codex-model",
        help="Pass -m/--model to Codex workers launched by the daemon loop.",
    )
    up_parser.add_argument(
        "--worker-codex-config",
        action="append",
        default=None,
        help="Pass one -c key=value override to Codex workers. Repeatable.",
    )
    up_parser.add_argument(
        "--name",
        help="Target one managed lane. Omit to rotate across active lanes.",
    )
    up_parser.add_argument(
        "--goal",
        help="User goal for the LLM planner when it may need to launch a new worker.",
    )
    up_parser.add_argument(
        "--llm-summary",
        action="store_true",
        help="Use configured LLM to add a compact Chinese summary.",
    )
    up_parser.add_argument(
        "--no-auto-adopt",
        action="store_false",
        dest="auto_adopt",
        help="Disable automatic adoption of discovered Codex-like tmux sessions.",
    )
    up_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    up_parser.set_defaults(auto_adopt=True)
    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Start, inspect, or stop the background Supervisor loop.",
    )
    daemon_subparsers = daemon_parser.add_subparsers(
        dest="daemon_command",
        required=True,
    )
    daemon_start_parser = daemon_subparsers.add_parser(
        "start",
        help="Start the Supervisor loop in the background.",
    )
    daemon_start_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    daemon_start_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum sessions.",
    )
    daemon_start_parser.add_argument(
        "--stale-after",
        type=int,
        default=600,
        help="Seconds without events before marking a session stale.",
    )
    daemon_start_parser.add_argument(
        "--active-within",
        type=int,
        default=180,
        help="Seconds with recent events before marking a session working.",
    )
    daemon_start_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between loop reports.",
    )
    daemon_start_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating send_status/send_continue for the same lane.",
    )
    daemon_start_parser.add_argument(
        "--max-continue-count",
        type=int,
        default=DEFAULT_MAX_CONTINUE_COUNT,
        help="Maximum consecutive send_continue prompts for the same lane status. Default 0 disables.",
    )
    daemon_start_parser.add_argument(
        "--max-context-requests",
        type=int,
        default=DEFAULT_MAX_CONTEXT_REQUESTS,
        help="Maximum request_context executions per loop iteration. Default 0 disables.",
    )
    daemon_start_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
    )
    daemon_start_parser.add_argument(
        "--worker-profile",
        choices=WORKER_PROFILE_CHOICES,
        default=DEFAULT_WORKER_PROFILE,
        help="Worker profile for Codex workers launched by the daemon loop.",
    )
    daemon_start_parser.add_argument(
        "--worker-codex-model",
        help="Pass -m/--model to Codex workers launched by the daemon loop.",
    )
    daemon_start_parser.add_argument(
        "--worker-codex-config",
        action="append",
        default=None,
        help="Pass one -c key=value override to Codex workers. Repeatable.",
    )
    daemon_start_parser.add_argument(
        "--name",
        help="Target one managed lane. Omit to rotate across active lanes.",
    )
    daemon_start_parser.add_argument(
        "--goal",
        help="User goal for the LLM planner when it may need to launch a new worker.",
    )
    daemon_start_parser.add_argument(
        "--llm-summary",
        action="store_true",
        help="Use configured LLM to add a compact Chinese summary.",
    )
    daemon_start_parser.add_argument(
        "--no-auto-adopt",
        action="store_false",
        dest="auto_adopt",
        help="Disable automatic adoption of discovered Codex-like tmux sessions.",
    )
    daemon_start_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    daemon_start_parser.set_defaults(auto_adopt=True)
    for daemon_command in ("status", "stop", "watchdog"):
        daemon_command_parser = daemon_subparsers.add_parser(
            daemon_command,
            help=f"{daemon_command.title()} the background Supervisor loop.",
        )
        daemon_command_parser.add_argument(
            "--codex-home",
            default=str(Path.home() / ".codex"),
            help="Codex home directory. Defaults to ~/.codex.",
        )
        daemon_command_parser.add_argument(
            "--json",
            action="store_true",
            help="Print JSON output.",
        )
    watcher_parser = daemon_subparsers.add_parser(
        "watcher",
        help="Manage the background periodic watchdog.",
    )
    watcher_subparsers = watcher_parser.add_subparsers(
        dest="watcher_command",
        required=True,
    )
    watcher_start_parser = watcher_subparsers.add_parser(
        "start",
        help="Start the periodic watchdog in the background.",
    )
    watcher_start_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    watcher_start_parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between watchdog checks.",
    )
    watcher_start_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    watcher_run_parser = watcher_subparsers.add_parser(
        "run",
        help="Run watchdog checks in the foreground.",
    )
    watcher_run_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    watcher_run_parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between watchdog checks.",
    )
    watcher_run_parser.add_argument(
        "--iterations",
        type=int,
        help="Stop after this many checks. Omit to run until interrupted.",
    )
    watcher_run_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    for watcher_command in ("status", "stop"):
        watcher_command_parser = watcher_subparsers.add_parser(
            watcher_command,
            help=f"{watcher_command.title()} the periodic watchdog.",
        )
        watcher_command_parser.add_argument(
            "--codex-home",
            default=str(Path.home() / ".codex"),
            help="Codex home directory. Defaults to ~/.codex.",
        )
        watcher_command_parser.add_argument(
            "--json",
            action="store_true",
            help="Print JSON output.",
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
        "--codex-model",
        help="Pass -m/--model to the launched Codex worker.",
    )
    launch_parser.add_argument(
        "--codex-config",
        action="append",
        default=[],
        help="Pass one -c key=value override to the launched Codex worker. Repeatable.",
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
    worker_review_parser = subparsers.add_parser(
        "worker-review",
        help="Summarize Supervisor-managed workers for human review.",
    )
    worker_review_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    worker_review_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    integration_review_parser = subparsers.add_parser(
        "integration-review",
        help="Group managed workers by read-only integration readiness.",
    )
    integration_review_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    integration_review_parser.add_argument(
        "--base",
        default="main",
        help="Base branch/ref to check containment against. Defaults to main.",
    )
    integration_review_parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Also include non-done managed workers. Defaults to integration-ready done workers only.",
    )
    integration_review_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    replan_parser = subparsers.add_parser(
        "replan",
        help="Build read-only next-round advice from worker-review candidates.",
    )
    replan_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    replan_parser.add_argument(
        "--base",
        default="main",
        help="Base branch/ref to check integration readiness against. Defaults to main.",
    )
    replan_parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Also include non-done workers in the integration-review input.",
    )
    replan_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    context_parser = subparsers.add_parser(
        "context",
        help="Search project context and record the result for the LLM planner.",
    )
    context_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    context_parser.add_argument("--cwd", required=True, help="Workspace directory.")
    context_parser.add_argument("--query", required=True, help="Context search query.")
    context_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum context snippets.",
    )
    context_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    decision_parser = subparsers.add_parser(
        "decision",
        help="List or archive Supervisor decision requests.",
    )
    decision_subparsers = decision_parser.add_subparsers(
        dest="decision_command",
        required=True,
    )
    for decision_command, help_text in (
        ("list", "List active decision requests."),
        ("archive", "Archive one handled decision request."),
        ("answer", "Record a user answer for one decision request."),
    ):
        command_parser = decision_subparsers.add_parser(
            decision_command,
            help=help_text,
        )
        command_parser.add_argument(
            "--codex-home",
            default=str(Path.home() / ".codex"),
            help="Codex home directory. Defaults to ~/.codex.",
        )
        command_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    decision_subparsers.choices["archive"].add_argument(
        "--request-id",
        required=True,
        help="Decision request id to archive.",
    )
    decision_subparsers.choices["answer"].add_argument(
        "--request-id",
        required=True,
        help="Decision request id to answer.",
    )
    decision_subparsers.choices["answer"].add_argument(
        "--answer",
        required=True,
        help="User decision answer.",
    )
    goal_parser = subparsers.add_parser(
        "goal",
        help="Add, list, or archive persistent Supervisor goals.",
    )
    goal_subparsers = goal_parser.add_subparsers(
        dest="goal_command",
        required=True,
    )
    goal_add_parser = goal_subparsers.add_parser(
        "add",
        help="Add one persistent goal for the Supervisor loop.",
    )
    goal_add_parser.add_argument(
        "goal_text",
        nargs="?",
        help="Goal text. Positional form for one-sentence goal entry.",
    )
    goal_add_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    goal_add_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory for this goal. Defaults to the current directory.",
    )
    goal_add_parser.add_argument("--goal", help="Goal text. Kept for compatibility.")
    goal_add_parser.add_argument(
        "--target-name",
        help="Preferred managed worker name. Defaults to the generated goal id.",
    )
    goal_add_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    goal_plan_parser = goal_subparsers.add_parser(
        "plan",
        help="Use LLM to propose a small batch of Supervisor goals.",
    )
    goal_plan_parser.add_argument(
        "goal_text",
        nargs="?",
        help="Optional high-level user goal to seed planning.",
    )
    goal_plan_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    goal_plan_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory whose current docs seed planning.",
    )
    goal_plan_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum goal candidates to return or write.",
    )
    goal_plan_parser.add_argument(
        "--write",
        action="store_true",
        help="Write generated candidates into the persistent goal queue.",
    )
    goal_plan_parser.add_argument(
        "--fanout-execute",
        action="store_true",
        help="After --write, execute parallel_recommendations as controlled launch_session actions.",
    )
    goal_plan_parser.add_argument(
        "--max-fanout-launches",
        type=int,
        default=DEFAULT_FANOUT_LIMIT,
        help="Maximum launch_session actions fanout may execute for this plan.",
    )
    goal_plan_parser.add_argument(
        "--prompt-cooldown",
        type=int,
        default=DEFAULT_PROMPT_COOLDOWN_SECONDS,
        help="Seconds before repeating launch_session for the same lane.",
    )
    goal_plan_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before launch_session is blocked for a lane. Default 0 disables.",
    )
    goal_plan_parser.add_argument(
        "--worker-profile",
        choices=WORKER_PROFILE_CHOICES,
        default=DEFAULT_WORKER_PROFILE,
        help="Worker profile for Codex workers launched by fanout.",
    )
    goal_plan_parser.add_argument(
        "--worker-codex-model",
        help="Pass -m/--model to Codex workers launched by fanout.",
    )
    goal_plan_parser.add_argument(
        "--worker-codex-config",
        action="append",
        default=None,
        help="Pass one -c key=value override to Codex workers. Repeatable.",
    )
    goal_plan_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    for goal_command, help_text in (
        ("list", "List active Supervisor goals."),
        ("archive", "Archive one handled Supervisor goal."),
    ):
        goal_command_parser = goal_subparsers.add_parser(goal_command, help=help_text)
        goal_command_parser.add_argument(
            "--codex-home",
            default=str(Path.home() / ".codex"),
            help="Codex home directory. Defaults to ~/.codex.",
        )
        goal_command_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    goal_subparsers.choices["archive"].add_argument(
        "--goal-id",
        required=True,
        help="Supervisor goal id to archive.",
    )
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="List or archive completed Supervisor lifecycle items.",
    )
    cleanup_subparsers = cleanup_parser.add_subparsers(
        dest="cleanup_command",
        required=True,
    )
    for cleanup_command, help_text in (
        ("list", "List completed goals, managed workers, and notifications."),
        ("archive", "Archive completed lifecycle items without deleting Codex history."),
    ):
        cleanup_command_parser = cleanup_subparsers.add_parser(
            cleanup_command,
            help=help_text,
        )
        cleanup_command_parser.add_argument(
            "--codex-home",
            default=str(Path.home() / ".codex"),
            help="Codex home directory. Defaults to ~/.codex.",
        )
        cleanup_command_parser.add_argument(
            "--json",
            action="store_true",
            help="Print JSON output.",
        )
    cleanup_archive_parser = cleanup_subparsers.choices["archive"]
    cleanup_target = cleanup_archive_parser.add_mutually_exclusive_group(required=True)
    cleanup_target.add_argument(
        "--all",
        action="store_true",
        help="Archive every currently listed cleanup candidate.",
    )
    cleanup_target.add_argument("--goal-id", help="Archive one completed goal.")
    cleanup_target.add_argument("--name", help="Archive one completed managed worker.")
    cleanup_target.add_argument(
        "--notification-id",
        help="Mark one completed Supervisor notification as read.",
    )
    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume a Codex session with a prompt and register the managed process.",
    )
    resume_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    resume_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory for Codex. Defaults to the current directory.",
    )
    resume_parser.add_argument("--name", required=True, help="Managed lane name.")
    resume_parser.add_argument("--prompt", required=True, help="Prompt sent after resume.")
    resume_target = resume_parser.add_mutually_exclusive_group(required=True)
    resume_target.add_argument("--session-id", help="Codex session id or thread name.")
    resume_target.add_argument(
        "--last",
        action="store_true",
        help="Resume the most recent Codex session.",
    )
    resume_parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable name or path.",
    )
    resume_parser.add_argument(
        "--codex-model",
        help="Pass -m/--model to the resumed Codex worker.",
    )
    resume_parser.add_argument(
        "--codex-config",
        action="append",
        default=[],
        help="Pass one -c key=value override to the resumed Codex worker. Repeatable.",
    )
    resume_parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
    guide_parser.add_argument(
        "--worker-profile",
        choices=WORKER_PROFILE_CHOICES,
        default=DEFAULT_WORKER_PROFILE,
        help="Worker profile used in generated loop/daemon commands.",
    )
    guide_parser.add_argument(
        "--worker-codex-model",
        help="Codex worker model used in generated loop/daemon commands.",
    )
    guide_parser.add_argument(
        "--worker-codex-config",
        action="append",
        help=(
            "Codex worker -c key=value override used in generated loop/daemon "
            "commands. Repeatable; replaces the guide default when provided."
        ),
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
            _normalize_loop_execution_mode(args)
            _validate_execution_modes(args)
            _run_supervise(args)
            return 0
        if args.command == "up":
            payload = _up_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_daemon_plain(payload)
            return 0
        if args.command == "daemon":
            if (
                args.daemon_command == "watcher"
                and args.watcher_command == "run"
            ):
                _run_daemon_watcher(args)
                return 0
            payload = _daemon_payload(args)
            if args.json:
                _print_json(payload)
            elif args.daemon_command == "watcher":
                _print_watcher_plain(payload)
            else:
                _print_daemon_plain(payload)
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
                codex_model=args.codex_model,
                codex_config=tuple(args.codex_config),
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
        if args.command == "worker-review":
            payload = collect_worker_reviews(codex_home=Path(args.codex_home))
            if args.json:
                _print_json(payload)
            else:
                print(render_worker_review_plain(payload))
            return 0
        if args.command == "integration-review":
            payload = collect_integration_reviews(
                codex_home=Path(args.codex_home),
                base_ref=args.base,
                include_unfinished=args.include_unfinished,
            )
            if args.json:
                _print_json(payload)
            else:
                print(render_integration_review_plain(payload))
            return 0
        if args.command == "replan":
            payload = _replan_payload(args)
            if args.json:
                _print_json(payload)
            else:
                print(render_supervisor_replan_plain(payload))
            return 0
        if args.command == "context":
            result = request_project_context(
                codex_home=Path(args.codex_home),
                cwd=Path(args.cwd),
                query=args.query,
                max_results=args.limit,
            )
            if args.json:
                _print_json({"status": "ok", "context": result.to_dict()})
            else:
                print(f"上下文：{result.query}")
                for item in result.items:
                    print(f"{item.path}:{item.line}: {item.text}")
            return 0
        if args.command == "decision":
            payload = _decision_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_decision_plain(payload)
            return 0
        if args.command == "goal":
            payload = _goal_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_goal_plain(payload)
            return 0
        if args.command == "cleanup":
            payload = _cleanup_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_cleanup_plain(payload)
            return 0
        if args.command == "resume":
            record = resume_managed_codex(
                codex_home=Path(args.codex_home),
                cwd=Path(args.cwd),
                name=args.name,
                prompt=args.prompt,
                session_id=args.session_id,
                last=args.last,
                codex_bin=args.codex_bin,
                codex_model=args.codex_model,
                codex_config=tuple(args.codex_config),
                popen=subprocess.Popen,
            )
            if args.json:
                _print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已恢复托管 Codex：{record.name}")
                target = "--last" if record.resume_last else record.resume_session_id
                print(f"session：{target}")
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


def _daemon_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.daemon_command == "watcher":
        return _watcher_payload(args)
    if args.daemon_command == "start":
        daemon = _start_daemon_from_args(args)
    elif args.daemon_command == "status":
        daemon = supervisor_daemon_status(codex_home=Path(args.codex_home))
        daemon["activity"] = _daemon_activity_payload(Path(args.codex_home), daemon)
    elif args.daemon_command == "stop":
        daemon = stop_supervisor_daemon(codex_home=Path(args.codex_home))
    elif args.daemon_command == "watchdog":
        daemon = watchdog_supervisor_daemon(codex_home=Path(args.codex_home))
    else:
        raise ValueError(f"unknown daemon command: {args.daemon_command}")
    return {
        "status": "ok",
        "daemon": daemon,
    }


def _up_payload(args: argparse.Namespace) -> dict[str, Any]:
    daemon = _start_daemon_from_args(args)
    daemon["activity"] = _daemon_activity_payload(Path(args.codex_home), daemon)
    return {
        "status": "ok",
        "daemon": daemon,
    }


def _start_daemon_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    if args.limit <= 0:
        raise ValueError("limit must be positive")
    if args.max_continue_count < 0:
        raise ValueError("max_continue_count must be zero or positive")
    if args.max_context_requests < 0:
        raise ValueError("max_context_requests must be zero or positive")
    if args.max_run_minutes < 0:
        raise ValueError("max_run_minutes must be zero or positive")
    worker_profile = _worker_profile_from_args(args)
    queued_goal = _queue_daemon_goal_from_args(args)
    daemon = start_supervisor_daemon(
        codex_home=Path(args.codex_home),
        interval=args.interval,
        limit=args.limit,
        stale_after=args.stale_after,
        active_within=args.active_within,
        prompt_cooldown=args.prompt_cooldown,
        max_continue_count=args.max_continue_count,
        max_context_requests=args.max_context_requests,
        max_run_minutes=args.max_run_minutes,
        name=args.name,
        goal=None,
        llm_summary=args.llm_summary,
        auto_adopt=args.auto_adopt,
        worker_codex_model=_worker_codex_model(args, profile=worker_profile),
        worker_codex_config=_worker_codex_config(args, profile=worker_profile),
    )
    if queued_goal is not None:
        daemon["queued_goal"] = queued_goal
    return daemon


def _queue_daemon_goal_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    goal = _explicit_goal_text(args)
    if goal is None:
        return None
    queued = record_supervisor_goal(
        codex_home=Path(args.codex_home),
        cwd=_explicit_goal_workspace(args),
        goal=goal,
    )
    return queued.to_dict()


def _daemon_activity_payload(
    codex_home: Path,
    daemon: dict[str, Any],
) -> dict[str, Any]:
    log_path = daemon.get("log_path")
    daemon_log = _read_tail_text(log_path if isinstance(log_path, str) else None)
    activity: dict[str, Any] = {
        "recent_llm_action": _recent_llm_action_from_log(daemon_log),
        "recent_execution": _recent_execution_from_log(daemon_log),
        "recent_worker": _recent_worker_payload(codex_home),
    }
    active_goals = _active_goal_dicts_for_codex_home(
        codex_home,
        include_status=True,
    )
    if active_goals:
        activity["active_goals"] = active_goals
    return activity


def _read_tail_text(path_text: str | None, *, max_bytes: int = 64 * 1024) -> str:
    if not path_text:
        return ""
    path = Path(path_text).expanduser()
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    try:
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            data = handle.read()
    except OSError:
        return ""
    return data.decode("utf-8", errors="ignore")


def _recent_llm_action_from_log(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    recent: dict[str, str] | None = None
    for index, raw_line in enumerate(lines):
        if raw_line.strip() != "[LLM 白名单动作]":
            continue
        for action_line in lines[index + 1 :]:
            line = action_line.strip()
            if not line:
                continue
            if " / " in line:
                kind, reason = line.split(" / ", 1)
            else:
                kind, reason = line, ""
            recent = {"kind": kind.strip(), "reason": reason.strip()}
            break
    return recent


def _recent_execution_from_log(text: str) -> dict[str, str] | None:
    recent: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("已执行："):
            recent = {"status": "executed", "detail": line.removeprefix("已执行：").strip()}
        elif line.startswith("已跳过："):
            recent = {"status": "skipped", "detail": line.removeprefix("已跳过：").strip()}
    return recent


def _recent_worker_payload(codex_home: Path) -> dict[str, Any] | None:
    records = [
        record
        for record in read_managed_record_events(default_registry_path(codex_home))
        if record.status != "archived"
    ]
    if not records:
        return None
    record = records[-1]
    model, config = _codex_worker_options_from_command(record.command)
    excerpt = _managed_process_log_excerpt(record.log_path)
    protocol = _supervisor_protocol_from_text(excerpt or "")
    status = protocol.get("status") or record.status
    if (
        record.backend != "tmux"
        and status in {"launched", "resumed", "working"}
        and not _pid_is_running(record.pid)
    ):
        status = "exited"
    return {
        "name": record.name,
        "record_id": record.record_id,
        "backend": record.backend,
        "pid": record.pid,
        "model": model,
        "config": config,
        "status": status,
        "summary": protocol.get("summary"),
        "next": protocol.get("next"),
        "log_path": record.log_path,
    }


def _codex_worker_options_from_command(command: tuple[str, ...]) -> tuple[str | None, list[str]]:
    model: str | None = None
    config: list[str] = []
    index = 0
    while index < len(command):
        item = command[index]
        if item in {"-m", "--model"} and index + 1 < len(command):
            model = command[index + 1]
            index += 2
            continue
        if item in {"-c", "--config"} and index + 1 < len(command):
            config.append(command[index + 1])
            index += 2
            continue
        index += 1
    return model, config


def _watcher_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.watcher_command == "start":
        if args.interval <= 0:
            raise ValueError("interval must be positive")
        watcher = start_supervisor_watcher(
            codex_home=Path(args.codex_home),
            interval=args.interval,
        )
    elif args.watcher_command == "status":
        watcher = supervisor_watcher_status(codex_home=Path(args.codex_home))
    elif args.watcher_command == "stop":
        watcher = stop_supervisor_watcher(codex_home=Path(args.codex_home))
    else:
        raise ValueError(f"unknown watcher command: {args.watcher_command}")
    return {
        "status": "ok",
        "watcher": watcher,
    }


def _run_daemon_watcher(args: argparse.Namespace) -> None:
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    if args.iterations is not None and args.iterations <= 0:
        raise ValueError("iterations must be positive")
    for payload in run_supervisor_watcher(
        codex_home=Path(args.codex_home),
        interval=args.interval,
        iterations=args.iterations,
    ):
        if args.json:
            _print_json(payload)
        else:
            _print_watcher_run_plain(payload)


def _print_daemon_plain(payload: dict[str, Any]) -> None:
    daemon = payload["daemon"]
    status = daemon["status"]
    print("[Codex Supervisor daemon]")
    if status == "running":
        action = daemon.get("action")
        if action in {"already_running", "alive"}:
            label = "后台 loop 仍在运行"
        elif action == "restarted":
            label = "后台 loop 已由 watchdog 重启"
        else:
            label = "已启动后台 loop"
        print(label)
        print(f"pid：{daemon['pid']}")
        if "previous_pid" in daemon:
            print(f"旧 pid：{daemon['previous_pid']}")
        print(f"日志：{daemon['log_path']}")
        print("命令：" + shlex.join(daemon["command"]))
        _print_daemon_activity_plain(daemon.get("activity"))
        return
    if status == "stopped":
        print("已停止后台 loop")
        print(f"pid：{daemon['pid']}")
        print(f"状态文件：{daemon['state_path']}")
        _print_daemon_activity_plain(daemon.get("activity"))
        return
    if status == "stale":
        print("后台 loop 状态已过期，进程可能已经退出。")
        print(f"pid：{daemon['pid']}")
        print(f"日志：{daemon['log_path']}")
        _print_daemon_activity_plain(daemon.get("activity"))
        return
    print("后台 loop 未运行。")
    print(f"状态文件：{daemon['state_path']}")
    _print_daemon_activity_plain(daemon.get("activity"))


def _print_daemon_activity_plain(activity: Any) -> None:
    if not isinstance(activity, dict):
        return
    action = activity.get("recent_llm_action")
    execution = activity.get("recent_execution")
    worker = activity.get("recent_worker")
    active_goals = activity.get("active_goals")
    if not action and not execution and not worker and not active_goals:
        return
    print("最近活动：")
    if isinstance(action, dict):
        print(f"LLM 动作：{action.get('kind') or '未知'} / {action.get('reason') or '无'}")
    if isinstance(execution, dict):
        print(
            f"执行结果：{execution.get('status') or 'unknown'} / "
            f"{execution.get('detail') or '无'}"
        )
    if isinstance(worker, dict):
        config = worker.get("config")
        config_text = ", ".join(config) if isinstance(config, list) and config else "无"
        print(
            f"最近 worker：{worker.get('name') or '未知'} "
            f"模型={worker.get('model') or '未指定'} 配置={config_text} "
            f"状态={worker.get('status') or '未知'}"
        )
        if worker.get("summary"):
            print(f"worker 摘要：{worker['summary']}")
    if isinstance(active_goals, list) and active_goals:
        print("活跃目标：")
        for item in active_goals:
            status = item.get("last_status") or "未汇报"
            print(
                f"- {item.get('target_name') or item.get('goal_id')}: "
                f"{status} / {item.get('goal') or '无目标文本'}"
            )
            if item.get("last_summary"):
                print(f"  摘要：{item['last_summary']}")


def _print_watcher_plain(payload: dict[str, Any]) -> None:
    watcher = payload["watcher"]
    status = watcher["status"]
    print("[Codex Supervisor watcher]")
    if status == "running":
        action = watcher.get("action")
        label = "周期 watcher 仍在运行" if action == "already_running" else "已启动周期 watcher"
        print(label)
        print(f"pid：{watcher['pid']}")
        print(f"日志：{watcher['log_path']}")
        print("命令：" + shlex.join(watcher["command"]))
        return
    if status == "stopped":
        print("已停止周期 watcher")
        print(f"pid：{watcher['pid']}")
        print(f"状态文件：{watcher['state_path']}")
        return
    if status == "stale":
        print("周期 watcher 状态已过期，进程可能已经退出。")
        print(f"pid：{watcher['pid']}")
        print(f"日志：{watcher['log_path']}")
        return
    print("周期 watcher 未运行。")
    print(f"状态文件：{watcher['state_path']}")


def _print_watcher_run_plain(payload: dict[str, Any]) -> None:
    watchdog = payload["watchdog"]
    print(f"[Codex Supervisor watcher] 第 {payload['iteration']} 轮")
    print(f"动作：{watchdog.get('action')}")
    print(f"状态：{watchdog.get('status')}")
    if watchdog.get("pid") is not None:
        print(f"pid：{watchdog['pid']}")


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
        goal_updates = _sync_goal_lifecycle(args, report)
        fingerprint = _report_fingerprint(report)
        report_changed = previous_fingerprint != fingerprint
        precomputed_auto_action: dict[str, Any] | None = None
        precomputed_executed: dict[str, Any] | None = None
        precomputed_payload: dict[str, Any] | None = None
        force_print = False
        if args.changes_only and not report_changed:
            if args.llm_execute:
                precomputed_payload = _supervise_payload(
                    args,
                    report,
                    iteration=count + 1,
                    auto_adopted=auto_adopted,
                    goal_updates=goal_updates,
                )
                force_print = _executed_action_forces_print(
                    precomputed_payload.get("executed", {})
                )
            elif args.auto_execute:
                precomputed_auto_action = _auto_execute_action(
                    report,
                    target_name=args.name,
                    codex_home=Path(args.codex_home),
                    prompt_cooldown_seconds=args.prompt_cooldown,
                    max_continue_count=args.max_continue_count,
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
            or bool(goal_updates)
        )
        if should_print:
            payload = precomputed_payload or _supervise_payload(
                args,
                report,
                iteration=count + 1,
                auto_adopted=auto_adopted,
                precomputed_auto_action=precomputed_auto_action,
                precomputed_executed=precomputed_executed,
                goal_updates=goal_updates,
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


def _sync_goal_lifecycle(
    args: argparse.Namespace,
    report: Any,
) -> list[dict[str, Any]]:
    active_goals = {
        goal.target_name: goal
        for goal in read_active_supervisor_goals(
            codex_home=Path(args.codex_home),
            limit=1000,
        )
    }
    if not active_goals:
        return []
    updates: list[dict[str, Any]] = []
    for session in report.sessions:
        target_name = getattr(session, "managed_name", None)
        if not isinstance(target_name, str) or not target_name:
            continue
        status = _goal_status_from_session(session)
        if status is None:
            continue
        goal = active_goals.pop(target_name, None)
        if goal is None:
            continue
        update = _record_goal_status_from_session(
            args,
            goal_id=goal.goal_id,
            target_name=target_name,
            session=session,
            status=status,
        )
        updates.append(update)
    return updates


def _goal_status_from_session(session: Any) -> str | None:
    status = getattr(session, "supervisor_status", None)
    if not isinstance(status, str):
        return None
    normalized = status.lower()
    if normalized not in {"done", "blocked", "needs_user"}:
        return None
    return normalized


def _record_goal_status_from_session(
    args: argparse.Namespace,
    *,
    goal_id: str,
    target_name: str,
    session: Any,
    status: str,
) -> dict[str, Any]:
    summary = getattr(session, "supervisor_summary", None)
    next_step = getattr(session, "supervisor_next", None)
    session_id = getattr(session, "session_id", None)
    event = record_supervisor_goal_status(
        codex_home=Path(args.codex_home),
        goal_id=goal_id,
        status=status,
        target_name=target_name,
        session_id=session_id if isinstance(session_id, str) else None,
        summary=summary if isinstance(summary, str) else None,
        next_step=next_step if isinstance(next_step, str) else None,
    )
    update: dict[str, Any] = {
        "goal_id": goal_id,
        "target_name": target_name,
        "session_id": session_id,
        "status": status,
    }
    if isinstance(summary, str) and summary:
        update["summary"] = summary
    if isinstance(next_step, str) and next_step:
        update["next"] = next_step
    if event is None:
        update["skipped"] = True
        update["reason"] = "duplicate goal status"
    else:
        update["event"] = event
    if status == "done":
        update["archived"] = archive_supervisor_goal(
            codex_home=Path(args.codex_home),
            goal_id=goal_id,
            status=status,
            target_name=target_name,
            session_id=session_id if isinstance(session_id, str) else None,
            summary=summary if isinstance(summary, str) else None,
            next_step=next_step if isinstance(next_step, str) else None,
        )
    return update


def _unknown_tmux_bell_hook(_session: str) -> None:
    return None


def _guide_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    cwd = str(Path(args.cwd).expanduser())
    tmux_session = args.tmux_session or args.name
    worker_profile = _worker_profile_from_args(args)
    worker_codex_model = _worker_codex_model(args, profile=worker_profile)
    worker_codex_config = _worker_codex_config(args, profile=worker_profile)
    worker_codex_args = _guide_worker_codex_args(
        model=worker_codex_model,
        config=worker_codex_config,
    )
    commands = {
        "resume": shlex.join(
            [
                "isotope-supervisor",
                "resume",
                "--name",
                args.name,
                "--cwd",
                cwd,
                "--session-id",
                "<session-id>",
                "--prompt",
                args.prompt,
            ]
        ),
        "resume_last": shlex.join(
            [
                "isotope-supervisor",
                "resume",
                "--name",
                args.name,
                "--cwd",
                cwd,
                "--last",
                "--prompt",
                args.prompt,
            ]
        ),
        "launch_process": shlex.join(
            [
                "isotope-supervisor",
                "launch",
                "--name",
                args.name,
                "--cwd",
                cwd,
                "--prompt",
                args.prompt,
            ]
        ),
        "launch_tmux": shlex.join(
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
                *worker_codex_args,
            ]
        ),
        "daemon": shlex.join(
            [
                "isotope-supervisor",
                "daemon",
                "start",
                "--interval",
                str(args.interval),
                *worker_codex_args,
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
            "worker_profile": worker_profile,
            "worker_codex_model": worker_codex_model,
            "worker_codex_config": list(worker_codex_config),
        },
        "commands": commands,
    }


def _guide_worker_codex_args(*, model: str | None, config: tuple[str, ...]) -> list[str]:
    args: list[str] = []
    if model:
        args.extend(["--worker-codex-model", model])
    for item in config:
        args.extend(["--worker-codex-config", item])
    return args


def _print_guide_plain(payload: dict[str, Any]) -> None:
    workflow = payload["workflow"]
    commands = payload["commands"]
    print("[Codex Supervisor 使用入口]")
    print(f"工作目录：{workflow['cwd']}")
    print(f"托管名：{workflow['lane_name']}")
    print(f"tmux：{workflow['tmux_session']}")
    print()
    print("1. 恢复历史会话并发送新指令：")
    print(commands["resume"])
    print("最近会话可用：")
    print(commands["resume_last"])
    print()
    print("2. 需要开新会话时：")
    print(commands["launch_process"])
    print()
    print("3. 需要透明旁观同一个 TUI 时，才使用 tmux：")
    print(commands["launch_tmux"])
    print(commands["adopt"])
    print()
    print("4. 启动后台自动监督：")
    print(commands["daemon"])
    print("前台调试可用：")
    print(commands["supervise"])
    print()
    print("5. 需要观察细节时：")
    print(commands["web"])
    print(commands["attach"])
    print()
    print("6. 窗口不用再跟进时归档：")
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
    if getattr(args, "max_continue_count", 0) < 0:
        raise ValueError("max_continue_count must be zero or positive")
    if getattr(args, "max_context_requests", 0) < 0:
        raise ValueError("max_context_requests must be zero or positive")
    if getattr(args, "max_run_minutes", 0) < 0:
        raise ValueError("max_run_minutes must be zero or positive")
    if getattr(args, "max_fanout_launches", 1) <= 0:
        raise ValueError("max_fanout_launches must be positive")
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


def _normalize_loop_execution_mode(args: argparse.Namespace) -> None:
    if getattr(args, "rule_execute", False):
        args.auto_execute = True
        args.llm_execute = False
        args.llm_action = False


def _action_report_for_workspace(args: argparse.Namespace, report: Any) -> Any:
    workspace_root = _workspace_root(args)
    if workspace_root is None:
        return report
    sessions = tuple(
        session
        for session in report.sessions
        if _session_in_workspace(session, workspace_root)
    )
    if not sessions and not getattr(args, "workspace_root", None):
        return report
    return CodexSupervisorReport(
        generated_at=report.generated_at,
        sessions=sessions,
    )


def _workspace_scope_payload(
    args: argparse.Namespace,
    report: Any,
    action_report: Any,
) -> dict[str, Any]:
    workspace_root = _workspace_root(args)
    return {
        "mode": "all" if workspace_root is None else "workspace",
        "workspace_root": str(workspace_root) if workspace_root is not None else None,
        "total_sessions": len(report.sessions),
        "candidate_sessions": len(action_report.sessions),
    }


def _workspace_root(args: argparse.Namespace) -> Path | None:
    if getattr(args, "all_workspaces", False):
        return None
    raw = getattr(args, "workspace_root", None)
    return Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()


def _goal_text(args: argparse.Namespace) -> str | None:
    explicit = _explicit_goal_text(args)
    if explicit is not None:
        return explicit
    active_goal = _selected_active_goal(args)
    return active_goal.get("goal") if active_goal else None


def _explicit_goal_text(args: argparse.Namespace) -> str | None:
    raw = getattr(args, "goal", None)
    if not isinstance(raw, str):
        return None
    return raw.strip() or None


def _goal_workspace(args: argparse.Namespace) -> str | None:
    raw = getattr(args, "goal", None)
    if isinstance(raw, str) and raw.strip():
        workspace = _explicit_goal_workspace(args)
        return str(workspace.resolve())
    active_goal = _selected_active_goal(args)
    if active_goal and isinstance(active_goal.get("cwd"), str):
        return active_goal["cwd"]
    return None


def _goal_target_name(args: argparse.Namespace) -> str | None:
    raw = getattr(args, "goal", None)
    if isinstance(raw, str) and raw.strip():
        return None
    active_goal = _selected_active_goal(args)
    if active_goal and isinstance(active_goal.get("target_name"), str):
        return active_goal["target_name"]
    return None


def _explicit_goal_workspace(args: argparse.Namespace) -> Path:
    raw = getattr(args, "workspace_root", None)
    return Path(raw).expanduser() if isinstance(raw, str) and raw else Path.cwd()


def _selected_active_goal(args: argparse.Namespace) -> dict[str, Any] | None:
    goals = _active_goal_dicts(args, limit=1)
    return goals[0] if goals else None


def _session_in_workspace(session: Any, workspace_root: Path) -> bool:
    cwd = getattr(session, "cwd", None)
    if not isinstance(cwd, str) or not cwd:
        return False
    session_cwd = Path(cwd).expanduser().resolve()
    return session_cwd == workspace_root or workspace_root in session_cwd.parents


def _supervise_payload(
    args: argparse.Namespace,
    report: Any,
    *,
    iteration: int,
    auto_adopted: list[dict[str, str]] | None = None,
    goal_updates: list[dict[str, Any]] | None = None,
    precomputed_auto_action: dict[str, Any] | None = None,
    precomputed_executed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action_report = _action_report_for_workspace(args, report)
    active_goals = _active_goal_dicts(args, include_status=True)
    explicit_goal = _explicit_goal_text(args)
    payload = _advice_payload(
        action_report,
        target_name=args.name,
        include_all_managed=args.llm_action or args.llm_execute,
        allow_workspace_actions=_loop_allows_workspace_actions(
            args,
            active_goals,
            explicit_goal,
        ),
        goal=_goal_text(args),
        goal_workspace=_goal_workspace(args),
        goal_target_name=_goal_target_name(args),
        active_goals=None if explicit_goal else active_goals,
    )
    payload["workspace_scope"] = _workspace_scope_payload(args, report, action_report)
    payload["iteration"] = iteration
    payload["report"] = report.to_dict()
    payload["automation"] = _automation_status(report)
    payload["auto_adopted"] = auto_adopted or []
    payload["active_goals"] = active_goals
    if goal_updates:
        payload["goal_updates"] = goal_updates
    worker_reviews: dict[str, Any] | None = None
    if args.llm_action or args.llm_execute:
        payload["recent_context_results"] = _recent_context_results(args, action_report)
        payload["recent_decision_answers"] = _decision_answer_dicts(args)
        worker_reviews = _worker_review_context(args)
        payload["worker_reviews"] = worker_reviews
    payload["current_batch"] = _current_batch_payload(
        report,
        active_goals=active_goals,
        worker_reviews=worker_reviews,
    )
    if args.llm_summary:
        payload["llm_summary"] = _summarize_with_llm(report)
    fanout_plan = _active_goals_fanout_launch_plan(args, report, active_goals)
    if fanout_plan is not None and (args.llm_action or args.llm_execute):
        payload["fanout_plan"] = fanout_plan
    if args.llm_action or args.llm_execute:
        if fanout_plan is not None:
            payload["llm_action"] = _fanout_llm_action(fanout_plan)
        elif _loop_without_autonomous_scope(
            args,
            action_report,
            active_goals,
            explicit_goal,
        ):
            payload["llm_action"] = _idle_loop_llm_action()
        else:
            payload["llm_action"] = _decide_action_with_llm(action_report, payload)
            _promote_llm_command_suggestion(payload)
    if args.llm_execute:
        if fanout_plan is not None:
            payload["executed"] = _execute_fanout_launch_actions(args, fanout_plan)
            if _fanout_execution_launched_workers(payload["executed"]):
                refreshed_report = _scan_report(args)
                payload["current_batch"] = _current_batch_payload(
                    refreshed_report,
                    active_goals=active_goals,
                    worker_reviews=worker_reviews,
                )
        else:
            payload["executed"] = _execute_llm_action(args, action_report, payload)
            _maybe_replan_after_context_request(args, action_report, payload)
    elif args.auto_execute:
        auto_action = precomputed_auto_action or _auto_execute_action(
            action_report,
            target_name=args.name,
            codex_home=Path(args.codex_home),
            prompt_cooldown_seconds=args.prompt_cooldown,
            max_continue_count=args.max_continue_count,
            max_run_minutes=args.max_run_minutes,
        )
        payload["auto_action"] = auto_action
        payload["executed"] = precomputed_executed or _execute_auto_action(
            args,
            action_report,
            auto_action,
        )
    elif args.execute:
        payload["executed"] = _execute_advice(args, report, payload)
    payload["decision_requests"] = _decision_request_dicts(args)
    return payload


def _active_goals_fanout_launch_plan(
    args: argparse.Namespace,
    report: Any,
    active_goals: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    targets = [
        target_name
        for goal in active_goals
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str) and target_name
    ]
    if len(targets) < 2:
        return None
    goal_plan = {
        "goals": active_goals,
        "parallel_recommendations": [
            {
                "batch": "active_goals",
                "targets": targets,
                "reason": "多个 active goals 可并行启动受控 worker。",
            }
        ],
    }
    return build_fanout_launch_plan(
        goal_plan,
        limit=getattr(args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT),
        running_target_names=_running_managed_target_names(report),
        requires_human_review=False,
    )


def _fanout_llm_action(fanout_plan: dict[str, Any]) -> dict[str, Any]:
    launchable = fanout_plan.get("summary", {}).get("launchable", 0)
    if launchable:
        reason = "多个 active goals 可并行启动受控 worker。"
    else:
        reason = "多个 active goals 已被 running worker 或 fanout gate 跳过。"
    return {
        "kind": "fanout_launch_sessions",
        "target_name": None,
        "reason": reason,
        "command_suggestion": None,
    }


def _execute_fanout_launch_actions(
    args: argparse.Namespace,
    fanout_plan: dict[str, Any],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for launch_spec in fanout_plan.get("launch_specs") or []:
        if not isinstance(launch_spec, dict):
            continue
        result = _execute_launch_action(args, launch_spec)
        if result.get("skipped"):
            skipped.append(result)
        else:
            results.append(result)
    return {
        "kind": "fanout_launch_sessions",
        "summary": {
            "launched": len(results),
            "skipped": len(skipped),
            "limit": fanout_plan.get("summary", {}).get("limit"),
        },
        "results": results,
        "skipped": skipped,
    }


def _fanout_execution_launched_workers(executed: dict[str, Any]) -> bool:
    summary = executed.get("summary")
    return isinstance(summary, dict) and bool(summary.get("launched"))


def _loop_without_autonomous_scope(
    args: argparse.Namespace,
    report: Any,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
) -> bool:
    if getattr(args, "command", None) != "loop":
        return False
    if getattr(args, "name", None):
        return False
    if explicit_goal or active_goals:
        return False
    return not _has_loop_managed_scope(report)


def _loop_allows_workspace_actions(
    args: argparse.Namespace,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
) -> bool:
    if getattr(args, "command", None) != "loop":
        return True
    return bool(getattr(args, "name", None) or explicit_goal or active_goals)


def _has_loop_managed_scope(report: Any) -> bool:
    for session in report.sessions:
        if _is_active_managed_tmux_session(session):
            return True
        if (
            getattr(session, "managed", False)
            and getattr(session, "managed_name", None)
            and not _is_completed_session(session)
            and not _session_marks_terminal_done(session)
        ):
            return True
    return False


def _idle_loop_llm_action() -> dict[str, Any]:
    return {
        "kind": "monitor",
        "target_name": None,
        "reason": IDLE_LOOP_REASON,
        "command_suggestion": None,
    }


def _maybe_replan_after_context_request(
    args: argparse.Namespace,
    report: Any,
    payload: dict[str, Any],
) -> None:
    executed = payload.get("executed")
    if not isinstance(executed, dict) or executed.get("kind") != "request_context":
        return
    if executed.get("skipped"):
        return
    context_result = executed.get("context")
    if isinstance(context_result, dict):
        recent = list(payload.get("recent_context_results") or [])
        recent.append(context_result)
        payload["recent_context_results"] = recent[-3:]
    payload["llm_followup_action"] = _decide_action_with_llm(report, payload)
    followup_payload = {
        **payload,
        "llm_action": payload["llm_followup_action"],
    }
    payload["followup_executed"] = _execute_llm_action(args, report, followup_payload)


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
    payload = _dashboard_payload(
        report,
        active_goals=_active_goal_dicts(args, include_status=True),
        decision_requests=_decision_request_dicts(args),
        notifications=_notification_dicts(Path(args.codex_home)),
    )
    if args.json:
        _print_json(payload)
        return
    _print_dashboard_plain(payload)


def _dashboard_payload(
    report: Any,
    *,
    active_goals: list[dict[str, Any]] | None = None,
    decision_requests: list[dict[str, Any]] | None = None,
    notifications: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {
        "needs_attention": [],
        "done": [],
        "working": [],
    }
    display_sessions = _dashboard_display_sessions(report.sessions)
    for session, linked_session, linked_match in display_sessions:
        groups[_dashboard_group_for(session, linked_session=linked_session)].append(
            _dashboard_item(
                session,
                linked_session=linked_session,
                linked_match=linked_match,
            )
        )
    notification_items = notifications or []
    return {
        "status": "ok",
        "generated_at": report.generated_at,
        "recommendation": report.recommendation.to_dict(),
        "counts": {key: len(value) for key, value in groups.items()},
        "groups": groups,
        "current": _dashboard_current_payload(
            display_sessions,
            active_goals=active_goals,
        ),
        "decision_requests": decision_requests or [],
        "notifications": notification_items,
        "notification_counts": {
            "total": len(notification_items),
            "unread": sum(1 for item in notification_items if item.get("unread") is True),
        },
    }


def _dashboard_current_payload(
    display_sessions: list[tuple[Any, Any | None, dict[str, Any] | None]],
    *,
    active_goals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _current_batch_payload_from_display_sessions(
        display_sessions,
        active_goals=active_goals,
    )


def _current_batch_payload(
    report: Any,
    *,
    active_goals: list[dict[str, Any]] | None = None,
    worker_reviews: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _current_batch_payload_from_display_sessions(
        _dashboard_display_sessions(report.sessions),
        active_goals=active_goals,
        worker_reviews=worker_reviews,
    )


def _current_batch_payload_from_display_sessions(
    display_sessions: list[tuple[Any, Any | None, dict[str, Any] | None]],
    *,
    active_goals: list[dict[str, Any]] | None = None,
    worker_reviews: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_goals = [
        item
        for item in (_dashboard_active_goal_item(goal) for goal in active_goals or [])
    ]
    managed_workers = [
        _dashboard_item(
            session,
            linked_session=linked_session,
            linked_match=linked_match,
        )
        for session, linked_session, linked_match in display_sessions
        if getattr(session, "managed", False) and getattr(session, "managed_name", None)
    ]
    return build_current_batch_view(
        active_goals=current_goals,
        managed_workers=managed_workers,
        worker_reviews=worker_reviews,
    ).to_dict()


def _dashboard_active_goal_item(goal: dict[str, Any]) -> dict[str, Any]:
    item = dict(goal)
    cwd_exists = _cwd_is_existing_dir(goal.get("cwd"))
    item["cwd_exists"] = cwd_exists
    item["current"] = cwd_exists and goal.get("last_status") != "done"
    return item


def _is_current_managed_worker(session: Any) -> bool:
    return bool(
        getattr(session, "managed", False)
        and getattr(session, "status", None) != "exited"
        and not _is_completed_session(session)
        and getattr(session, "managed_name", None)
        and _cwd_is_existing_dir(getattr(session, "cwd", None))
    )


def _notification_dicts(codex_home: Path) -> list[dict[str, Any]]:
    return [
        _dashboard_notification_dict(notification.to_dict())
        for notification in NotificationFlow.in_process(codex_home).list_notifications()
    ]


def _dashboard_notification_dict(notification: dict[str, Any]) -> dict[str, Any]:
    item = dict(notification)
    source_ref = item.get("source_ref")
    item["source_ref"] = (
        _dashboard_notification_source_ref(source_ref)
        if isinstance(source_ref, dict)
        else {}
    )
    return item


def _dashboard_notification_source_ref(source_ref: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "ref_type",
        "goal_id",
        "request_id",
        "run_id",
        "session_id",
        "notification_id",
        "status",
    }
    return {
        key: value
        for key, value in source_ref.items()
        if key in allowed_keys and isinstance(value, (str, bool, int, float))
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
        if not _cwd_is_existing_dir(getattr(session, "cwd", None)):
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
    followup_executed = payload.get("followup_executed")
    if isinstance(followup_executed, dict) and followup_executed.get("kind") == "ask_user":
        return (
            "supervise",
            "ask_user",
            followup_executed.get("session_id"),
            followup_executed.get("question"),
        )
    executed = payload.get("executed")
    if not executed:
        return _attention_bell_fingerprint(report)
    if executed.get("kind") == "ask_user":
        return (
            "supervise",
            "ask_user",
            executed.get("session_id"),
            executed.get("question"),
        )
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
    cwd_exists = _cwd_is_existing_dir(session.cwd)
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
        "cwd_exists": cwd_exists,
        "current": _dashboard_item_is_current(session, cwd_exists=cwd_exists),
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


def _dashboard_item_is_current(session: Any, *, cwd_exists: bool) -> bool:
    if not cwd_exists or _session_marks_terminal_done(session):
        return False
    if _is_current_managed_worker(session):
        return True
    return getattr(session, "status", None) in {"working", "needs_user", "error"}


def _dashboard_status_source(session: Any, linked_session: Any | None) -> Any:
    if linked_session is not None and linked_session.supervisor_status:
        return linked_session
    return session


def _print_dashboard_plain(payload: dict[str, Any]) -> None:
    print("[Codex Supervisor dashboard]")
    print(f"生成时间：{payload['generated_at']}")
    print(f"建议：{payload['recommendation']['label']}")
    decision_requests = payload.get("decision_requests") or []
    print(f"等待拍板：{len(decision_requests)}")
    for item in decision_requests:
        target = item.get("target_name") or item.get("session_id") or "未知"
        context_status = item.get("context_status") or "unknown"
        print(f"- {item['question']} context={context_status} target={target}")
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


def _decision_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.decision_command == "list":
        return {
            "status": "ok",
            "decision_requests": _decision_request_dicts(args),
        }
    if args.decision_command == "archive":
        archived = archive_decision_request(
            codex_home=Path(args.codex_home),
            request_id=args.request_id,
        )
        return {
            "status": "ok",
            "archived": archived,
            "decision_requests": _decision_request_dicts(args),
        }
    if args.decision_command == "answer":
        answered = record_decision_answer(
            codex_home=Path(args.codex_home),
            request_id=args.request_id,
            answer=args.answer,
        )
        return {
            "status": "ok",
            "answered": answered,
            "decision_requests": _decision_request_dicts(args),
            "recent_decision_answers": _decision_answer_dicts(args),
        }
    raise ValueError(f"unsupported decision command: {args.decision_command}")


def _print_decision_plain(payload: dict[str, Any]) -> None:
    archived = payload.get("archived")
    if isinstance(archived, dict):
        print(f"已归档拍板请求：{archived['request_id']}")
    answered = payload.get("answered")
    if isinstance(answered, dict):
        print(f"已记录拍板答案：{answered['request_id']}")
    requests = payload.get("decision_requests") or []
    print(f"等待拍板：{len(requests)}")
    for item in requests:
        archive_command = shlex.join(
            [
                "isotope-supervisor",
                "decision",
                "archive",
                "--request-id",
                item["request_id"],
            ]
        )
        target = item.get("target_name") or item.get("session_id") or "未知"
        context_status = item.get("context_status") or "unknown"
        print(f"- {item['request_id']} {item['question']}")
        print(f"  target={target} context={context_status}")
        print(f"  归档：{archive_command}")


def _goal_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.goal_command == "add":
        goal = record_supervisor_goal(
            codex_home=Path(args.codex_home),
            cwd=Path(args.cwd),
            goal=_goal_command_goal_text(args),
            target_name=args.target_name,
        )
        return {
            "status": "ok",
            "goal": goal.to_dict(),
            "active_goals": _active_goal_dicts(args, include_status=True),
        }
    if args.goal_command == "plan":
        if args.fanout_execute and not args.write:
            raise ValueError("fanout-execute requires --write")
        provider = resolve_summary_provider_from_env(agent_name="supervisor")
        payload = plan_supervisor_goals(
            root=Path(args.cwd),
            codex_home=Path(args.codex_home),
            provider=provider,
            user_goal=_goal_command_goal_text(args, required=False),
            write=args.write,
            limit=args.limit,
        )
        if args.fanout_execute:
            fanout_plan = build_fanout_launch_plan(
                payload,
                cwd=str(Path(args.cwd).expanduser()),
                limit=args.max_fanout_launches,
                running_target_names=_running_managed_target_names_from_registry(
                    Path(args.codex_home)
                ),
                requires_human_review=False,
            )
            payload["fanout_plan"] = fanout_plan
            payload["executed"] = _execute_fanout_launch_actions(args, fanout_plan)
        return payload
    if args.goal_command == "list":
        return {
            "status": "ok",
            "active_goals": _active_goal_dicts(args, include_status=True),
        }
    if args.goal_command == "archive":
        archived = archive_supervisor_goal(
            codex_home=Path(args.codex_home),
            goal_id=args.goal_id,
        )
        return {
            "status": "ok",
            "archived": archived,
            "active_goals": _active_goal_dicts(args, include_status=True),
        }
    raise ValueError(f"unsupported goal command: {args.goal_command}")


def _replan_payload(args: argparse.Namespace) -> dict[str, Any]:
    return build_supervisor_replan(
        worker_reviews=collect_worker_reviews(codex_home=Path(args.codex_home)),
        integration_reviews=collect_integration_reviews(
            codex_home=Path(args.codex_home),
            base_ref=args.base,
            include_unfinished=args.include_unfinished,
        ),
        active_goals=_active_goal_dicts(args, include_status=True),
    )


def _goal_command_goal_text(
    args: argparse.Namespace,
    *,
    required: bool = True,
) -> str | None:
    positional = _optional_text(getattr(args, "goal_text", None))
    option = _optional_text(getattr(args, "goal", None))
    if positional and option and positional != option:
        raise ValueError("goal positional argument and --goal must match when both are set")
    goal = option or positional
    if required and goal is None:
        raise ValueError("goal must not be empty")
    return goal


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _print_goal_plain(payload: dict[str, Any]) -> None:
    goal = payload.get("goal")
    if isinstance(goal, dict):
        print(f"已添加目标：{goal['goal_id']}")
        print(f"目标：{goal['goal']}")
        print(f"工作区：{goal['cwd']}")
        print(f"worker：{goal['target_name']}")
    archived = payload.get("archived")
    if isinstance(archived, dict):
        print(f"已归档目标：{archived['goal_id']}")
    candidates = payload.get("candidates") or []
    if candidates:
        mode = "写入" if payload.get("mode") == "write" else "预览"
        print(f"LLM 目标规划：{mode}")
        plan_summary = payload.get("plan_summary")
        if isinstance(plan_summary, str) and plan_summary:
            print(f"计划摘要：{plan_summary}")
        phases = payload.get("phases") or []
        if phases:
            print("阶段/批次：")
            for phase in phases:
                if not isinstance(phase, dict):
                    continue
                name = phase.get("name") or "未命名阶段"
                print(f"- {name}")
                for goal in phase.get("goals") or []:
                    print(f"  目标：{goal}")
                for condition in phase.get("stop_conditions") or []:
                    print(f"  停止条件：{condition}")
                for condition in phase.get("acceptance_conditions") or []:
                    print(f"  验收条件：{condition}")
        recommendations = payload.get("parallel_recommendations") or []
        if recommendations:
            print("并行建议：")
            for item in recommendations:
                if not isinstance(item, dict):
                    continue
                batch = item.get("batch") or "未命名批次"
                targets = ", ".join(item.get("targets") or [])
                reason = item.get("reason") or ""
                print(f"- {batch}: {targets}")
                if reason:
                    print(f"  依据：{reason}")
        stop_conditions = payload.get("stop_conditions") or []
        if stop_conditions:
            print("停止条件：")
            for condition in stop_conditions:
                print(f"- {condition}")
        acceptance_conditions = payload.get("acceptance_conditions") or []
        if acceptance_conditions:
            print("验收条件：")
            for condition in acceptance_conditions:
                print(f"- {condition}")
        for item in candidates:
            print(f"- {item['target_name']} {item['goal']}")
            print(f"  依据：{item['reason']}")
    written_goals = payload.get("written_goals") or []
    if written_goals:
        print(f"已写入目标：{len(written_goals)}")
    if executed := payload.get("executed"):
        _print_executed_plain(executed)
    goals = payload.get("active_goals") or []
    print(f"活跃目标：{len(goals)}")
    for item in goals:
        archive_command = shlex.join(
            [
                "isotope-supervisor",
                "goal",
                "archive",
                "--goal-id",
                item["goal_id"],
            ]
        )
        print(f"- {item['goal_id']} {item['goal']}")
        print(f"  cwd={item['cwd']} worker={item['target_name']}")
        if item.get("last_status"):
            print(f"  状态：{item['last_status']}")
        if item.get("last_summary"):
            print(f"  摘要：{item['last_summary']}")
        if item.get("last_next"):
            print(f"  下一步：{item['last_next']}")
        print(f"  归档：{archive_command}")


def _cleanup_payload(args: argparse.Namespace) -> dict[str, Any]:
    codex_home = Path(args.codex_home)
    candidates = _cleanup_candidate_dicts(codex_home)
    if args.cleanup_command == "list":
        return {
            "status": "ok",
            "candidates": candidates,
        }
    if args.cleanup_command == "archive":
        selected = _select_cleanup_candidates(args, candidates)
        archived = [_archive_cleanup_candidate(codex_home, item) for item in selected]
        return {
            "status": "ok",
            "candidates": _cleanup_candidate_dicts(codex_home),
            "archived": archived,
            "active_goals": _active_goal_dicts_for_codex_home(
                codex_home,
                include_status=True,
            ),
        }
    raise ValueError(f"unsupported cleanup command: {args.cleanup_command}")


def _print_cleanup_plain(payload: dict[str, Any]) -> None:
    archived = payload.get("archived") or []
    if archived:
        print(f"已归档/标记：{len(archived)}")
        for item in archived:
            target = item.get("goal_id") or item.get("name") or item.get("notification_id")
            print(f"- {item['kind']} {target}")
    candidates = payload.get("candidates") or []
    print(f"可归档项：{len(candidates)}")
    for item in candidates:
        target = item.get("goal_id") or item.get("name") or item.get("notification_id")
        print(f"- {item['kind']} {target}")
        if item.get("summary"):
            print(f"  摘要：{item['summary']}")
        if item.get("command"):
            print(f"  归档：{item['command']}")


def _cleanup_candidate_dicts(codex_home: Path) -> list[dict[str, Any]]:
    goals = _cleanup_goal_candidates(codex_home)
    return [
        *goals,
        *_cleanup_managed_worker_candidates(codex_home),
        *_cleanup_notification_candidates(codex_home),
    ]


def _cleanup_goal_candidates(codex_home: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for goal in _active_goal_dicts_for_codex_home(codex_home, include_status=True):
        status = goal.get("last_status")
        if status not in ARCHIVABLE_SUPERVISOR_STATUSES:
            continue
        goal_id = goal.get("goal_id")
        if not isinstance(goal_id, str) or not goal_id:
            continue
        candidate = {
            "kind": "goal",
            "goal_id": goal_id,
            "status": status,
            "target_name": goal.get("target_name"),
            "cwd": goal.get("cwd"),
            "goal": goal.get("goal"),
            "summary": goal.get("last_summary"),
            "next": goal.get("last_next"),
            "command": _cleanup_archive_command(
                codex_home,
                "--goal-id",
                goal_id,
            ),
        }
        candidates.append(_drop_none_values(candidate))
    return candidates


def _cleanup_managed_worker_candidates(codex_home: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in read_managed_records(default_registry_path(codex_home)):
        protocol = _managed_record_supervisor_protocol(record)
        if protocol.get("status") not in ARCHIVABLE_SUPERVISOR_STATUSES:
            continue
        if _managed_record_is_still_working(record):
            continue
        candidate = {
            "kind": "managed_worker",
            "name": record.name,
            "record_id": record.record_id,
            "status": protocol.get("status"),
            "summary": protocol.get("summary"),
            "next": protocol.get("next"),
            "backend": record.backend,
            "tmux_session": record.tmux_session,
            "command": _cleanup_archive_command(
                codex_home,
                "--name",
                record.name,
            ),
        }
        candidates.append(_drop_none_values(candidate))
    return candidates


def _cleanup_notification_candidates(codex_home: Path) -> list[dict[str, Any]]:
    try:
        notifications = NotificationFlow.in_process(codex_home).list_notifications(
            unread=True,
            notification_type="supervisor_goal_status",
        )
    except (OSError, ValueError):
        return []
    candidates: list[dict[str, Any]] = []
    for notification in notifications:
        source_ref = notification.source_ref or {}
        if not isinstance(source_ref, dict):
            continue
        goal_id = source_ref.get("goal_id")
        status = source_ref.get("status")
        if status not in ARCHIVABLE_SUPERVISOR_STATUSES:
            continue
        candidate = {
            "kind": "notification",
            "notification_id": notification.notification_id,
            "type": notification.notification_type,
            "title": notification.title,
            "goal_id": goal_id,
            "status": status,
            "command": _cleanup_archive_command(
                codex_home,
                "--notification-id",
                notification.notification_id,
            ),
        }
        candidates.append(_drop_none_values(candidate))
    return candidates


def _cleanup_archive_command(codex_home: Path, *target_args: str) -> str:
    return shlex.join(
        [
            "isotope-supervisor",
            "cleanup",
            "archive",
            "--codex-home",
            str(codex_home),
            *target_args,
        ]
    )


def _select_cleanup_candidates(
    args: argparse.Namespace,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if getattr(args, "all", False):
        return candidates
    goal_id = getattr(args, "goal_id", None)
    name = getattr(args, "name", None)
    notification_id = getattr(args, "notification_id", None)
    selected = [
        item
        for item in candidates
        if (goal_id and item.get("kind") == "goal" and item.get("goal_id") == goal_id)
        or (
            name
            and item.get("kind") == "managed_worker"
            and item.get("name") == name
        )
        or (
            notification_id
            and item.get("kind") == "notification"
            and item.get("notification_id") == notification_id
        )
    ]
    if not selected:
        raise ValueError("cleanup target is not currently archivable")
    return selected


def _archive_cleanup_candidate(
    codex_home: Path,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    kind = candidate.get("kind")
    if kind == "goal":
        goal_id = str(candidate["goal_id"])
        archived = archive_supervisor_goal(codex_home=codex_home, goal_id=goal_id)
        return {
            "kind": kind,
            "goal_id": goal_id,
            "archived": archived,
        }
    if kind == "managed_worker":
        name = str(candidate["name"])
        record = archive_managed_codex(codex_home=codex_home, name=name)
        return {
            "kind": kind,
            "name": name,
            "managed": record.to_dict(),
        }
    if kind == "notification":
        notification_id = str(candidate["notification_id"])
        marked = NotificationFlow.in_process(codex_home).mark_read(notification_id)
        return {
            "kind": kind,
            "notification_id": notification_id,
            "notification": marked.to_dict(),
        }
    raise ValueError(f"unsupported cleanup candidate kind: {kind}")


def _managed_record_supervisor_protocol(record: Any) -> dict[str, str]:
    excerpt = _managed_record_status_excerpt(record)
    if not excerpt:
        return {}
    return _supervisor_protocol_from_text(excerpt)


def _managed_record_is_still_working(record: Any) -> bool:
    if record.backend != "tmux" and record.pid > 0 and _pid_is_running(record.pid):
        return True
    excerpt = _managed_record_status_excerpt(record)
    if not excerpt:
        return False
    lines = [line.strip() for line in excerpt.splitlines() if line.strip()]
    return _terminal_has_active_work_marker(lines[-8:])


def _managed_record_status_excerpt(record: Any) -> str | None:
    if record.backend == "tmux" and record.tmux_session:
        pane_text = _tmux_capture_pane(record.tmux_session)
        if pane_text:
            return pane_text
    return _managed_process_log_excerpt(record.log_path)


def _drop_none_values(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value is not None}


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
    _print_dashboard_plain(
        _dashboard_payload(
            report,
            decision_requests=payload.get("decision_requests") or [],
        )
    )
    automation = payload["automation"]
    print()
    print("[托管自动化]")
    print(automation["reason"])
    if auto_adopted := payload.get("auto_adopted"):
        for item in auto_adopted:
            print(
                f"自动接管：{item['name']} tmux={item['tmux_session']} cwd={item['cwd']}"
            )
    if goal_updates := payload.get("goal_updates"):
        print()
        print("[目标队列更新]")
        for item in goal_updates:
            archived = "，已归档" if item.get("archived") else ""
            print(f"{item['target_name']} / {item['status']}{archived}")
            if item.get("summary"):
                print(f"摘要：{item['summary']}")
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
        _print_ask_user_action_plain(llm_action)
    if llm_followup_action := payload.get("llm_followup_action"):
        print()
        print("[LLM 同轮后续动作]")
        print(f"{llm_followup_action['kind']} / {llm_followup_action['reason']}")
        _print_ask_user_action_plain(llm_followup_action)
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
    if followup_executed := payload.get("followup_executed"):
        _print_executed_plain(followup_executed)


def _print_advice(args: argparse.Namespace) -> None:
    report = _scan_report(args)
    action_report = _action_report_for_workspace(args, report)
    active_goals = _active_goal_dicts(args, include_status=True)
    explicit_goal = _explicit_goal_text(args)
    payload = _advice_payload(
        action_report,
        target_name=args.name,
        include_all_managed=args.llm_action or args.llm_execute,
        goal=_goal_text(args),
        goal_workspace=_goal_workspace(args),
        goal_target_name=_goal_target_name(args),
        active_goals=None if explicit_goal else active_goals,
    )
    payload["workspace_scope"] = _workspace_scope_payload(args, report, action_report)
    payload["active_goals"] = active_goals
    if args.llm_action or args.llm_execute:
        payload["recent_context_results"] = _recent_context_results(args, action_report)
        payload["recent_decision_answers"] = _decision_answer_dicts(args)
        payload["worker_reviews"] = _worker_review_context(args)
        payload["llm_action"] = _decide_action_with_llm(action_report, payload)
        _promote_llm_command_suggestion(payload)
    if args.llm_execute:
        payload["executed"] = _execute_llm_action(args, action_report, payload)
    elif args.execute:
        payload["executed"] = _execute_advice(args, action_report, payload)
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
        _print_ask_user_action_plain(llm_action)
    if command_suggestion is None:
        print("命令：暂无可安全生成的命令草案。")
    else:
        print(f"命令：{command_suggestion['command']}")
    if executed := payload.get("executed"):
        _print_executed_plain(executed)


def _automation_status(report: Any) -> dict[str, Any]:
    tmux_lanes = [
        session for session in report.sessions if _is_active_managed_tmux_session(session)
    ]
    process_lanes = [
        session
        for session in report.sessions
        if _is_active_managed_process_session(session)
    ]
    managed_lanes = tmux_lanes + process_lanes
    names = [session.managed_name for session in managed_lanes if session.managed_name]
    if managed_lanes:
        process_note = (
            f"{len(process_lanes)} 个后台托管 Codex 进程"
            if process_lanes
            else ""
        )
        tmux_note = f"{len(tmux_lanes)} 个可旁观 tmux lane" if tmux_lanes else ""
        joined = "，".join(item for item in (process_note, tmux_note) if item)
        return {
            "ready": True,
            "managed_tmux_count": len(tmux_lanes),
            "managed_process_count": len(process_lanes),
            "managed_names": names,
            "reason": f"当前有 {joined}。",
            "launch_hint": LAUNCH_PROCESS_HINT,
            "adopt_hint": ADOPT_TMUX_HINT,
        }
    return {
        "ready": False,
        "managed_tmux_count": 0,
        "managed_process_count": 0,
        "managed_names": [],
        "reason": "当前没有托管的 Codex 进程或可旁观 tmux lane。",
        "launch_hint": LAUNCH_PROCESS_HINT,
        "adopt_hint": ADOPT_TMUX_HINT,
    }


def _advice_payload(
    report: Any,
    *,
    target_name: str | None = None,
    include_all_managed: bool = False,
    allow_workspace_actions: bool = True,
    goal: str | None = None,
    goal_workspace: str | None = None,
    goal_target_name: str | None = None,
    active_goals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    recommendation = report.recommendation
    suggestions = _command_suggestions(
        report,
        target_name=target_name,
        include_all_managed=include_all_managed,
        allow_workspace_actions=allow_workspace_actions,
        goal=goal,
        goal_workspace=goal_workspace,
        goal_target_name=goal_target_name,
        active_goals=active_goals,
    )
    return {
        "status": "ok",
        "generated_at": report.generated_at,
        "recommendation": recommendation.to_dict(),
        "command_suggestion": suggestions[0] if suggestions else None,
        "command_suggestions": suggestions,
    }


def _promote_llm_command_suggestion(payload: dict[str, Any]) -> None:
    action = payload.get("llm_action")
    if not isinstance(action, dict):
        return
    if "command_suggestion" not in action:
        return
    if "rule_command_suggestion" not in payload:
        payload["rule_command_suggestion"] = payload.get("command_suggestion")
    payload["command_suggestion"] = action.get("command_suggestion")


def _print_executed_plain(executed: dict[str, Any]) -> None:
    if executed.get("kind") == "ask_user":
        print(f"等待拍板：{executed['question']}")
        return
    if executed.get("kind") == "fanout_launch_sessions":
        summary = executed.get("summary") or {}
        print(
            "fanout 已执行："
            f"{summary.get('launched', 0)} 个启动，"
            f"{summary.get('skipped', 0)} 个跳过"
        )
        for result in executed.get("results") or []:
            if isinstance(result, dict) and result.get("command"):
                print(f"已执行：{result['command']}")
        for result in executed.get("skipped") or []:
            if isinstance(result, dict) and result.get("reason"):
                print(f"已跳过：{result['reason']}")
        return
    if executed.get("skipped"):
        print(f"已跳过：{executed['reason']}")
        return
    print(f"已执行：{executed['command']}")


def _print_ask_user_action_plain(action: dict[str, Any]) -> None:
    if action.get("kind") != "ask_user":
        return
    question = action.get("question")
    if question:
        print(f"等待拍板：{question}")
    context_status = action.get("context_status")
    if context_status:
        print(f"上下文状态：{context_status}")


def _command_suggestions(
    report: Any,
    *,
    target_name: str | None = None,
    include_all_managed: bool = False,
    allow_workspace_actions: bool = True,
    goal: str | None = None,
    goal_workspace: str | None = None,
    goal_target_name: str | None = None,
    active_goals: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    if target_name:
        managed_tmux = _managed_tmux_session_by_name(report, target_name)
        if managed_tmux is not None:
            return _managed_tmux_command_suggestions(managed_tmux) + [
                _watch_command_suggestion()
            ]
        return [_watch_command_suggestion()]
    goal_suggestions = (
        _active_goal_action_command_suggestions(
            active_goals,
            running_target_names=_running_managed_target_names(report),
        )
        or _goal_action_command_suggestions(
            goal,
            goal_workspace,
            goal_target_name=goal_target_name,
        )
    )
    if include_all_managed:
        suggestions: list[dict[str, str]] = []
        suggestions.extend(goal_suggestions)
        for session in report.sessions:
            if _is_active_managed_tmux_session(session):
                suggestions.extend(_managed_tmux_command_suggestions(session))
            if _is_resume_capable_session(session):
                suggestions.extend(_resume_session_command_suggestions(session))
        if allow_workspace_actions:
            suggestions.extend(_workspace_action_command_suggestions(report))
        if suggestions:
            suggestions.append(_watch_command_suggestion())
            return _dedupe_command_suggestions(suggestions)
    if goal_suggestions:
        return _dedupe_command_suggestions(goal_suggestions + [_watch_command_suggestion()])
    recommendation = report.recommendation
    target = _target_session(report, recommendation.target_session_id)
    if target is not None and target.managed_tmux_session:
        return _managed_tmux_command_suggestions(target)
    if target is not None and _is_resume_capable_session(target):
        return _resume_session_command_suggestions(target) + [_watch_command_suggestion()]
    managed_tmux = _first_managed_tmux_session(report)
    if managed_tmux is not None:
        return _managed_tmux_command_suggestions(managed_tmux) + [_watch_command_suggestion()]
    if recommendation.action == "monitor":
        return [_watch_command_suggestion()]
    return []


def _workspace_action_command_suggestions(report: Any) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    for cwd in _workspace_cwds(report):
        suggestions.append(_workspace_context_command_suggestion(cwd))
        suggestions.append(_workspace_launch_command_suggestion(cwd))
    return suggestions


def _goal_action_command_suggestions(
    goal: str | None,
    goal_workspace: str | None,
    *,
    goal_target_name: str | None = None,
) -> list[dict[str, str]]:
    if not goal or not goal_workspace:
        return []
    return [
        _workspace_context_command_suggestion(goal_workspace, query=goal),
        _workspace_launch_command_suggestion(
            goal_workspace,
            prompt=goal,
            target_name=goal_target_name or "planner-session",
        ),
    ]


def _active_goal_action_command_suggestions(
    active_goals: list[dict[str, Any]] | None,
    *,
    running_target_names: set[str] | None = None,
) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    running_names = running_target_names or set()
    for goal in active_goals or []:
        goal_text = goal.get("goal")
        goal_workspace = goal.get("cwd")
        goal_target_name = goal.get("target_name")
        if not isinstance(goal_text, str) or not isinstance(goal_workspace, str):
            continue
        if isinstance(goal_target_name, str) and goal_target_name in running_names:
            continue
        suggestions.extend(
            _goal_action_command_suggestions(
                goal_text,
                goal_workspace,
                goal_target_name=goal_target_name
                if isinstance(goal_target_name, str)
                else None,
            )
        )
    return suggestions


def _running_managed_target_names(report: Any) -> set[str]:
    names: set[str] = set()
    for session in report.sessions:
        name = getattr(session, "managed_name", None)
        if not isinstance(name, str) or not name:
            continue
        if getattr(session, "status", None) != "working":
            continue
        if _session_marks_terminal_done(session):
            continue
        names.add(name)
    return names


def _running_managed_target_names_from_registry(codex_home: Path) -> set[str]:
    names: set[str] = set()
    for record in read_managed_records(default_registry_path(codex_home)):
        if record.backend == "tmux":
            continue
        if _pid_is_running(record.pid):
            names.add(record.name)
    return names


def _workspace_cwds(report: Any) -> list[str]:
    seen: set[str] = set()
    workspaces: list[str] = []
    for session in report.sessions:
        if _session_marks_terminal_done(session):
            continue
        cwd = getattr(session, "cwd", None)
        if not isinstance(cwd, str) or not cwd or cwd in seen:
            continue
        if not _cwd_is_existing_dir(cwd):
            continue
        seen.add(cwd)
        workspaces.append(cwd)
    return workspaces


def _workspace_context_command_suggestion(
    cwd: str,
    *,
    query: str = DEFAULT_CONTEXT_QUERY,
) -> dict[str, str]:
    return {
        "kind": "request_context",
        "label": "让 LLM 先检索项目上下文",
        "cwd": cwd,
        "query": query,
        "command": shlex.join(
            [
                "isotope-supervisor",
                "context",
                "--cwd",
                cwd,
                "--query",
                query,
            ]
        ),
    }


def _workspace_launch_command_suggestion(
    cwd: str,
    *,
    prompt: str = DEFAULT_LAUNCH_PROMPT,
    target_name: str = "planner-session",
) -> dict[str, str]:
    return {
        "kind": "launch_session",
        "label": "让 LLM 启动新的 Codex 会话",
        "target_name": target_name,
        "cwd": cwd,
        "prompt": prompt,
        "command": shlex.join(
            [
                "isotope-supervisor",
                "launch",
                "--name",
                target_name,
                "--cwd",
                cwd,
                "--prompt",
                prompt,
            ]
        ),
    }


def _dedupe_command_suggestions(suggestions: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str | None, str | None, str | None]] = set()
    deduped: list[dict[str, str]] = []
    for suggestion in suggestions:
        key = (
            suggestion.get("kind"),
            suggestion.get("command"),
            suggestion.get("session_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(suggestion)
    return deduped


def _resume_session_command_suggestions(session: Any) -> list[dict[str, str]]:
    if not _is_resume_capable_session(session):
        return []
    return [
        _resume_session_command_suggestion(session, prompt_kind="send_status"),
        _resume_session_command_suggestion(session, prompt_kind="send_continue"),
    ]


def _resume_session_command_suggestion(
    session: Any,
    *,
    prompt_kind: str,
) -> dict[str, str]:
    prompt_text = EXECUTABLE_ADVICE_TEXT[prompt_kind]
    label = (
        "恢复 Codex 历史会话并汇报状态"
        if prompt_kind == "send_status"
        else "恢复 Codex 历史会话并继续推进"
    )
    target_name = _resume_managed_name_for_session(session)
    return {
        "kind": "resume_session",
        "label": label,
        "target_name": target_name,
        "session_id": session.session_id,
        "prompt_kind": prompt_kind,
        "command": shlex.join(
            [
                "isotope-supervisor",
                "resume",
                "--name",
                target_name,
                "--cwd",
                session.cwd,
                "--session-id",
                session.session_id,
                "--prompt",
                prompt_text,
            ]
        ),
    }


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


def _is_active_managed_process_session(session: Any) -> bool:
    return bool(
        getattr(session, "managed", False)
        and getattr(session, "managed_name", None)
        and getattr(session, "managed_backend", None) != "tmux"
        and not _is_completed_session(session)
        and getattr(session, "status", None) != "exited"
    )


def _is_resume_capable_session(session: Any) -> bool:
    session_id = getattr(session, "session_id", None)
    return (
        isinstance(session_id, str)
        and bool(session_id)
        and not session_id.startswith("managed:")
        and bool(getattr(session, "cwd", None))
        and _cwd_is_existing_dir(getattr(session, "cwd", None))
        and not _is_completed_session(session)
    )


def _resume_managed_name_for_session(session: Any) -> str:
    return "resume-" + session.short_session_id


def _is_completed_session(session: Any) -> bool:
    return (
        getattr(session, "status", None) in {"done", "archived"}
        or getattr(session, "supervisor_status", None) == "done"
    )


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
    if _managed_terminal_looks_busy(target):
        return {
            "kind": "monitor",
            "skipped": True,
            "reason": "managed lane is running without ready signal",
            "blocked_kind": kind,
            "command": suggestion["command"],
        }
    if kind == "send_continue":
        if budget_state := continue_budget_state(
            codex_home=Path(args.codex_home),
            name=target.managed_name,
            max_continue_count=args.max_continue_count,
        ):
            return {
                "kind": kind,
                "command": suggestion["command"],
                "skipped": True,
                "reason": "lane continue budget exhausted",
                "lane_state": budget_state.to_dict(),
            }
        if run_budget := _run_budget_state(
            codex_home=Path(args.codex_home),
            name=target.managed_name,
            max_run_minutes=args.max_run_minutes,
        ):
            return {
                "kind": kind,
                "command": suggestion["command"],
                "skipped": True,
                "reason": "lane run budget exhausted",
                "run_budget": run_budget,
            }
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
        prompt_kind=kind,
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


def _context_request_count(payload: dict[str, Any]) -> int:
    count = 0
    for key in ("executed", "followup_executed"):
        item = payload.get(key)
        if (
            isinstance(item, dict)
            and item.get("kind") == "request_context"
            and not item.get("skipped")
        ):
            count += 1
    return count


def _context_request_budget_result(
    args: argparse.Namespace,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    max_requests = getattr(args, "max_context_requests", DEFAULT_MAX_CONTEXT_REQUESTS)
    if max_requests <= 0:
        return None
    count = _context_request_count(payload)
    if count < max_requests:
        return None
    return {
        "kind": "request_context",
        "skipped": True,
        "reason": "context request budget exhausted",
        "context_request_count": count,
        "max_context_requests": max_requests,
    }


def _run_budget_state(
    *,
    codex_home: Path,
    name: str,
    max_run_minutes: int,
) -> dict[str, Any] | None:
    if max_run_minutes <= 0:
        return None
    records = [
        record
        for record in read_managed_records(default_registry_path(codex_home))
        if record.name == name
    ]
    if not records:
        return None
    latest = max(records, key=lambda record: _timestamp_sort_value(record.started_at))
    started_at = _parse_timestamp(latest.started_at)
    if started_at is None:
        return None
    elapsed_seconds = max(0, int((_utc_now() - started_at).total_seconds()))
    if elapsed_seconds < max_run_minutes * 60:
        return None
    return {
        "name": latest.name,
        "record_id": latest.record_id,
        "started_at": latest.started_at,
        "elapsed_seconds": elapsed_seconds,
        "max_run_minutes": max_run_minutes,
    }


def _timestamp_sort_value(value: str) -> float:
    parsed = _parse_timestamp(value)
    return parsed.timestamp() if parsed is not None else 0.0


def _parse_timestamp(value: str) -> datetime | None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return _ensure_aware_utc(datetime.fromisoformat(normalized))
    except ValueError:
        return None


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    if kind == "resume_session":
        if _resume_action_outside_active_goals(payload, action):
            return {
                "kind": "resume_session",
                "skipped": True,
                "reason": "resume session outside active goals",
                "session_id": action.get("session_id"),
            }
        return _execute_resume_action(args, report, action)
    if kind == "launch_session":
        return _execute_launch_action(args, action)
    if kind == "request_context":
        if budget_result := _context_request_budget_result(args, payload):
            return budget_result
        return _execute_context_action(args, action)
    if kind == "ask_user":
        return _execute_ask_user_action(args, action)
    return _execute_advice(
        args,
        report,
        payload,
        kind=kind,
        target_name=action.get("target_name"),
    )


def _resume_action_outside_active_goals(
    payload: dict[str, Any],
    action: dict[str, Any],
) -> bool:
    active_goals = payload.get("active_goals")
    if not isinstance(active_goals, list) or not active_goals:
        return False
    session_id = action.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return False
    allowed_session_ids = _active_goal_resume_session_ids(
        payload.get("command_suggestions"),
        active_goals,
    )
    return session_id not in allowed_session_ids


def _active_goal_resume_session_ids(
    command_suggestions: Any,
    active_goals: list[Any],
) -> set[str]:
    if not isinstance(command_suggestions, list):
        return set()
    goal_names = {
        target_name
        for goal in active_goals
        if isinstance(goal, dict)
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str) and target_name
    }
    allowed: set[str] = set()
    for suggestion in command_suggestions:
        if not isinstance(suggestion, dict) or suggestion.get("kind") != "resume_session":
            continue
        session_id = suggestion.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        target_name = suggestion.get("target_name")
        command = suggestion.get("command")
        targets_goal = (
            isinstance(target_name, str)
            and target_name in goal_names
        ) or (
            isinstance(command, str)
            and any(_command_targets_name(command, name) for name in goal_names)
        )
        if targets_goal:
            allowed.add(session_id)
    return allowed


def _worker_profile_from_args(args: argparse.Namespace) -> str:
    raw = getattr(args, "worker_profile", DEFAULT_WORKER_PROFILE)
    profile = raw if isinstance(raw, str) and raw else DEFAULT_WORKER_PROFILE
    if profile not in WORKER_PROFILE_DEFAULTS:
        supported = ", ".join(WORKER_PROFILE_CHOICES)
        raise ValueError(f"unsupported worker_profile: {profile}; allowed: {supported}")
    return profile


def _worker_profile_for_action(
    args: argparse.Namespace,
    action: dict[str, Any],
) -> str:
    raw = action.get("worker_profile")
    if isinstance(raw, str) and raw:
        if raw not in WORKER_PROFILE_DEFAULTS:
            supported = ", ".join(WORKER_PROFILE_CHOICES)
            raise ValueError(f"unsupported worker_profile: {raw}; allowed: {supported}")
        return raw
    return _worker_profile_from_args(args)


def _worker_profile_defaults(profile: str) -> dict[str, Any]:
    defaults = WORKER_PROFILE_DEFAULTS.get(profile)
    if defaults is None:
        supported = ", ".join(WORKER_PROFILE_CHOICES)
        raise ValueError(f"unsupported worker_profile: {profile}; allowed: {supported}")
    return defaults


def _worker_codex_model(
    args: argparse.Namespace,
    *,
    profile: str | None = None,
) -> str | None:
    if not hasattr(args, "worker_codex_model"):
        return None
    value = getattr(args, "worker_codex_model", None)
    if value is None:
        defaults = _worker_profile_defaults(profile or _worker_profile_from_args(args))
        return str(defaults["model"])
    return value if isinstance(value, str) else None


def _worker_codex_config(
    args: argparse.Namespace,
    *,
    profile: str | None = None,
) -> tuple[str, ...]:
    if not hasattr(args, "worker_codex_config"):
        return ()
    value = getattr(args, "worker_codex_config", None)
    if value is None:
        defaults = _worker_profile_defaults(profile or _worker_profile_from_args(args))
        return tuple(defaults["config"])
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _execute_resume_action(
    args: argparse.Namespace,
    report: Any,
    action: dict[str, Any],
) -> dict[str, Any]:
    session_id = action.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id is required for resume_session")
    target = _target_session(report, session_id)
    if target is None or not _is_resume_capable_session(target):
        raise ValueError(f"no resumable Codex session for: {session_id}")
    prompt_kind = action.get("prompt_kind") or "send_continue"
    if prompt_kind not in EXECUTABLE_ADVICE_KINDS:
        supported = ", ".join(sorted(EXECUTABLE_ADVICE_KINDS))
        raise ValueError(f"resume prompt_kind supports only: {supported}")
    prompt_text = EXECUTABLE_ADVICE_TEXT[str(prompt_kind)]
    suggestion = action.get("command_suggestion") or _resume_session_command_suggestion(
        target,
        prompt_kind=str(prompt_kind),
    )
    target_name = action.get("target_name") or suggestion.get("target_name")
    if not isinstance(target_name, str) or not target_name:
        target_name = _resume_managed_name_for_session(target)
    if running_record := _running_managed_process_for_session(
        codex_home=Path(args.codex_home),
        session=target,
    ):
        return {
            "kind": "resume_session",
            "command": suggestion["command"],
            "skipped": True,
            "reason": "managed process already running",
            "managed": {
                "name": running_record.name,
                "record_id": running_record.record_id,
                "pid": running_record.pid,
                "backend": running_record.backend,
            },
        }
    if not _cwd_is_existing_dir(target.cwd):
        return {
            "kind": "resume_session",
            "command": suggestion["command"],
            "skipped": True,
            "reason": "resume cwd missing",
            "cwd": target.cwd,
        }
    if prompt_kind == "send_continue":
        if budget_state := continue_budget_state(
            codex_home=Path(args.codex_home),
            name=target_name,
            max_continue_count=args.max_continue_count,
        ):
            return {
                "kind": "resume_session",
                "command": suggestion["command"],
                "skipped": True,
                "reason": "lane continue budget exhausted",
                "lane_state": budget_state.to_dict(),
            }
        if run_budget := _run_budget_state(
            codex_home=Path(args.codex_home),
            name=target_name,
            max_run_minutes=args.max_run_minutes,
        ):
            return {
                "kind": "resume_session",
                "command": suggestion["command"],
                "skipped": True,
                "reason": "lane run budget exhausted",
                "run_budget": run_budget,
            }
    if cooldown_state := prompt_cooldown_state(
        codex_home=Path(args.codex_home),
        name=target_name,
        cooldown_seconds=args.prompt_cooldown,
    ):
        return {
            "kind": "resume_session",
            "command": suggestion["command"],
            "skipped": True,
            "reason": "resume prompt cooldown active",
            "lane_state": cooldown_state.to_dict(),
        }
    record = resume_managed_codex(
        codex_home=Path(args.codex_home),
        cwd=Path(target.cwd),
        name=target_name,
        prompt=prompt_text,
        session_id=session_id,
        codex_model=_worker_codex_model(args),
        codex_config=_worker_codex_config(args),
        popen=subprocess.Popen,
    )
    record_lane_prompt(
        codex_home=Path(args.codex_home),
        name=record.name,
        tmux_session=None,
        status=target.supervisor_status or target.status,
        prompt_kind=str(prompt_kind),
    )
    return {
        "kind": "resume_session",
        "command": suggestion["command"],
        "text": prompt_text,
        "managed": {
            "name": record.name,
            "record_id": record.record_id,
            "pid": record.pid,
            "backend": record.backend,
            "resume_session_id": record.resume_session_id,
        },
    }


def _execute_launch_action(
    args: argparse.Namespace,
    action: dict[str, Any],
) -> dict[str, Any]:
    target_name = action.get("target_name")
    cwd = action.get("cwd")
    prompt = action.get("prompt")
    if not isinstance(target_name, str) or not target_name.strip():
        raise ValueError("target_name is required for launch_session")
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("cwd is required for launch_session")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required for launch_session")
    if run_budget := _run_budget_state(
        codex_home=Path(args.codex_home),
        name=target_name,
        max_run_minutes=args.max_run_minutes,
    ):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "lane run budget exhausted",
            "run_budget": run_budget,
        }
    if not _cwd_is_existing_dir(cwd):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "launch cwd missing",
            "cwd": cwd,
        }
    if running_record := _running_managed_process_by_name(
        codex_home=Path(args.codex_home),
        name=target_name,
    ):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "managed process already running",
            "managed": {
                "name": running_record.name,
                "record_id": running_record.record_id,
                "pid": running_record.pid,
                "backend": running_record.backend,
            },
        }
    if cooldown_state := prompt_cooldown_state(
        codex_home=Path(args.codex_home),
        name=target_name,
        cooldown_seconds=args.prompt_cooldown,
    ):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "launch prompt cooldown active",
            "lane_state": cooldown_state.to_dict(),
        }
    worktree = _prepare_launch_worktree(cwd=Path(cwd), target_name=target_name)
    if worktree.get("failed"):
        return {
            "kind": "launch_session",
            "skipped": True,
            "reason": "worktree setup failed",
            "worktree": worktree,
        }
    worker_cwd = str(worktree["cwd"])
    worker_profile = _worker_profile_for_action(args, action)
    work_order_prompt = build_launch_work_order_prompt(
        target_name=target_name,
        cwd=worker_cwd,
        goal=prompt,
    )
    command = shlex.join(
        [
            "isotope-supervisor",
            "launch",
            "--name",
            target_name,
            "--cwd",
            worker_cwd,
            "--prompt",
            work_order_prompt,
        ]
    )
    record = launch_managed_codex(
        codex_home=Path(args.codex_home),
        cwd=Path(worker_cwd),
        name=target_name,
        prompt=work_order_prompt,
        codex_model=_worker_codex_model(args, profile=worker_profile),
        codex_config=_worker_codex_config(args, profile=worker_profile),
        popen=subprocess.Popen,
        run=subprocess.run,
    )
    record_lane_prompt(
        codex_home=Path(args.codex_home),
        name=record.name,
        tmux_session=None,
        status="launch_session",
        prompt_kind="launch_session",
    )
    return {
        "kind": "launch_session",
        "command": command,
        "text": work_order_prompt,
        "worker_profile": worker_profile,
        "managed": {
            "name": record.name,
            "record_id": record.record_id,
            "pid": record.pid,
            "backend": record.backend,
        },
        "worktree": worktree,
    }


def _prepare_launch_worktree(*, cwd: Path, target_name: str) -> dict[str, Any]:
    source_cwd = cwd.expanduser()
    root = _git_root_for_worktree(source_cwd)
    if root is None:
        return {
            "enabled": False,
            "source_cwd": str(source_cwd),
            "cwd": str(source_cwd),
            "reason": "not_git_repo",
        }
    suffix = uuid.uuid4().hex[:8]
    safe_name = _safe_worktree_name(target_name)
    branch = f"supervisor/{safe_name}-{suffix}"
    worktree = root / ".worktrees" / "supervisor" / f"{safe_name}-{suffix}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "worktree",
                "add",
                "-b",
                branch,
                str(worktree),
                "HEAD",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError, TypeError) as exc:
        return {
            "enabled": False,
            "failed": True,
            "source_cwd": str(source_cwd),
            "cwd": str(source_cwd),
            "worktree_root": str(worktree),
            "branch": branch,
            "reason": str(exc),
        }
    if completed.returncode != 0:
        return {
            "enabled": False,
            "failed": True,
            "source_cwd": str(source_cwd),
            "cwd": str(source_cwd),
            "worktree_root": str(worktree),
            "branch": branch,
            "reason": (completed.stderr or completed.stdout or "git worktree add failed").strip(),
        }
    worker_cwd = worktree / _relative_cwd_in_repo(source_cwd, root)
    return {
        "enabled": True,
        "source_cwd": str(source_cwd),
        "cwd": str(worker_cwd),
        "worktree_root": str(worktree),
        "branch": branch,
    }


def _git_root_for_worktree(cwd: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError, TypeError):
        return None
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    return Path(root) if root else None


def _safe_worktree_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip(".-_")
    return safe.lower() or "worker"


def _relative_cwd_in_repo(cwd: Path, root: Path) -> Path:
    try:
        return cwd.resolve().relative_to(root.resolve())
    except ValueError:
        return Path()


def _running_managed_process_by_name(
    *,
    codex_home: Path,
    name: str,
) -> Any | None:
    for record in reversed(read_managed_records(default_registry_path(codex_home))):
        if record.name != name:
            continue
        if record.backend == "tmux":
            continue
        if _pid_is_running(record.pid):
            return record
    return None


def _running_managed_process_for_session(
    *,
    codex_home: Path,
    session: Any,
) -> Any | None:
    session_id = getattr(session, "session_id", None)
    session_cwd = _path_identity(getattr(session, "cwd", None))
    for record in reversed(read_managed_records(default_registry_path(codex_home))):
        if record.backend == "tmux":
            continue
        if not _pid_is_running(record.pid):
            continue
        if isinstance(session_id, str) and record.resume_session_id == session_id:
            return record
        if session_cwd is not None and _path_identity(record.cwd) == session_cwd:
            return record
    return None


def _path_identity(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return str(Path(value).expanduser().resolve(strict=False))


def _cwd_is_existing_dir(value: object) -> bool:
    return isinstance(value, str) and bool(value) and Path(value).expanduser().is_dir()


def _execute_context_action(
    args: argparse.Namespace,
    action: dict[str, Any],
) -> dict[str, Any]:
    cwd = action.get("cwd")
    query = action.get("query")
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("cwd is required for request_context")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required for request_context")
    suggestion = action.get("command_suggestion")
    command = (
        suggestion["command"]
        if isinstance(suggestion, dict) and isinstance(suggestion.get("command"), str)
        else shlex.join(
            [
                "isotope-supervisor",
                "context",
                "--cwd",
                cwd,
                "--query",
                query,
            ]
        )
    )
    if not _cwd_is_existing_dir(cwd):
        return {
            "kind": "request_context",
            "command": command,
            "cwd": cwd,
            "query": query,
            "skipped": True,
            "reason": "request_context cwd missing",
        }
    result = request_project_context(
        codex_home=Path(args.codex_home),
        cwd=Path(cwd),
        query=query,
    )
    return {
        "kind": "request_context",
        "command": command,
        "cwd": cwd,
        "query": query,
        "context": result.to_dict(),
    }


def _execute_ask_user_action(
    args: argparse.Namespace,
    action: dict[str, Any],
) -> dict[str, Any]:
    question = action.get("question")
    session_id = action.get("session_id")
    goal_id = action.get("goal_id")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required for ask_user")
    if not isinstance(session_id, str) or not session_id.strip():
        session_id = (
            f"goal:{goal_id}"
            if isinstance(goal_id, str) and goal_id.strip()
            else None
        )
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is required for ask_user")
    gate = {
        "codex_requested_decision": action.get("codex_requested_decision"),
        "instructions_exhausted": action.get("instructions_exhausted"),
        "context_status": action.get("context_status"),
    }
    decision_request = record_decision_request(
        codex_home=Path(args.codex_home),
        action={**action, "session_id": session_id, "gate": gate},
    )
    return {
        "kind": "ask_user",
        "requires_user": True,
        "session_id": session_id,
        **({"goal_id": goal_id} if isinstance(goal_id, str) and goal_id else {}),
        "target_name": action.get("target_name"),
        "question": question,
        "reason": action["reason"],
        "context_status": action.get("context_status"),
        "gate": gate,
        "decision_request": decision_request.to_dict(),
    }


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
    if executed.get("kind") == "ask_user":
        return True
    return executed.get("kind") != "monitor" and not executed.get("skipped")


def _auto_execute_action(
    report: Any,
    *,
    target_name: str | None = None,
    codex_home: Path | None = None,
    prompt_cooldown_seconds: int = DEFAULT_PROMPT_COOLDOWN_SECONDS,
    max_continue_count: int = DEFAULT_MAX_CONTINUE_COUNT,
    max_run_minutes: int = DEFAULT_MAX_RUN_MINUTES,
) -> dict[str, str]:
    if target_name:
        managed = _managed_tmux_session_by_name(report, target_name)
        if managed is None:
            return {
                "kind": "monitor",
                "reason": f"managed lane not found: {target_name}",
            }
        action = _auto_execute_action_for_managed(report, managed)
        if _auto_action_exhausts_continue_budget(
            action,
            codex_home=codex_home,
            managed=managed,
            max_continue_count=max_continue_count,
        ):
            return {
                "kind": "monitor",
                "reason": "lane continue budget exhausted",
                "target_name": managed.managed_name or target_name,
            }
        if _auto_action_exhausts_run_budget(
            action,
            codex_home=codex_home,
            managed=managed,
            max_run_minutes=max_run_minutes,
        ):
            return {
                "kind": "monitor",
                "reason": "lane run budget exhausted",
                "target_name": managed.managed_name or target_name,
            }
        return action
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
    continue_budget_candidates: list[dict[str, str]] = []
    for action, managed in candidates:
        if action["kind"] not in EXECUTABLE_ADVICE_KINDS:
            continue
        if _auto_action_exhausts_continue_budget(
            action,
            codex_home=codex_home,
            managed=managed,
            max_continue_count=max_continue_count,
        ):
            continue_budget_candidates.append(
                {
                    "kind": "monitor",
                    "reason": "lane continue budget exhausted",
                    **({"target_name": managed.managed_name} if managed.managed_name else {}),
                }
            )
            continue
        if _auto_action_exhausts_run_budget(
            action,
            codex_home=codex_home,
            managed=managed,
            max_run_minutes=max_run_minutes,
        ):
            continue_budget_candidates.append(
                {
                    "kind": "monitor",
                    "reason": "lane run budget exhausted",
                    **({"target_name": managed.managed_name} if managed.managed_name else {}),
                }
            )
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
    if continue_budget_candidates:
        return continue_budget_candidates[0]
    return candidates[0][0]


def _auto_action_exhausts_continue_budget(
    action: dict[str, str],
    *,
    codex_home: Path | None,
    managed: Any,
    max_continue_count: int,
) -> bool:
    if (
        action["kind"] != "send_continue"
        or codex_home is None
        or not managed.managed_name
    ):
        return False
    return (
        continue_budget_state(
            codex_home=codex_home,
            name=managed.managed_name,
            max_continue_count=max_continue_count,
        )
        is not None
    )


def _auto_action_exhausts_run_budget(
    action: dict[str, str],
    *,
    codex_home: Path | None,
    managed: Any,
    max_run_minutes: int,
) -> bool:
    if (
        action["kind"] != "send_continue"
        or codex_home is None
        or not managed.managed_name
    ):
        return False
    return (
        _run_budget_state(
            codex_home=codex_home,
            name=managed.managed_name,
            max_run_minutes=max_run_minutes,
        )
        is not None
    )


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
    if not _has_llm_action_target(report, payload.get("command_suggestions")):
        return generate_llm_action_decision(
            report,
            payload["command_suggestions"],
            _UnavailableSummaryProvider(),
            payload.get("recent_context_results"),
            payload.get("active_goals"),
            payload.get("recent_decision_answers"),
            payload.get("worker_reviews"),
        )
    try:
        provider = resolve_summary_provider_from_env(agent_name="supervisor")
        return generate_llm_action_decision(
            report,
            payload["command_suggestions"],
            provider,
            payload.get("recent_context_results"),
            payload.get("active_goals"),
            payload.get("recent_decision_answers"),
            payload.get("worker_reviews"),
        )
    except ValueError as exc:
        error = str(exc)
        reason = f"LLM 动作无效，已跳过执行：{error}"
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": reason,
            "command_suggestion": None,
            "error": error,
        }


def _recent_context_results(args: argparse.Namespace, report: Any) -> list[dict[str, Any]]:
    cwd = _context_cwd_for_report(report) or _goal_workspace(args)
    results = read_recent_context_results(
        codex_home=Path(args.codex_home),
        cwd=Path(cwd) if cwd else None,
    )
    return [result.to_dict() for result in results]


def _decision_request_dicts(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        request.to_dict()
        for request in read_active_decision_requests(codex_home=Path(args.codex_home))
    ]


def _decision_answer_dicts(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        dict(answer)
        for answer in read_recent_decision_answers(codex_home=Path(args.codex_home))
    ]


def _worker_review_context(args: argparse.Namespace) -> dict[str, Any]:
    return collect_worker_reviews(codex_home=Path(args.codex_home))


def _active_goal_dicts(
    args: argparse.Namespace,
    *,
    limit: int = 20,
    include_status: bool = False,
) -> list[dict[str, Any]]:
    return _active_goal_dicts_for_codex_home(
        Path(args.codex_home),
        limit=limit,
        include_status=include_status,
    )


def _active_goal_dicts_for_codex_home(
    codex_home: Path,
    *,
    limit: int = 20,
    include_status: bool = False,
) -> list[dict[str, Any]]:
    statuses = (
        read_latest_supervisor_goal_statuses(codex_home=codex_home)
        if include_status
        else {}
    )
    return [
        _goal_dict_with_status(goal.to_dict(), statuses)
        for goal in read_active_supervisor_goals(
            codex_home=codex_home,
            limit=limit,
        )
    ]


def _goal_dict_with_status(
    goal: dict[str, Any],
    statuses: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status = statuses.get(goal.get("goal_id"))
    if not status:
        return goal
    merged = {**goal}
    for key, value in status.items():
        if key != "goal_id":
            merged[key] = value
    return merged


def _context_cwd_for_report(report: Any) -> str | None:
    for session in report.sessions:
        cwd = getattr(session, "cwd", None)
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


class _UnavailableSummaryProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        raise AssertionError("LLM provider should not be called without Supervisor context")


def _has_llm_action_target(
    report: Any,
    command_suggestions: Any = None,
) -> bool:
    if any(
        (
            session.managed_name
            and session.managed_tmux_session
            and not _session_marks_terminal_done(session)
        )
        or _is_resume_capable_session(session)
        for session in report.sessions
    ):
        return True
    if _context_cwd_for_actionable_report(report) is not None:
        return True
    if not isinstance(command_suggestions, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("kind") in {"request_context", "launch_session"}
        and isinstance(item.get("cwd"), str)
        for item in command_suggestions
    )


def _session_marks_terminal_done(session: Any) -> bool:
    return _is_completed_session(session) and _supervisor_next_marks_terminal_done(session)


def _context_cwd_for_actionable_report(report: Any) -> str | None:
    for session in report.sessions:
        if _session_marks_terminal_done(session):
            continue
        cwd = getattr(session, "cwd", None)
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


if __name__ == "__main__":
    raise SystemExit(main())
