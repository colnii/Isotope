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
    build_supervisor_daemon_night_summary,
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
    DEFAULT_DECISION_TIMEOUT_SECONDS,
    archive_decision_request,
    mark_stale_decision_request_timeouts,
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
from .fanout import (
    DEFAULT_FANOUT_LIMIT,
    build_fanout_launch_plan,
    build_fanout_status_summary,
)
from .failure_ledger import FailureLedger, default_failure_ledger_path
from .goal_queue import (
    GOAL_STATUS_VALUES,
    archive_supervisor_goal,
    build_supervisor_goal_queue_view,
    read_latest_supervisor_goal_statuses,
    read_active_supervisor_goals,
    record_supervisor_goal,
    record_supervisor_goal_status,
)
from .goal_planner import plan_supervisor_goals
from .integration_review import (
    collect_integration_reviews,
    review_managed_record_integration,
)
from .lane_state import (
    DEFAULT_MAX_CONTINUE_COUNT,
    DEFAULT_PROMPT_COOLDOWN_SECONDS,
    default_lane_state_path,
    continue_budget_state,
    lane_failure_state,
    prompt_cooldown_state,
    read_lane_states,
    record_lane_failure,
    record_lane_prompt,
    record_worker_retry,
)
from .llm_summary import (
    generate_llm_action_decision,
    generate_llm_summary,
    resolve_summary_provider_from_env,
)
from .merge_dispatch import (
    DEFAULT_TARGET_NAME as MERGE_DISPATCH_TARGET_NAME,
    build_merge_dispatch_launch_spec,
)
from .notifications import (
    notify_merge_worker_auto_archived,
    notify_worker_integration_review_passed,
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
from .commands.main import run_cli as _run_cli
from .commands.parser import build_parser as _build_parser
from .commands.cleanup import (
    auto_archive_done_merge_workers as _auto_archive_done_merge_workers,
    archive_cleanup_candidate as _archive_cleanup_candidate,
    cleanup_archive_command as _cleanup_archive_command,
    cleanup_candidate_dicts as _cleanup_candidate_dicts,
    cleanup_delete_worktree_command as _cleanup_delete_worktree_command,
    cleanup_goal_candidates as _cleanup_goal_candidates,
    cleanup_managed_worker_candidates as _cleanup_managed_worker_candidates,
    cleanup_notification_candidates as _cleanup_notification_candidates,
    cleanup_payload as _cleanup_payload,
    cleanup_worktree_candidate_dicts as _cleanup_worktree_candidate_dicts,
    drop_none_values as _drop_none_values,
    handle_cleanup_command as _handle_cleanup_command,
    managed_record_is_still_working as _managed_record_is_still_working,
    managed_record_status_excerpt as _managed_record_status_excerpt,
    managed_record_supervisor_protocol as _managed_record_supervisor_protocol,
    print_cleanup_plain as _print_cleanup_plain,
    select_cleanup_candidates as _select_cleanup_candidates,
)
from .commands.dashboard import handle_dashboard_command as _handle_dashboard_command
from .commands.goal import (
    active_goal_dicts_with_managed_protocol_status as _active_goal_dicts_with_managed_protocol_status,
    goal_command_goal_text as _goal_command_goal_text,
    goal_payload as _goal_payload,
    goal_queue_view as _goal_queue_view,
    handle_goal_command as _handle_goal_command,
    managed_protocol_statuses_by_name as _managed_protocol_statuses_by_name,
    optional_text as _optional_text,
    print_goal_plain as _print_goal_plain,
    print_goal_queue_view_plain as _print_goal_queue_view_plain,
)
from .commands.merge import (
    handle_integration_review_command as _handle_integration_review_command,
    handle_merge_work_order_command as _handle_merge_work_order_command,
)
from .commands.promotion import (
    auto_promote_done_merge_workers_to_main as _auto_promote_done_merge_workers_to_main,
)
from .planner.goal_scope import (
    _explicit_goal_text,
    _explicit_goal_workspace,
    _goal_target_name,
    _goal_text,
    _goal_workspace,
)
from .state.time_utils import (
    _ensure_aware_utc,
    _parse_timestamp,
    _timestamp_sort_value,
    _utc_now,
)
from .state.memory_view import (
    build_memory_status_payload,
    render_memory_status_plain,
)
from .state.multi_worker import (
    build_multi_worker_status_payload,
    render_multi_worker_status_plain,
)
from .state.worker_event_channel import (
    list_worker_events,
    publish_worker_event,
    render_worker_event_channel_plain,
)

EXECUTABLE_ADVICE_KINDS = {"send_status", "send_continue"}
MERGE_DISPATCH_WORKER_ROLE = "merge_dispatch"
MERGE_REPAIR_WORKER_ROLE = "merge_repair"
RECURSIVE_WORKER_ROLES = {MERGE_DISPATCH_WORKER_ROLE, MERGE_REPAIR_WORKER_ROLE, "cleanup"}
DEFAULT_MAX_CONTEXT_REQUESTS = 0
DEFAULT_MAX_FAILURE_RETRIES = 3
DEFAULT_MAX_RUN_MINUTES = 0
DEFAULT_MAX_WORKER_RETRY_COUNT = 2
DEFAULT_WORKER_CODEX_MODEL = "gpt-5.5"
DEFAULT_WORKER_CODEX_CONFIG = ('model_reasoning_effort="high"',)
DEFAULT_WORKER_PROFILE = "coding"
_MERGE_PROMOTION_DECISION_QUESTION = (
    "merge promotion 失败：是否修复 CI/工作区后重试，还是放弃本次 merge worker？"
)
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
DEFAULT_GOAL_REPLENISH_PROMPT = " ".join(
    [
        "根据 AGENTS.md、docs/current/status.md、docs/current/agent-task-queue.md",
        "和 docs/current/supervisor-capability-map.md，",
        "为 Supervisor/Isotope 当前目标继续规划下一批可并行、可验证的 Codex worker 任务。",
        "优先选择能推动长跑自动开发闭环、低冲突、完成后可独立提交的目标；",
        "只有满足拍板条件才生成需要用户决策的任务。",
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


def _json_object_arg(raw: str | None, field_name: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def _add_goal_replenishment_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--goal-low-water",
        type=int,
        default=0,
        help=(
            "When active goals fall below this count, ask LLM to plan more goals "
            "from current docs. Default 0 disables."
        ),
    )
    parser.add_argument(
        "--goal-replenish-limit",
        type=int,
        default=DEFAULT_FANOUT_LIMIT,
        help="Maximum goals the LLM low-water planner may write in one loop.",
    )
    parser.add_argument(
        "--goal-replenish-prompt",
        help="Optional seed prompt for low-water goal planning.",
    )


def _add_failure_retry_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-failure-retries",
        type=int,
        default=DEFAULT_MAX_FAILURE_RETRIES,
        help=(
            "Maximum repeated Supervisor failures before creating a decision "
            "request. Default 3."
        ),
    )


def _add_webhook_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--webhook-url",
        help="HTTP endpoint for low-sensitive Supervisor event POSTs.",
    )
    parser.add_argument(
        "--webhook-secret",
        help="Optional shared secret for X-Isotope-Signature HMAC headers.",
    )


def _build_parser_impl() -> argparse.ArgumentParser:
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
        if command == "supervise":
            _add_webhook_args(subparser)
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
        if command == "supervise":
            _add_failure_retry_args(subparsers.choices[command])
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
        if command == "supervise":
            subparsers.choices[command].add_argument(
                "--max-worker-retry-count",
                type=int,
                default=DEFAULT_MAX_WORKER_RETRY_COUNT,
                help=(
                    "Maximum automatic restarts for an exited process worker. "
                    "Default 2."
                ),
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
    _add_webhook_args(loop_parser)
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
        "--decision-timeout",
        type=int,
        default=DEFAULT_DECISION_TIMEOUT_SECONDS,
        help="Seconds before an active decision request raises a timeout alert.",
    )
    _add_failure_retry_args(loop_parser)
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
        "--max-worker-retry-count",
        type=int,
        default=DEFAULT_MAX_WORKER_RETRY_COUNT,
        help="Maximum automatic restarts for an exited process worker. Default 2.",
    )
    _add_goal_replenishment_args(loop_parser)
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
    loop_parser.add_argument(
        "--merge-dispatch-execute",
        action="store_true",
        help=(
            "Actually launch merge-dispatch workers from ready_to_integrate. "
            "Default loop only reports the launch action."
        ),
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
        "--decision-timeout",
        type=int,
        default=DEFAULT_DECISION_TIMEOUT_SECONDS,
        help="Seconds before an active decision request raises a timeout alert.",
    )
    _add_failure_retry_args(up_parser)
    up_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
    )
    up_parser.add_argument(
        "--max-fanout-launches",
        type=int,
        default=DEFAULT_FANOUT_LIMIT,
        help="Maximum launch_session actions fanout may execute in one loop iteration.",
    )
    _add_goal_replenishment_args(up_parser)
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
    _add_webhook_args(up_parser)
    up_parser.add_argument(
        "--no-auto-adopt",
        action="store_false",
        dest="auto_adopt",
        help="Disable automatic adoption of discovered Codex-like tmux sessions.",
    )
    up_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    up_parser.set_defaults(auto_adopt=True)
    for check_command, help_text in (
        (
            "check",
            "Print one read-only morning summary across daemon, goals, review, and cleanup.",
        ),
        (
            "overnight-check",
            "Alias for check; useful after an overnight Supervisor run.",
        ),
    ):
        check_parser = subparsers.add_parser(check_command, help=help_text)
        check_parser.add_argument(
            "--codex-home",
            default=str(Path.home() / ".codex"),
            help="Codex home directory. Defaults to ~/.codex.",
        )
        check_parser.add_argument(
            "--base",
            default="main",
            help="Base branch/ref for integration-review. Defaults to main.",
        )
        check_parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
        "--decision-timeout",
        type=int,
        default=DEFAULT_DECISION_TIMEOUT_SECONDS,
        help="Seconds before an active decision request raises a timeout alert.",
    )
    _add_failure_retry_args(daemon_start_parser)
    daemon_start_parser.add_argument(
        "--max-run-minutes",
        type=int,
        default=DEFAULT_MAX_RUN_MINUTES,
        help="Maximum elapsed minutes before send_continue is blocked for a lane. Default 0 disables.",
    )
    daemon_start_parser.add_argument(
        "--max-fanout-launches",
        type=int,
        default=DEFAULT_FANOUT_LIMIT,
        help="Maximum launch_session actions fanout may execute in one loop iteration.",
    )
    _add_goal_replenishment_args(daemon_start_parser)
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
    _add_webhook_args(daemon_start_parser)
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
    launch_parser.add_argument(
        "--worker-role",
        default="worker",
        help="Worker role stored in the managed registry. Defaults to worker.",
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
    memory_parser = subparsers.add_parser(
        "memory",
        help="Show a low-sensitive summary of local memory records.",
    )
    memory_parser.add_argument(
        "--root",
        default=".",
        help="Runtime root containing memory/*.json. Defaults to current directory.",
    )
    memory_parser.add_argument(
        "--scope",
        choices=("thread", "run", "session"),
        help="Only show one memory scope.",
    )
    memory_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum records to preview.",
    )
    memory_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    worker_event_parser = subparsers.add_parser(
        "worker-event",
        help="Publish or list memory-backed worker events.",
    )
    worker_event_subparsers = worker_event_parser.add_subparsers(
        dest="worker_event_command",
        required=True,
    )
    worker_event_publish = worker_event_subparsers.add_parser(
        "publish",
        help="Publish one worker event into the memory-backed channel.",
    )
    worker_event_publish.add_argument(
        "--root",
        default=".",
        help="Runtime root containing memory/*.json. Defaults to current directory.",
    )
    worker_event_publish.add_argument("--from", dest="from_worker", required=True)
    worker_event_publish.add_argument("--to", dest="to_worker")
    worker_event_publish.add_argument("--type", dest="event_type", default="message")
    worker_event_publish.add_argument("--channel", default="default")
    worker_event_publish.add_argument("--message", required=True)
    worker_event_publish.add_argument(
        "--payload-json",
        help="Optional JSON object payload for the event.",
    )
    worker_event_publish.add_argument("--json", action="store_true", help="Print JSON output.")
    worker_event_list = worker_event_subparsers.add_parser(
        "list",
        help="List worker events from the memory-backed channel.",
    )
    worker_event_list.add_argument(
        "--root",
        default=".",
        help="Runtime root containing memory/*.json. Defaults to current directory.",
    )
    worker_event_list.add_argument("--from", dest="from_worker")
    worker_event_list.add_argument("--to", dest="to_worker")
    worker_event_list.add_argument("--type", dest="event_type")
    worker_event_list.add_argument("--channel")
    worker_event_list.add_argument("--limit", type=int, default=20)
    worker_event_list.add_argument("--json", action="store_true", help="Print JSON output.")
    worker_manager_parser = subparsers.add_parser(
        "worker-manager",
        help="Show a memory-backed multi-worker status view.",
    )
    worker_manager_parser.add_argument(
        "--root",
        default=".",
        help="Runtime root containing memory/*.json. Defaults to current directory.",
    )
    worker_manager_parser.add_argument("--worker", help="Only show one worker.")
    worker_manager_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum workers to preview.",
    )
    worker_manager_parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
        "--include-missing-worktrees",
        action="store_true",
        help="Also include stale records whose worktree is already missing.",
    )
    integration_review_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    _add_webhook_args(integration_review_parser)
    merge_work_order_parser = subparsers.add_parser(
        "merge-work-order",
        help="Build a read-only merge work order from integration-review.",
    )
    merge_work_order_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    merge_work_order_parser.add_argument(
        "--base",
        default="main",
        help="Base branch/ref to check containment against. Defaults to main.",
    )
    merge_work_order_parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
    _add_webhook_args(decision_subparsers.choices["answer"])
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
    goal_subparsers.choices["archive"].add_argument(
        "--status",
        choices=sorted(GOAL_STATUS_VALUES),
        help="Optional final Supervisor status to store on the archive event.",
    )
    goal_subparsers.choices["archive"].add_argument(
        "--summary",
        help="Optional completion summary to store on the archive event.",
    )
    goal_subparsers.choices["archive"].add_argument(
        "--next-step",
        help="Optional next step to store as next on the archive event.",
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
        ("delete-worktree", "Remove one archived and integrated Supervisor worktree."),
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
    cleanup_delete_worktree_parser = cleanup_subparsers.choices["delete-worktree"]
    cleanup_delete_worktree_parser.add_argument(
        "--name",
        required=True,
        help="Managed worker name whose worktree should be removed.",
    )
    cleanup_delete_worktree_parser.add_argument(
        "--record-id",
        help="Managed record id to guard against deleting a newer worker.",
    )
    cleanup_delete_worktree_parser.add_argument(
        "--base",
        default="main",
        help="Base ref used for integration confirmation. Defaults to main.",
    )
    cleanup_delete_worktree_parser.add_argument(
        "--confirm-delete-worktree",
        action="store_true",
        help="Required confirmation before removing the worktree.",
    )
    trace_parser = subparsers.add_parser(
        "trace",
        help="Print a read-only Supervisor lifecycle trace.",
    )
    trace_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    trace_parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
    start_here_parser = subparsers.add_parser(
        "start-here",
        help="Print the shortest human-first Supervisor trial workflow.",
    )
    start_here_parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    start_here_parser.add_argument(
        "--cwd",
        default=str(Path.cwd()),
        help="Workspace directory. Defaults to the current directory.",
    )
    start_here_parser.add_argument(
        "--goal",
        default="让 Supervisor 根据当前项目文档继续推进下一步可验证任务。",
        help="The first goal to hand to Supervisor.",
    )
    start_here_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Web dashboard host used in the printed command.",
    )
    start_here_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Web dashboard port used in the printed command.",
    )
    start_here_parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
    return _run_cli(argv)


_COMMAND_HANDLERS = {
    "dashboard": _handle_dashboard_command,
    "integration-review": _handle_integration_review_command,
    "merge-work-order": _handle_merge_work_order_command,
    "goal": _handle_goal_command,
    "cleanup": _handle_cleanup_command,
}


def _run_cli_impl(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            _print_report(args)
            return 0
        if args.command in _COMMAND_HANDLERS:
            return _COMMAND_HANDLERS[args.command](args, api=sys.modules[__name__])
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
        if args.command in {"check", "overnight-check"}:
            payload = _overnight_check_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_overnight_check_plain(payload)
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
                worker_role=getattr(args, "worker_role", "worker"),
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
        if args.command == "memory":
            payload = build_memory_status_payload(
                root=Path(args.root),
                scope=args.scope,
                limit=args.limit,
            )
            if args.json:
                _print_json(payload)
            else:
                print(render_memory_status_plain(payload))
            return 0
        if args.command == "worker-event":
            if args.worker_event_command == "publish":
                payload = publish_worker_event(
                    root=Path(args.root),
                    from_worker=args.from_worker,
                    to_worker=args.to_worker,
                    event_type=args.event_type,
                    channel=args.channel,
                    message=args.message,
                    payload=_json_object_arg(args.payload_json, "payload-json"),
                )
                if args.json:
                    _print_json(payload)
                else:
                    print(render_worker_event_channel_plain({"store": payload["store"], "events": [payload["event"]]}))
                return 0
            if args.worker_event_command == "list":
                payload = list_worker_events(
                    root=Path(args.root),
                    channel=args.channel,
                    from_worker=args.from_worker,
                    to_worker=args.to_worker,
                    event_type=args.event_type,
                    limit=args.limit,
                )
                if args.json:
                    _print_json(payload)
                else:
                    print(render_worker_event_channel_plain(payload))
                return 0
        if args.command == "worker-manager":
            payload = build_multi_worker_status_payload(
                root=Path(args.root),
                worker=args.worker,
                limit=args.limit,
            )
            if args.json:
                _print_json(payload)
            else:
                print(render_multi_worker_status_plain(payload))
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
        if args.command == "trace":
            payload = _lifecycle_trace_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_lifecycle_trace_plain(payload)
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
        if args.command == "start-here":
            payload = _start_here_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_start_here_plain(payload)
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
    if args.decision_timeout < 0:
        raise ValueError("decision_timeout must be zero or positive")
    if args.max_failure_retries < 0:
        raise ValueError("max_failure_retries must be zero or positive")
    if args.max_run_minutes < 0:
        raise ValueError("max_run_minutes must be zero or positive")
    if args.max_fanout_launches <= 0:
        raise ValueError("max_fanout_launches must be positive")
    if getattr(args, "goal_low_water", 0) < 0:
        raise ValueError("goal_low_water must be zero or positive")
    if getattr(args, "goal_replenish_limit", 1) <= 0:
        raise ValueError("goal_replenish_limit must be positive")
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
        decision_timeout=args.decision_timeout,
        max_failure_retries=args.max_failure_retries,
        max_run_minutes=args.max_run_minutes,
        max_fanout_launches=args.max_fanout_launches,
        goal_low_water=args.goal_low_water,
        goal_replenish_limit=args.goal_replenish_limit,
        goal_replenish_prompt=args.goal_replenish_prompt,
        name=args.name,
        goal=None,
        llm_summary=args.llm_summary,
        auto_adopt=args.auto_adopt,
        worker_codex_model=_worker_codex_model(args, profile=worker_profile),
        worker_codex_config=_worker_codex_config(args, profile=worker_profile),
        webhook_url=args.webhook_url,
        webhook_secret=args.webhook_secret,
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
    _sync_managed_worker_failures(
        codex_home=codex_home,
        max_run_minutes=_max_run_minutes_from_daemon_command(daemon),
    )
    recent_ci = _recent_ci_from_log(daemon_log)
    recent_execution = _recent_execution_from_log(daemon_log)
    recent_worker = _recent_worker_payload(codex_home)
    active_goals = _active_goal_dicts_for_codex_home(
        codex_home,
        include_status=True,
    )
    managed_workers = _daemon_managed_worker_payloads(codex_home)
    integration_reviews = _daemon_integration_reviews(codex_home)
    activity: dict[str, Any] = {
        "recent_llm_action": _recent_llm_action_from_log(daemon_log),
        "recent_ci": recent_ci,
        "recent_execution": recent_execution,
        "recent_worker": recent_worker,
        "night_summary": build_supervisor_daemon_night_summary(
            active_goals=active_goals,
            managed_workers=managed_workers,
            integration_reviews=integration_reviews,
            recent_ci=recent_ci,
            recent_execution=recent_execution,
            recent_worker=recent_worker,
            merge_worker_name=MERGE_DISPATCH_TARGET_NAME,
        ),
    }
    if active_goals:
        activity["active_goals"] = active_goals
    return activity


def _max_run_minutes_from_daemon_command(daemon: dict[str, Any]) -> int:
    command = daemon.get("command")
    if not isinstance(command, list):
        return 0
    for index, item in enumerate(command):
        if item != "--max-run-minutes" or index + 1 >= len(command):
            continue
        try:
            return max(0, int(command[index + 1]))
        except (TypeError, ValueError):
            return 0
    return 0


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


def _recent_ci_from_log(text: str) -> dict[str, str] | None:
    recent: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("CI："):
            recent = _status_detail_from_text(line.removeprefix("CI：").strip())
        elif line.startswith("CI:"):
            recent = _status_detail_from_text(line.removeprefix("CI:").strip())
    return recent


def _status_detail_from_text(text: str) -> dict[str, str]:
    if " / " in text:
        status, detail = text.split(" / ", 1)
    else:
        status, detail = text, ""
    return {"status": status.strip(), "detail": detail.strip()}


def _daemon_integration_reviews(codex_home: Path) -> dict[str, Any]:
    try:
        return collect_integration_reviews(
            codex_home=codex_home,
            base_ref="main",
            include_unfinished=False,
            run_test_gate=False,
            run_candidate_validation=False,
        )
    except Exception as exc:  # pragma: no cover - defensive status surface
        return {
            "status": "error",
            "error": str(exc),
            "summary": {"ready_to_integrate": 0},
        }


def _daemon_managed_worker_payloads(codex_home: Path) -> list[dict[str, Any]]:
    return [
        _daemon_managed_worker_payload(codex_home=codex_home, record=record)
        for record in read_managed_records(default_registry_path(codex_home))
    ]


def _daemon_managed_worker_payload(*, codex_home: Path, record: Any) -> dict[str, Any]:
    model, config = _codex_worker_options_from_command(record.command)
    protocol = _supervisor_protocol_from_text(
        _managed_process_log_excerpt(record.log_path) or ""
    )
    status = protocol.get("status") or record.status
    process_running = (
        _pid_is_running(record.pid)
        if record.backend != "tmux" and record.pid
        else None
    )
    failure = _lane_failure_payload(codex_home=codex_home, record=record)
    if failure is not None:
        status = "error"
    if (
        record.backend != "tmux"
        and status in {"launched", "resumed", "working"}
        and not process_running
    ):
        status = "exited"
    return {
        "name": record.name,
        "record_id": record.record_id,
        "backend": record.backend,
        "pid": record.pid,
        "process_running": process_running,
        "model": model,
        "config": config,
        "status": status,
        "summary": protocol.get("summary"),
        "next": protocol.get("next"),
        "log_path": record.log_path,
        **({"failure": failure} if failure is not None else {}),
    }


def _recent_worker_payload(codex_home: Path) -> dict[str, Any] | None:
    workers = _daemon_managed_worker_payloads(codex_home)
    if not workers:
        return None
    return workers[-1]


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


def _overnight_check_payload(args: argparse.Namespace) -> dict[str, Any]:
    codex_home = Path(args.codex_home)
    daemon = supervisor_daemon_status(codex_home=codex_home)
    daemon["activity"] = _daemon_activity_payload(codex_home, daemon)
    watcher = supervisor_watcher_status(codex_home=codex_home)
    goals = {
        "status": "ok",
        "active_goals": _active_goal_dicts_for_codex_home(
            codex_home,
            include_status=True,
        ),
    }
    integration_review = collect_integration_reviews(
        codex_home=codex_home,
        base_ref=args.base,
        include_unfinished=True,
    )
    cleanup = {
        "status": "ok",
        "candidates": _cleanup_candidate_dicts(codex_home),
    }
    integration_summary = integration_review.get("summary") or {}
    return {
        "status": "ok",
        "summary": {
            "daemon_status": daemon.get("status"),
            "watcher_status": watcher.get("status"),
            "active_goals": len(goals["active_goals"]),
            "integration_review": {
                "total": integration_summary.get("total", 0),
                "ready_to_integrate": integration_summary.get("ready_to_integrate", 0),
                "already_integrated": integration_summary.get("already_integrated", 0),
                "needs_review": integration_summary.get("needs_review", 0),
                "conflict_risk": integration_summary.get("conflict_risk", 0),
            },
            "cleanup_candidates": len(cleanup["candidates"]),
        },
        "daemon": daemon,
        "watcher": watcher,
        "goals": goals,
        "integration_review": integration_review,
        "cleanup": cleanup,
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
    ci = activity.get("recent_ci")
    execution = activity.get("recent_execution")
    worker = activity.get("recent_worker")
    active_goals = activity.get("active_goals")
    night_summary = activity.get("night_summary")
    if (
        not action
        and not ci
        and not execution
        and not worker
        and not active_goals
        and not night_summary
    ):
        return
    print("最近活动：")
    if isinstance(night_summary, dict):
        merge_label = "运行中" if night_summary.get("merge_worker_running") else "未运行"
        print(
            "夜间摘要：active goals {active_goals} / running workers {running_workers} / "
            "ready_to_integrate {ready_to_integrate} / merge worker {merge_label}".format(
                active_goals=night_summary.get("active_goals", 0),
                running_workers=night_summary.get("running_workers", 0),
                ready_to_integrate=night_summary.get("ready_to_integrate", 0),
                merge_label=merge_label,
            )
        )
    if isinstance(action, dict):
        print(f"LLM 动作：{action.get('kind') or '未知'} / {action.get('reason') or '无'}")
    if isinstance(ci, dict):
        print(f"CI：{ci.get('status') or 'unknown'} / {ci.get('detail') or '无'}")
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


def _print_overnight_check_plain(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    integration = summary["integration_review"]
    print("[Codex Supervisor overnight check]")
    print(f"daemon：{summary['daemon_status']}")
    print(f"watcher：{summary['watcher_status']}")
    print(f"活跃目标：{summary['active_goals']}")
    print(
        "integration-review："
        f"total={integration['total']} "
        f"ready={integration['ready_to_integrate']} "
        f"integrated={integration['already_integrated']} "
        f"review={integration['needs_review']} "
        f"conflict={integration['conflict_risk']}"
    )
    print(f"可归档项：{summary['cleanup_candidates']}")


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
    decision_timeout = getattr(
        args,
        "decision_timeout",
        DEFAULT_DECISION_TIMEOUT_SECONDS,
    )
    if decision_timeout < 0:
        raise ValueError("decision_timeout must be zero or positive")
    iterations = args.iterations
    count = 0
    previous_fingerprint: tuple[object, ...] | None = None
    previous_bell_fingerprint: tuple[object, ...] | None = None
    while iterations is None or count < iterations:
        auto_adopted = _auto_adopt_discovered_tmux_sessions(args)
        auto_retried_workers = _auto_retry_exited_process_workers(args)
        report = _scan_report(args)
        goal_updates = _sync_goal_lifecycle(args, report)
        merge_promotions = _auto_promote_done_merge_workers_to_main(args)
        cleanup_archived = _auto_archive_done_merge_workers(args)
        cleanup_deleted_worktrees = _auto_delete_archived_worktrees_after_cleanup(
            args,
            cleanup_archived=cleanup_archived,
        )
        decision_timeout_alerts = mark_stale_decision_request_timeouts(
            codex_home=Path(args.codex_home),
            timeout_seconds=decision_timeout,
            webhook_url=getattr(args, "webhook_url", None),
            webhook_secret=getattr(args, "webhook_secret", None),
        )
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
                    auto_retried_workers=auto_retried_workers,
                    goal_updates=goal_updates,
                    merge_promotions=merge_promotions,
                    cleanup_archived=cleanup_archived,
                    cleanup_deleted_worktrees=cleanup_deleted_worktrees,
                    decision_timeout_alerts=decision_timeout_alerts,
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
            or bool(auto_retried_workers)
            or bool(goal_updates)
            or bool(merge_promotions)
            or bool(cleanup_archived)
            or bool(cleanup_deleted_worktrees)
            or bool(decision_timeout_alerts)
        )
        if should_print:
            payload = precomputed_payload or _supervise_payload(
                args,
                report,
                iteration=count + 1,
                auto_adopted=auto_adopted,
                auto_retried_workers=auto_retried_workers,
                precomputed_auto_action=precomputed_auto_action,
                precomputed_executed=precomputed_executed,
                goal_updates=goal_updates,
                merge_promotions=merge_promotions,
                cleanup_archived=cleanup_archived,
                cleanup_deleted_worktrees=cleanup_deleted_worktrees,
                decision_timeout_alerts=decision_timeout_alerts,
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
    _sync_managed_worker_failures(
        codex_home=Path(args.codex_home),
        max_run_minutes=getattr(args, "max_run_minutes", 0),
    )
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


def _sync_managed_worker_failures(
    *,
    codex_home: Path,
    max_run_minutes: int = 0,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for record in read_managed_records(default_registry_path(codex_home)):
        if record.backend == "tmux":
            continue
        failure = _managed_worker_failure_from_record(
            record,
            max_run_minutes=max_run_minutes,
        )
        if failure is None:
            continue
        state = record_lane_failure(
            codex_home=codex_home,
            name=record.name,
            tmux_session=record.tmux_session,
            reason=failure["reason"],
            exit_code=failure.get("exit_code"),
            stderr_summary=failure.get("stderr_summary"),
            record_id=record.record_id,
        )
        failures.append(state.to_dict())
    return failures


def _managed_worker_failure_from_record(
    record: Any,
    *,
    max_run_minutes: int = 0,
) -> dict[str, Any] | None:
    excerpt = _managed_process_log_excerpt(record.log_path) or ""
    protocol = _supervisor_protocol_from_text(excerpt)
    if protocol.get("status") in {"done", "blocked", "needs_user"}:
        return None
    is_running = _pid_is_running(record.pid)
    if not is_running and (parsed := _nonzero_exit_failure(excerpt)):
        return parsed
    if max_run_minutes > 0 and _managed_record_exceeded_run_budget(
        record,
        max_run_minutes=max_run_minutes,
    ):
        return {
            "reason": "timeout",
            "exit_code": None,
            "stderr_summary": _stderr_summary_from_excerpt(excerpt)
            or f"worker exceeded {max_run_minutes} minute run budget",
        }
    return None


def _auto_retry_exited_process_workers(args: argparse.Namespace) -> list[dict[str, Any]]:
    max_retries = getattr(
        args,
        "max_worker_retry_count",
        DEFAULT_MAX_WORKER_RETRY_COUNT,
    )
    if max_retries <= 0:
        return []
    codex_home = Path(args.codex_home)
    latest_by_name: dict[str, Any] = {}
    for record in read_managed_records(default_registry_path(codex_home)):
        latest_by_name[record.name] = record

    retried: list[dict[str, Any]] = []
    lane_states = read_lane_states(default_lane_state_path(codex_home))
    for record in latest_by_name.values():
        failure = _process_worker_retry_failure(
            record,
            max_run_minutes=getattr(args, "max_run_minutes", 0),
        )
        legacy_working_retry = failure is None and _process_worker_needs_retry(record)
        if failure is None and not legacy_working_retry:
            continue
        state = (
            record_lane_failure(
                codex_home=codex_home,
                name=record.name,
                tmux_session=record.tmux_session,
                reason=str(failure["reason"]),
                exit_code=failure.get("exit_code"),
                stderr_summary=failure.get("stderr_summary"),
                record_id=record.record_id,
            )
            if failure is not None
            else lane_states.get(record.name)
        )
        retry_count = state.worker_retry_count if state is not None else 0
        if retry_count >= max_retries:
            if failure is not None:
                _ensure_worker_retry_decision_request(
                    args,
                    record=record,
                    state=state,
                    failure=failure,
                    max_retries=max_retries,
                )
            continue
        launched = launch_managed_codex(
            codex_home=codex_home,
            cwd=Path(record.cwd),
            name=record.name,
            prompt=record.prompt,
            codex_model=_worker_codex_model(args),
            codex_config=_worker_codex_config(args),
            worker_role=record.worker_role,
            popen=subprocess.Popen,
            run=subprocess.run,
        )
        updated_state = record_worker_retry(
            codex_home=codex_home,
            name=record.name,
            tmux_session=None,
        )
        retried.append(
            {
                "name": record.name,
                "previous_record_id": record.record_id,
                "record_id": launched.record_id,
                "pid": launched.pid,
                "retry_count": updated_state.worker_retry_count,
                "max_retries": max_retries,
                **({"failure": failure} if failure is not None else {}),
            }
        )
    return retried


def _process_worker_retry_failure(
    record: Any,
    *,
    max_run_minutes: int = 0,
) -> dict[str, Any] | None:
    if record.backend != "process":
        return None
    if not _cwd_is_existing_dir(record.cwd):
        return None
    return _managed_worker_failure_from_record(
        record,
        max_run_minutes=max_run_minutes,
    )


def _ensure_worker_retry_decision_request(
    args: argparse.Namespace,
    *,
    record: Any,
    state: Any,
    failure: dict[str, Any],
    max_retries: int,
) -> dict[str, Any] | None:
    if _active_worker_retry_decision_exists(
        codex_home=Path(args.codex_home),
        lane_name=record.name,
    ):
        return None
    event = {
        "event_type": "worker_retry_failed",
        "lane_name": record.name,
        "goal_id": None,
        "error_summary": _worker_retry_error_summary(failure),
        "retry_count": state.worker_retry_count if state is not None else max_retries,
        "max_retries": max_retries,
        "record_id": record.record_id,
        "failure": failure,
    }
    return _execute_ask_user_action(
        args,
        _failure_decision_request_action(
            event=event,
            question=_failure_question("worker_retry_failed"),
            reason="worker retry limit exceeded",
        ),
    )


def _active_worker_retry_decision_exists(
    *,
    codex_home: Path,
    lane_name: str,
) -> bool:
    session_id = f"failure:worker_retry_failed:{lane_name}"
    return any(
        request.session_id == session_id
        for request in read_active_decision_requests(codex_home=codex_home, limit=1000)
    )


def _worker_retry_error_summary(failure: dict[str, Any]) -> str:
    reason = str(failure.get("reason") or "worker failed")
    stderr_summary = failure.get("stderr_summary")
    if isinstance(stderr_summary, str) and stderr_summary.strip():
        return f"{reason}: {stderr_summary.strip()}"
    exit_code = failure.get("exit_code")
    if isinstance(exit_code, int):
        return f"{reason}: exit code {exit_code}"
    return reason


def _process_worker_needs_retry(record: Any) -> bool:
    if record.backend != "process":
        return False
    if _pid_is_running(record.pid):
        return False
    if not _cwd_is_existing_dir(record.cwd):
        return False
    excerpt = _managed_process_log_excerpt(record.log_path) or ""
    protocol = _supervisor_protocol_from_text(excerpt)
    status = (protocol.get("status") or "").strip().lower()
    return status == "working"


def _managed_record_exceeded_run_budget(
    record: Any,
    *,
    max_run_minutes: int,
) -> bool:
    started_at = _parse_timestamp(record.started_at)
    if started_at is None:
        return False
    elapsed_seconds = max(0, int((_utc_now() - started_at).total_seconds()))
    return elapsed_seconds >= max_run_minutes * 60


def _nonzero_exit_failure(excerpt: str) -> dict[str, Any] | None:
    for pattern in (
        r"process exited with code\s+(-?\d+)",
        r"exit code\s+(-?\d+)",
        r"exited with status\s+(-?\d+)",
        r"returncode[=:]\s*(-?\d+)",
    ):
        match = re.search(pattern, excerpt, flags=re.IGNORECASE)
        if match is None:
            continue
        exit_code = int(match.group(1))
        if exit_code == 0:
            return None
        return {
            "reason": "exit_code",
            "exit_code": exit_code,
            "stderr_summary": _stderr_summary_from_excerpt(excerpt),
        }
    return None


def _stderr_summary_from_excerpt(excerpt: str, *, limit: int = 500) -> str | None:
    lines = [line.strip() for line in excerpt.splitlines() if line.strip()]
    stderr_lines = [
        line
        for line in lines
        if line.lower().startswith(("stderr:", "error:", "traceback"))
    ]
    candidates = stderr_lines or [
        line
        for line in lines
        if not line.upper().startswith("SUPERVISOR_")
        and not re.search(
            r"(process exited with code|exit code|exited with status|returncode[=:])",
            line,
            flags=re.IGNORECASE,
        )
    ]
    if not candidates:
        return None
    summary = " / ".join(candidates[-3:])
    return summary[:limit]


def _lane_failure_payload(
    *,
    codex_home: Path,
    record: Any,
) -> dict[str, Any] | None:
    state = lane_failure_state(codex_home=codex_home, name=record.name)
    if state is None:
        return None
    if state.last_failure_record_id and state.last_failure_record_id != record.record_id:
        return None
    return {
        "reason": state.last_failure_reason,
        "exit_code": state.last_failure_exit_code,
        "stderr_summary": state.last_failure_stderr_summary,
        "record_id": state.last_failure_record_id,
    }


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
        if target_name == MERGE_DISPATCH_TARGET_NAME and status == "done":
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


def _auto_promote_merge_worker_review_item(
    item: dict[str, Any],
    *,
    args: argparse.Namespace,
    codex_home: Path,
    repo_root: Path,
    run: Any,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> dict[str, Any] | None:
    if not _merge_worker_review_item_is_done(item):
        return None
    if item.get("main_contains_worker") is True:
        return None
    name = _non_empty_text(item.get("name"))
    record_id = _non_empty_text(item.get("record_id"))
    branch = _non_empty_text(item.get("branch"))
    worker_commit = _non_empty_text(item.get("worker_commit"))
    if not name or not record_id or not branch or not worker_commit:
        return None
    answered_decision = _merge_promotion_recent_decision_answer(
        codex_home=codex_home,
        record_id=record_id,
    )
    decision_intent = _merge_promotion_decision_intent(answered_decision)
    repair_completed: dict[str, Any] | None = None
    if decision_intent == "abandon":
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "skipped_by_decision",
            "reason": "merge promotion abandoned by decision",
            "decision_answer": answered_decision,
        }
    if decision_intent == "repair":
        repair_completed = _completed_merge_promotion_repair_worker(
            codex_home=codex_home,
            repair_name=f"{name}-repair",
        )
        if repair_completed is None:
            branch_ci = _latest_ci_run_for_ref(
                branch=branch,
                commit=worker_commit,
                run=run,
            )
            return _launch_merge_promotion_repair_worker(
                args=args,
                codex_home=codex_home,
                repo_root=repo_root,
                item=item,
                branch_ci=branch_ci,
                decision_answer=answered_decision,
            )
    branch_ci = _latest_ci_run_for_ref(
        branch=branch,
        commit=worker_commit,
        run=run,
    )
    if not _ci_run_succeeded(branch_ci, expected_commit=worker_commit):
        if _ci_run_is_terminal(branch_ci):
            return _blocked_merge_promotion(
                item,
                status_reason="branch CI did not succeed",
                branch_ci=branch_ci,
                codex_home=codex_home,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
            )
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "waiting_for_branch_ci",
            "branch_ci": branch_ci,
        }
    precheck = _check_main_promotion_preconditions(repo_root, run=run)
    if precheck is not None:
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "blocked",
            "reason": precheck,
            "branch_ci": branch_ci,
            "decision_request": _merge_promotion_decision_request(
                codex_home=codex_home,
                item=item,
                reason=precheck,
                branch_ci=branch_ci,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
            ),
        }
    merge_result = _run_checked(
        ["git", "-C", str(repo_root), "merge", "--ff-only", worker_commit],
        run=run,
    )
    if merge_result is not None:
        return _blocked_merge_promotion(
            item,
            status_reason=merge_result,
            branch_ci=branch_ci,
            codex_home=codex_home,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
    diff_result = _run_checked(
        ["git", "-C", str(repo_root), "diff", "--check"],
        run=run,
    )
    if diff_result is not None:
        return _blocked_merge_promotion(
            item,
            status_reason=diff_result,
            branch_ci=branch_ci,
            codex_home=codex_home,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
    push_result = _run_checked(
        ["git", "-C", str(repo_root), "push", "origin", "main"],
        run=run,
    )
    if push_result is not None:
        return _blocked_merge_promotion(
            item,
            status_reason=push_result,
            branch_ci=branch_ci,
            codex_home=codex_home,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
    main_head = _git_text(repo_root, ["rev-parse", "HEAD"], run=run)
    if not main_head:
        main_head = worker_commit
    main_ci = _latest_ci_run_for_ref(branch="main", commit=main_head, run=run)
    main_ci_run_id = main_ci.get("databaseId") if isinstance(main_ci, dict) else None
    if main_ci_run_id is not None:
        watch_result = _run_checked(
            ["gh", "run", "watch", str(main_ci_run_id), "--exit-status"],
            run=run,
        )
        if watch_result is not None:
            return _blocked_merge_promotion(
                item,
                status_reason=watch_result,
                branch_ci=branch_ci,
                main_ci=main_ci,
                main_head=main_head,
                codex_home=codex_home,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
            )
        viewed = _view_ci_run(str(main_ci_run_id), run=run)
        if viewed:
            main_ci = viewed
    if not _ci_run_succeeded(main_ci, expected_commit=main_head):
        return _blocked_merge_promotion(
            item,
            status_reason="main CI did not succeed",
            branch_ci=branch_ci,
            main_ci=main_ci,
            main_head=main_head,
            codex_home=codex_home,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
    payload = {
        "kind": "merge_worker_main_promotion",
        "name": name,
        "record_id": record_id,
        "branch": branch,
        "worker_commit": worker_commit,
        "status": "done",
        "main_head": main_head,
        "branch_ci": branch_ci,
        "main_ci": main_ci,
    }
    if repair_completed is not None:
        payload["repair_completed"] = _archive_completed_merge_promotion_repair_worker(
            codex_home=codex_home,
            repair_completed=repair_completed,
        )
    return payload


def _blocked_merge_promotion(
    item: dict[str, Any],
    *,
    status_reason: str,
    branch_ci: dict[str, Any],
    main_ci: dict[str, Any] | None = None,
    main_head: str | None = None,
    codex_home: Path | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> dict[str, Any]:
    payload = {
        "kind": "merge_worker_main_promotion",
        "name": item.get("name"),
        "record_id": item.get("record_id"),
        "branch": item.get("branch"),
        "worker_commit": item.get("worker_commit"),
        "status": "blocked",
        "reason": status_reason,
        "branch_ci": branch_ci,
    }
    if main_ci is not None:
        payload["main_ci"] = main_ci
    if main_head is not None:
        payload["main_head"] = main_head
    if codex_home is not None:
        payload["decision_request"] = _merge_promotion_decision_request(
            codex_home=codex_home,
            item=item,
            reason=status_reason,
            branch_ci=branch_ci,
            main_ci=main_ci,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
    return payload


def _merge_promotion_decision_request(
    *,
    codex_home: Path,
    item: dict[str, Any],
    reason: str,
    branch_ci: dict[str, Any],
    main_ci: dict[str, Any] | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> dict[str, Any]:
    record_id = _non_empty_text(item.get("record_id")) or "unknown"
    target_name = _non_empty_text(item.get("name"))
    branch = _non_empty_text(item.get("branch")) or "unknown"
    worker_commit = _non_empty_text(item.get("worker_commit")) or "unknown"
    for request in read_active_decision_requests(codex_home=codex_home, limit=1000):
        if (
            request.session_id == f"managed:{record_id}"
            and request.reason == "merge_promotion_failed"
            and request.question == _MERGE_PROMOTION_DECISION_QUESTION
        ):
            return request.to_dict()
    action = {
        "kind": "ask_user",
        "session_id": f"managed:{record_id}",
        "target_name": target_name,
        "question": _MERGE_PROMOTION_DECISION_QUESTION,
        "reason": "merge_promotion_failed",
        "context_status": "promotion_blocked",
        "gate": {
            "event_type": "merge_promotion_failed",
            "reason": reason,
            "branch": branch,
            "worker_commit": worker_commit,
            "branch_ci": branch_ci,
            "main_ci": main_ci,
        },
    }
    return record_decision_request(
        codex_home=codex_home,
        action=action,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    ).to_dict()


def _launch_merge_promotion_repair_worker(
    *,
    args: argparse.Namespace,
    codex_home: Path,
    repo_root: Path,
    item: dict[str, Any],
    branch_ci: dict[str, Any],
    decision_answer: dict[str, Any] | None,
) -> dict[str, Any]:
    name = _non_empty_text(item.get("name")) or MERGE_DISPATCH_TARGET_NAME
    record_id = _non_empty_text(item.get("record_id")) or "unknown"
    branch = _non_empty_text(item.get("branch")) or "unknown"
    worker_commit = _non_empty_text(item.get("worker_commit")) or "unknown"
    repair_name = f"{name}-repair"
    if running_worker := _running_managed_process_by_name(
        codex_home=codex_home,
        name=repair_name,
    ):
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "repair_already_running",
            "repair": _managed_worker_reference(running_worker),
            "decision_answer": decision_answer,
        }
    if cooldown_state := prompt_cooldown_state(
        codex_home=codex_home,
        name=repair_name,
        cooldown_seconds=getattr(args, "prompt_cooldown", DEFAULT_PROMPT_COOLDOWN_SECONDS),
    ):
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "repair_cooldown_active",
            "repair": {
                "kind": "launch_session",
                "skipped": True,
                "reason": "launch prompt cooldown active",
                "lane_state": cooldown_state.to_dict(),
            },
            "decision_answer": decision_answer,
        }
    worktree = _prepare_launch_worktree(cwd=repo_root, target_name=repair_name)
    if worktree.get("failed"):
        return {
            "kind": "merge_worker_main_promotion",
            "name": name,
            "record_id": record_id,
            "branch": branch,
            "worker_commit": worker_commit,
            "status": "repair_blocked",
            "repair": {
                "kind": "launch_session",
                "skipped": True,
                "reason": "worktree setup failed",
                "worktree": worktree,
            },
            "decision_answer": decision_answer,
        }
    repair_prompt = _merge_promotion_repair_prompt(
        item=item,
        branch_ci=branch_ci,
        decision_answer=decision_answer,
    )
    worker_cwd = Path(str(worktree["cwd"]))
    work_order_prompt = build_launch_work_order_prompt(
        target_name=repair_name,
        cwd=str(worker_cwd),
        goal=repair_prompt,
        allow_remote_push=False,
    )
    record = launch_managed_codex(
        codex_home=codex_home,
        cwd=worker_cwd,
        name=repair_name,
        prompt=work_order_prompt,
        codex_model=_worker_codex_model(args, profile=DEFAULT_WORKER_PROFILE),
        codex_config=_worker_codex_config(args, profile=DEFAULT_WORKER_PROFILE),
        worker_role=MERGE_REPAIR_WORKER_ROLE,
        popen=subprocess.Popen,
        run=subprocess.run,
    )
    record_lane_prompt(
        codex_home=codex_home,
        name=record.name,
        tmux_session=None,
        status="launch_session",
        prompt_kind="merge_promotion_repair",
    )
    return {
        "kind": "merge_worker_main_promotion",
        "name": name,
        "record_id": record_id,
        "branch": branch,
        "worker_commit": worker_commit,
        "status": "repair_launched",
        "branch_ci": branch_ci,
        "decision_answer": decision_answer,
        "repair": {
            "kind": "launch_session",
            "target_name": repair_name,
            "worker_role": record.worker_role,
            "text": work_order_prompt,
            "managed": {
                "name": record.name,
                "record_id": record.record_id,
                "pid": record.pid,
                "backend": record.backend,
                "worker_role": record.worker_role,
            },
            "worktree": worktree,
        },
    }


def _merge_promotion_repair_prompt(
    *,
    item: dict[str, Any],
    branch_ci: dict[str, Any],
    decision_answer: dict[str, Any] | None,
) -> str:
    answer_text = (
        str(decision_answer.get("answer"))
        if isinstance(decision_answer, dict) and decision_answer.get("answer") is not None
        else ""
    ).strip()
    return "\n".join(
        [
            "修复 merge promotion 失败，并在修复后汇报状态。",
            f"merge worker: {_non_empty_text(item.get('name')) or 'unknown'}",
            f"record_id: {_non_empty_text(item.get('record_id')) or 'unknown'}",
            f"branch: {_non_empty_text(item.get('branch')) or 'unknown'}",
            f"worker_commit: {_non_empty_text(item.get('worker_commit')) or 'unknown'}",
            f"用户拍板: {answer_text or '修复后重试'}",
            "失败 CI:",
            json.dumps(branch_ci, ensure_ascii=False, sort_keys=True),
            "要求：检查失败原因，做必要代码修复和相关测试。",
            "不要 force push，不要改写共享历史；完成后按 SUPERVISOR_STATUS 协议汇报。",
        ]
    )


def _completed_merge_promotion_repair_worker(
    *,
    codex_home: Path,
    repair_name: str,
) -> dict[str, Any] | None:
    for record in reversed(read_managed_records(default_registry_path(codex_home))):
        if record.name != repair_name:
            continue
        if getattr(record, "worker_role", "worker") != MERGE_REPAIR_WORKER_ROLE:
            continue
        protocol = _supervisor_protocol_from_text(
            _managed_process_log_excerpt(record.log_path) or ""
        )
        status = str(protocol.get("status") or "").strip().lower()
        if status != "done":
            return None
        payload = {
            "status": "done",
            "managed": _managed_worker_reference(record),
        }
        if summary := _non_empty_text(protocol.get("summary")):
            payload["summary"] = summary
        if next_step := _non_empty_text(protocol.get("next")):
            payload["next"] = next_step
        return payload
    return None


def _archive_completed_merge_promotion_repair_worker(
    *,
    codex_home: Path,
    repair_completed: dict[str, Any],
) -> dict[str, Any]:
    managed = repair_completed.get("managed")
    if not isinstance(managed, dict):
        return repair_completed
    name = _non_empty_text(managed.get("name"))
    record_id = _non_empty_text(managed.get("record_id"))
    if not name or not record_id:
        return repair_completed
    archived = archive_managed_codex(
        codex_home=codex_home,
        name=name,
        record_id=record_id,
    )
    return {
        **repair_completed,
        "status": "archived",
        "managed": archived.to_dict(),
    }


def _merge_promotion_recent_decision_answer(
    *,
    codex_home: Path,
    record_id: str,
) -> dict[str, Any] | None:
    session_id = f"managed:{record_id}"
    for answer in read_recent_decision_answers(codex_home=codex_home, limit=1000):
        if answer.get("session_id") != session_id:
            continue
        if answer.get("reason") == "merge_promotion_failed":
            return dict(answer)
        if answer.get("question") == _MERGE_PROMOTION_DECISION_QUESTION:
            return dict(answer)
    return None


def _merge_promotion_decision_intent(answer: dict[str, Any] | None) -> str | None:
    if not isinstance(answer, dict):
        return None
    text = str(answer.get("answer") or "").strip().lower()
    if not text:
        return None
    if any(token in text for token in ("放弃", "不再", "不要合", "丢弃", "abandon", "drop")):
        return "abandon"
    if any(token in text for token in ("修复", "fix", "repair")):
        return "repair"
    if any(token in text for token in ("重试", "再试", "retry", "rerun")):
        return "retry"
    return "unknown"


def _check_main_promotion_preconditions(repo_root: Path, *, run: Any) -> str | None:
    branch = _git_text(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"], run=run)
    if branch != "main":
        return f"workspace branch is {branch or 'unknown'}, expected main"
    status = _git_text(repo_root, ["status", "--short"], run=run)
    if status is None:
        return "unable to read git status"
    if status.strip():
        return "main worktree is dirty"
    return None


def _latest_ci_run_for_ref(*, branch: str, commit: str, run: Any) -> dict[str, Any]:
    completed = run(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            "CI",
            "--branch",
            branch,
            "--commit",
            commit,
            "--limit",
            "1",
            "--json",
            "databaseId,headSha,status,conclusion,url",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return {
            "status": "unavailable",
            "conclusion": "failure",
            "stderr": _tail_text(completed.stderr),
        }
    try:
        runs = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return {"status": "invalid_json", "conclusion": "failure"}
    if not isinstance(runs, list) or not runs:
        return {"status": "missing", "conclusion": None}
    first = runs[0]
    return first if isinstance(first, dict) else {"status": "invalid_item"}


def _view_ci_run(run_id: str, *, run: Any) -> dict[str, Any]:
    completed = run(
        [
            "gh",
            "run",
            "view",
            run_id,
            "--json",
            "databaseId,headSha,status,conclusion,url",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return {}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ci_run_succeeded(run_payload: dict[str, Any], *, expected_commit: str) -> bool:
    return (
        run_payload.get("status") == "completed"
        and run_payload.get("conclusion") == "success"
        and run_payload.get("headSha") == expected_commit
    )


def _ci_run_is_terminal(run_payload: dict[str, Any]) -> bool:
    return run_payload.get("status") == "completed" or run_payload.get("conclusion") in {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
    }


def _run_checked(command: list[str], *, run: Any) -> str | None:
    completed = run(command, check=False, text=True, capture_output=True)
    if completed.returncode == 0:
        return None
    detail = _tail_text(completed.stderr) or _tail_text(completed.stdout)
    return f"{shlex.join(command)} failed" + (f": {detail}" if detail else "")


def _git_text(repo_root: Path, args: list[str], *, run: Any) -> str | None:
    completed = run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    return (completed.stdout or "").strip()


def _non_empty_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _auto_delete_archived_worktrees_after_cleanup(
    args: argparse.Namespace,
    *,
    cleanup_archived: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not cleanup_archived:
        return []
    if getattr(args, "command", None) != "loop":
        return []
    if _current_workspace_has_worker_role(args, RECURSIVE_WORKER_ROLES):
        return []
    archived_record_ids = {
        record_id
        for item in cleanup_archived
        for record_id in (item.get("record_id"),)
        if isinstance(record_id, str) and record_id
    }
    if not archived_record_ids:
        return []
    deleted: list[dict[str, Any]] = []
    for candidate in _delete_worktree_candidate_payloads(args):
        target_name = candidate.get("target_name") or candidate.get("name")
        record_id = candidate.get("record_id")
        if not isinstance(target_name, str) or not target_name.strip():
            continue
        if not isinstance(record_id, str) or not record_id.strip():
            continue
        if record_id not in archived_record_ids:
            continue
        deleted.append(
            _execute_delete_worktree_action(
                args,
                {
                    "kind": "delete_worktree",
                    "target_name": target_name,
                    "record_id": record_id,
                    "confirm_delete_worktree": True,
                    "base_ref": "main",
                    "source": "cleanup_auto",
                },
            )
        )
    return deleted


def _auto_archive_integrated_merge_workers(
    *,
    codex_home: Path,
    review_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    groups = review_payload.get("groups")
    if not isinstance(groups, dict):
        return []
    integrated_record_ids = _review_group_record_ids(groups, "already_integrated")
    if not integrated_record_ids:
        return []
    records = {
        record.record_id: record
        for record in read_managed_records(default_registry_path(codex_home))
    }
    archived: list[dict[str, Any]] = []
    archived_record_ids: set[str] = set()
    for item in _review_group_items(groups, "merge_workers"):
        record_id = item.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            continue
        record = records.get(record_id)
        if record is None:
            continue
        if not _merge_worker_review_item_is_done(item):
            continue
        candidate_record_ids = _merge_candidate_record_ids(record)
        if not candidate_record_ids:
            continue
        if not candidate_record_ids <= integrated_record_ids:
            continue
        for candidate_record_id in sorted(candidate_record_ids):
            if candidate_record_id in archived_record_ids:
                continue
            candidate_record = records.get(candidate_record_id)
            if candidate_record is None:
                continue
            archived.append(
                _archive_integrated_source_worker(codex_home, candidate_record)
            )
            archived_record_ids.add(candidate_record_id)
        if record_id in archived_record_ids:
            continue
        archived.append(_archive_integrated_merge_worker(codex_home, record, item))
        archived_record_ids.add(record_id)
    return archived


def _archive_integrated_source_worker(
    codex_home: Path,
    record: Any,
) -> dict[str, Any]:
    managed = archive_managed_codex(
        codex_home=codex_home,
        name=record.name,
        record_id=record.record_id,
    )
    return {
        "kind": "source_worker",
        "name": record.name,
        "record_id": record.record_id,
        "managed": managed.to_dict(),
        "integration_group": "already_integrated",
    }


def _archive_integrated_merge_worker(
    codex_home: Path,
    record: Any,
    review_item: dict[str, Any],
) -> dict[str, Any]:
    managed = archive_managed_codex(
        codex_home=codex_home,
        name=record.name,
        record_id=record.record_id,
    )
    protocol = review_item.get("supervisor_protocol")
    protocol = protocol if isinstance(protocol, dict) else {}
    goal = _archive_related_merge_goal(
        codex_home=codex_home,
        target_name=record.name,
        protocol=protocol,
    )
    notification = notify_merge_worker_auto_archived(
        codex_home=codex_home,
        record_id=record.record_id,
        status="done",
        group="already_integrated",
    )
    result: dict[str, Any] = {
        "kind": "merge_worker",
        "name": record.name,
        "record_id": record.record_id,
        "managed": managed.to_dict(),
        "integration_group": "already_integrated",
    }
    if goal is not None:
        result["goal"] = goal
    if notification is not None:
        result["notification"] = notification.to_dict()
    return result


def _archive_related_merge_goal(
    *,
    codex_home: Path,
    target_name: str,
    protocol: dict[str, Any],
) -> dict[str, Any] | None:
    for goal in read_active_supervisor_goals(codex_home=codex_home, limit=1000):
        if goal.target_name != target_name:
            continue
        return archive_supervisor_goal(
            codex_home=codex_home,
            goal_id=goal.goal_id,
            status="done",
            target_name=target_name,
            summary=(
                protocol.get("summary")
                if isinstance(protocol.get("summary"), str)
                else None
            ),
            next_step=(
                protocol.get("next")
                if isinstance(protocol.get("next"), str)
                else None
            ),
        )
    return None


def _merge_worker_review_item_is_done(item: dict[str, Any]) -> bool:
    protocol = item.get("supervisor_protocol")
    if not isinstance(protocol, dict):
        return False
    status = protocol.get("status")
    return isinstance(status, str) and status.lower() == "done"


def _merge_candidate_record_ids(record: Any) -> set[str]:
    text = "\n".join(
        [
            str(getattr(record, "prompt", "") or ""),
            " ".join(str(part) for part in getattr(record, "command", ()) or ()),
        ]
    )
    return {
        match.group(0)
        for match in re.finditer(r"\bmanaged-[A-Za-z0-9_-]+\b", text)
        if match.group(0) != getattr(record, "record_id", None)
    }


def _review_group_record_ids(groups: dict[str, Any], group: str) -> set[str]:
    return {
        record_id
        for item in _review_group_items(groups, group)
        for record_id in (item.get("record_id"),)
        if isinstance(record_id, str) and record_id
    }


def _review_group_items(groups: dict[str, Any], group: str) -> list[dict[str, Any]]:
    items = groups.get(group)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _integration_reviews_by_record_ref(
    payload: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    reviews: dict[tuple[str, str], dict[str, Any]] = {}
    raw_workers = payload.get("workers")
    workers = raw_workers if isinstance(raw_workers, list) else []
    for raw in workers:
        if not isinstance(raw, dict):
            continue
        record_id = raw.get("record_id")
        name = raw.get("name")
        if isinstance(record_id, str) and record_id:
            reviews[("record_id", record_id)] = raw
        if isinstance(name, str) and name:
            reviews[("name", name)] = raw
    return reviews


def _integration_review_for_cleanup_candidate(
    candidate: dict[str, Any],
    reviews: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    record_id = candidate.get("record_id")
    if isinstance(record_id, str) and record_id:
        review = reviews.get(("record_id", record_id))
        if review is not None:
            return review
    name = candidate.get("name")
    if isinstance(name, str) and name:
        return reviews.get(("name", name))
    return None


def _auto_cleanup_integration_summary(review: dict[str, Any]) -> dict[str, Any]:
    return _drop_none_values(
        {
            "group": review.get("group"),
            "reason": review.get("reason"),
            "record_id": review.get("record_id"),
            "name": review.get("name"),
            "branch": review.get("branch"),
            "worker_commit": review.get("worker_commit"),
            "base_ref": review.get("base_ref"),
            "main_contains_worker": review.get("main_contains_worker"),
            "main_has_worker_patch": review.get("main_has_worker_patch"),
            "dirty": review.get("dirty"),
        }
    )


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
        webhook_url=args.webhook_url,
        webhook_secret=args.webhook_secret,
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


def _start_here_payload(args: argparse.Namespace) -> dict[str, Any]:
    cwd = str(Path(args.cwd).expanduser())
    codex_home = str(Path(args.codex_home).expanduser())
    goal = str(args.goal).strip()
    if not goal:
        raise ValueError("goal must not be empty")
    start_command = " && ".join(
        [
            shlex.join(["cd", cwd]),
            shlex.join(
                [
                    "isotope-supervisor",
                    "up",
                    "--codex-home",
                    codex_home,
                    "--goal",
                    goal,
                    "--goal-low-water",
                    "2",
                    "--goal-replenish-limit",
                    "2",
                    "--max-fanout-launches",
                    "2",
                ]
            ),
        ]
    )
    commands = {
        "start": start_command,
        "open_web": shlex.join(
            [
                "isotope-supervisor",
                "web",
                "--codex-home",
                codex_home,
                "--host",
                str(args.host),
                "--port",
                str(args.port),
            ]
        ),
        "check_status": shlex.join(
            ["isotope-supervisor", "daemon", "status", "--codex-home", codex_home]
        ),
        "list_goals": shlex.join(
            ["isotope-supervisor", "goal", "list", "--codex-home", codex_home]
        ),
        "list_decisions": shlex.join(
            ["isotope-supervisor", "decision", "list", "--codex-home", codex_home]
        ),
        "trace": shlex.join(
            ["isotope-supervisor", "trace", "--codex-home", codex_home, "--json"]
        ),
        "stop": shlex.join(
            ["isotope-supervisor", "daemon", "stop", "--codex-home", codex_home]
        ),
    }
    return {
        "status": "ok",
        "workflow": {
            "cwd": cwd,
            "codex_home": codex_home,
            "goal": goal,
            "goal_low_water": 2,
            "goal_replenish_limit": 2,
            "max_fanout_launches": 2,
            "web_url": f"http://{args.host}:{args.port}",
        },
        "recommended_order": [
            "start",
            "open_web",
            "check_status",
            "send_feedback",
        ],
        "commands": commands,
        "what_to_expect": [
            "start 会启动或唤起后台 daemon，并把目标交给 Supervisor。",
            "后台 loop 会让 LLM 读当前文档，必要时补充目标并启动 worker。",
            "web 和 trace 用来观察 goal、worker、decision、merge、cleanup 停在哪一步。",
        ],
        "feedback_prompts": [
            "页面是否能看出哪些 worker 正在跑？",
            "lifecycle_trace.next_attention 是否符合你的直觉？",
            "如果它停住了，停在 goal、worker、decision、merge 还是 cleanup？",
        ],
    }


def _print_start_here_plain(payload: dict[str, Any]) -> None:
    workflow = payload["workflow"]
    commands = payload["commands"]
    print("[Supervisor 从这里开始]")
    print(f"工作目录：{workflow['cwd']}")
    print(f"目标：{workflow['goal']}")
    print()
    print("1. 先启动后台 Supervisor：")
    print(commands["start"])
    print()
    print("2. 打开本地页面观察：")
    print(commands["open_web"])
    print(f"浏览器地址：{workflow['web_url']}")
    print()
    print("3. 需要命令行看状态时：")
    print(commands["check_status"])
    print(commands["list_goals"])
    print(commands["list_decisions"])
    print(commands["trace"])
    print()
    print("4. 给我反馈时，优先看这三点：")
    for item in payload["feedback_prompts"]:
        print(f"- {item}")
    print()
    print("5. 想停掉后台 Supervisor：")
    print(commands["stop"])


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
    if getattr(args, "max_failure_retries", DEFAULT_MAX_FAILURE_RETRIES) < 0:
        raise ValueError("max_failure_retries must be zero or positive")
    if getattr(args, "max_run_minutes", 0) < 0:
        raise ValueError("max_run_minutes must be zero or positive")
    if getattr(args, "max_worker_retry_count", DEFAULT_MAX_WORKER_RETRY_COUNT) < 0:
        raise ValueError("max_worker_retry_count must be zero or positive")
    if getattr(args, "max_fanout_launches", 1) <= 0:
        raise ValueError("max_fanout_launches must be positive")
    if getattr(args, "goal_low_water", 0) < 0:
        raise ValueError("goal_low_water must be zero or positive")
    if getattr(args, "goal_replenish_limit", 1) <= 0:
        raise ValueError("goal_replenish_limit must be positive")
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


def _maybe_replenish_active_goals(
    args: argparse.Namespace,
    active_goals: list[dict[str, Any]],
    *,
    running_target_names: set[str] | None = None,
) -> dict[str, Any] | None:
    if getattr(args, "command", None) != "loop":
        return None
    low_water = getattr(args, "goal_low_water", 0)
    if low_water <= 0:
        return None
    if getattr(args, "name", None) or _explicit_goal_text(args):
        return None
    active_before = len(
        _replenishment_counted_active_goals(
            active_goals,
            running_target_names=running_target_names,
        )
    )
    if active_before >= low_water:
        return None

    replenish_limit = min(
        getattr(args, "goal_replenish_limit", DEFAULT_FANOUT_LIMIT),
        low_water - active_before,
    )
    root = _workspace_root(args) or Path.cwd().resolve()
    try:
        provider = resolve_summary_provider_from_env(agent_name="supervisor")
        plan = plan_supervisor_goals(
            root=root,
            codex_home=Path(args.codex_home),
            provider=provider,
            user_goal=_goal_replenishment_prompt(args),
            write=True,
            limit=replenish_limit,
            planning_trigger="low_water",
        )
    except Exception as exc:
        return {
            "status": "error",
            "trigger": "low_water",
            "active_before": active_before,
            "active_total_before": len(active_goals),
            "low_water": low_water,
            "requested_limit": replenish_limit,
            "root": str(root),
            "reason": str(exc),
        }
    written_goals = plan.get("written_goals") if isinstance(plan, dict) else []
    if not isinstance(written_goals, list):
        written_goals = []
    parallel_recommendations = (
        plan.get("parallel_recommendations") if isinstance(plan, dict) else []
    )
    if not isinstance(parallel_recommendations, list):
        parallel_recommendations = []
    return {
        "status": "ok",
        "trigger": "low_water",
        "active_before": active_before,
        "active_total_before": len(active_goals),
        "low_water": low_water,
        "requested_limit": replenish_limit,
        "root": str(root),
        "written_count": len(written_goals),
        "written_goals": written_goals,
        "plan_summary": plan.get("plan_summary") if isinstance(plan, dict) else None,
        "parallel_recommendations": parallel_recommendations,
    }


def _goal_replenishment_prompt(args: argparse.Namespace) -> str:
    raw = getattr(args, "goal_replenish_prompt", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return DEFAULT_GOAL_REPLENISH_PROMPT


def _replenishment_counted_active_goals(
    active_goals: list[dict[str, Any]],
    *,
    running_target_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    running_names = running_target_names or set()
    counted: list[dict[str, Any]] = []
    for goal in active_goals:
        if _active_goal_is_deferred(goal):
            continue
        target_name = goal.get("target_name")
        if isinstance(target_name, str) and target_name in running_names:
            continue
        counted.append(goal)
    return counted


def _fanout_candidate_active_goals(
    active_goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [goal for goal in active_goals if not _active_goal_is_deferred(goal)]


def _active_goal_is_deferred(goal: dict[str, Any]) -> bool:
    for key in ("last_status", "status", "supervisor_status"):
        status = goal.get(key)
        if isinstance(status, str) and status.lower() in {
            "blocked",
            "done",
            "needs_user",
        }:
            return True
    return False


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
    auto_retried_workers: list[dict[str, Any]] | None = None,
    goal_updates: list[dict[str, Any]] | None = None,
    merge_promotions: list[dict[str, Any]] | None = None,
    cleanup_archived: list[dict[str, Any]] | None = None,
    cleanup_deleted_worktrees: list[dict[str, Any]] | None = None,
    decision_timeout_alerts: list[dict[str, Any]] | None = None,
    precomputed_auto_action: dict[str, Any] | None = None,
    precomputed_executed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action_report = _action_report_for_workspace(args, report)
    active_goals = _active_goal_dicts(args, include_status=True)
    running_target_names = _running_managed_target_names(report)
    goal_replenishment = _maybe_replenish_active_goals(
        args,
        active_goals,
        running_target_names=running_target_names,
    )
    if (
        isinstance(goal_replenishment, dict)
        and goal_replenishment.get("status") == "ok"
        and goal_replenishment.get("written_count")
    ):
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
    payload["auto_retried_workers"] = auto_retried_workers or []
    payload["active_goals"] = active_goals
    if goal_replenishment is not None:
        payload["goal_replenishment"] = goal_replenishment
    if goal_updates:
        payload["goal_updates"] = goal_updates
    if merge_promotions:
        payload["merge_promotions"] = merge_promotions
    if cleanup_archived:
        payload["cleanup_archived"] = cleanup_archived
    if cleanup_deleted_worktrees:
        payload["cleanup_deleted_worktrees"] = cleanup_deleted_worktrees
    payload["decision_timeout_alerts"] = decision_timeout_alerts or []
    worker_reviews: dict[str, Any] | None = None
    if args.llm_action or args.llm_execute:
        payload["recent_context_results"] = _recent_context_results(args, action_report)
        payload["recent_decision_answers"] = _decision_answer_dicts(args)
        worker_reviews = _worker_review_context(args)
        payload["worker_reviews"] = worker_reviews
        payload["delete_worktree_candidates"] = _delete_worktree_candidate_payloads(args)
    payload["current_batch"] = _current_batch_payload(
        report,
        active_goals=active_goals,
        worker_reviews=worker_reviews,
    )
    fanout_status = _fanout_status_payload(
        report,
        active_goals=_fanout_candidate_active_goals(active_goals),
        goal_updates=goal_updates or [],
    )
    if fanout_status is not None:
        payload["fanout_status"] = fanout_status
    if args.llm_summary:
        payload["llm_summary"] = _summarize_with_llm(report)
    fanout_paused = (
        isinstance(fanout_status, dict) and fanout_status.get("status") == "paused"
        and not _goal_replenishment_wrote_goals(goal_replenishment)
    )
    worker_role_guard = _recursive_worker_role_guard_payload(args)
    merge_dispatch = (
        _integration_merge_dispatch_payload(args)
        if not fanout_paused
        and worker_role_guard is None
        and (args.llm_action or args.llm_execute)
        else None
    )
    fanout_plan = (
        None
        if merge_dispatch is not None
        else (
            _paused_active_goals_fanout_plan(args, active_goals)
            if fanout_paused
            else _replenished_goal_plan_fanout_launch_plan(
                args,
                report,
                goal_replenishment,
            )
            or _active_goals_fanout_launch_plan(args, report, active_goals)
        )
    )
    if fanout_plan is not None and (args.llm_action or args.llm_execute):
        payload["fanout_plan"] = fanout_plan
        payload["fanout_log"] = _fanout_log_payload(
            fanout_plan,
            goal_replenishment=goal_replenishment,
        )
    if merge_dispatch is not None:
        payload["merge_dispatch"] = merge_dispatch
    if (
        fanout_plan is None
        and merge_dispatch is None
        and not fanout_paused
        and worker_role_guard is None
        and (args.llm_action or args.llm_execute)
    ):
        merge_dispatch = _integration_merge_dispatch_payload(args)
        if merge_dispatch is not None:
            payload["merge_dispatch"] = merge_dispatch
    if args.llm_action or args.llm_execute:
        if fanout_paused:
            payload["llm_action"] = _fanout_paused_action(fanout_status)
        elif fanout_plan is not None:
            payload["llm_action"] = _fanout_llm_action(fanout_plan)
        elif worker_role_guard is not None:
            payload["llm_action"] = _recursive_worker_role_guard_action(
                worker_role_guard
            )
        elif merge_dispatch is not None:
            if merge_dispatch.get("status") == "worker_already_running":
                payload["llm_action"] = _merge_dispatch_already_running_action(
                    merge_dispatch
                )
            else:
                payload["llm_action"] = merge_dispatch["launch_spec"]
        elif _loop_without_autonomous_scope(
            args,
            action_report,
            active_goals,
            explicit_goal,
        ):
            payload["llm_action"] = _idle_loop_llm_action()
        else:
            payload["llm_action"] = _decide_action_with_llm(args, action_report, payload)
            _promote_llm_command_suggestion(payload)
    if args.llm_execute:
        if fanout_paused:
            payload["executed"] = _fanout_paused_executed(fanout_status)
        elif fanout_plan is not None:
            payload["executed"] = _execute_fanout_launch_actions(
                args,
                fanout_plan,
                report=action_report,
                payload=payload,
            )
            payload["fanout_log"] = _fanout_log_payload(
                fanout_plan,
                goal_replenishment=goal_replenishment,
                executed=payload["executed"],
            )
            if _fanout_execution_launched_workers(payload["executed"]):
                refreshed_report = _scan_report(args)
                payload["current_batch"] = _current_batch_payload(
                    refreshed_report,
                    active_goals=active_goals,
                    worker_reviews=worker_reviews,
                )
        elif worker_role_guard is not None:
            payload["executed"] = _recursive_worker_role_guard_executed(
                worker_role_guard
            )
        elif merge_dispatch is not None:
            if merge_dispatch.get("status") == "worker_already_running":
                payload["executed"] = _merge_dispatch_already_running_executed(
                    merge_dispatch
                )
            elif not getattr(args, "merge_dispatch_execute", False):
                payload["executed"] = _merge_dispatch_planned_executed(merge_dispatch)
            else:
                payload["executed"] = _mark_merge_dispatch_execution(
                    _execute_failure_guarded_action(
                        args,
                        report=action_report,
                        payload=payload,
                        action=merge_dispatch["launch_spec"],
                        event_type="merge_dispatch_failed",
                        execute=lambda: _execute_launch_action(
                            args,
                            merge_dispatch["launch_spec"],
                        ),
                    )
                )
            if _executed_action_forces_print(payload["executed"]):
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
    if getattr(args, "command", None) == "loop":
        payload["lifecycle_trace"] = _lifecycle_trace_payload(args, lightweight=True)
    return payload


def _integration_merge_dispatch_payload(args: argparse.Namespace) -> dict[str, Any] | None:
    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    if MERGE_DISPATCH_TARGET_NAME in _running_managed_target_names_from_registry(
        Path(args.codex_home)
    ):
        return None
    review_payload = collect_integration_reviews(
        codex_home=Path(args.codex_home),
        base_ref="main",
        include_unfinished=False,
        run_test_gate=False,
        run_candidate_validation=False,
    )
    launch_spec = build_merge_dispatch_launch_spec(
        review_payload,
        cwd=str(_merge_dispatch_cwd(args)),
        requires_human_review=False,
    )
    if launch_spec is None:
        return None
    running_worker = _running_managed_process_by_name(
        codex_home=Path(args.codex_home),
        name=str(launch_spec["target_name"]),
    )
    payload: dict[str, Any] = {
        "status": "worker_already_running" if running_worker else "ready_to_launch",
        "integration_review": {
            "base_ref": review_payload.get("base_ref"),
            "summary": review_payload.get("summary") or {},
            "safety": review_payload.get("safety") or {},
        },
        "launch_spec": launch_spec,
    }
    if running_worker is not None:
        payload["running_worker"] = _managed_worker_reference(running_worker)
    return payload


def _merge_dispatch_already_running_action(
    merge_dispatch: dict[str, Any],
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "kind": "monitor",
        "reason": "merge worker already running",
    }
    if running_worker := merge_dispatch.get("running_worker"):
        action["managed"] = running_worker
    return action


def _merge_dispatch_already_running_executed(
    merge_dispatch: dict[str, Any],
) -> dict[str, Any]:
    executed = _merge_dispatch_already_running_action(merge_dispatch)
    executed["skipped"] = True
    return executed


def _merge_dispatch_planned_executed(merge_dispatch: dict[str, Any]) -> dict[str, Any]:
    launch_spec = merge_dispatch.get("launch_spec")
    target_name = (
        launch_spec.get("target_name") if isinstance(launch_spec, dict) else None
    )
    return {
        "kind": "launch_session",
        "display_kind": "merge_dispatch",
        "source": "integration_review",
        "target_name": target_name,
        "skipped": True,
        "reason": "merge dispatch launch not enabled",
    }


def _managed_worker_reference(record: Any) -> dict[str, Any]:
    return {
        "name": record.name,
        "record_id": record.record_id,
        "pid": record.pid,
        "backend": record.backend,
        "worker_role": getattr(record, "worker_role", "worker"),
    }


def _merge_dispatch_cwd(args: argparse.Namespace) -> Path:
    workspace_root = _workspace_root(args)
    return workspace_root if workspace_root is not None else Path.cwd()


def _recursive_worker_role_guard_payload(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    role = _current_workspace_worker_role(args, RECURSIVE_WORKER_ROLES)
    if role is None:
        return None
    reason = (
        "当前工作区是 merge worker，跳过 merge dispatch。"
        if role == MERGE_DISPATCH_WORKER_ROLE
        else f"当前工作区是 {role} worker，跳过递归调度。"
    )
    return {
        "status": "skipped_current_worker_role",
        "worker_role": role,
        "reason": reason,
    }


def _recursive_worker_role_guard_action(guard: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "monitor",
        "target_name": None,
        "reason": guard["reason"],
        "command_suggestion": None,
    }


def _recursive_worker_role_guard_executed(guard: dict[str, Any]) -> dict[str, Any]:
    executed = _recursive_worker_role_guard_action(guard)
    executed["skipped"] = True
    executed["worker_role"] = guard["worker_role"]
    return executed


def _current_workspace_has_worker_role(
    args: argparse.Namespace,
    roles: set[str],
) -> bool:
    return _current_workspace_worker_role(args, roles) is not None


def _current_workspace_worker_role(
    args: argparse.Namespace,
    roles: set[str],
) -> str | None:
    workspace = _workspace_root(args)
    if workspace is None:
        return None
    workspace_identity = _path_identity(str(workspace))
    if workspace_identity is None:
        return None
    for record in reversed(read_managed_records(default_registry_path(Path(args.codex_home)))):
        role = getattr(record, "worker_role", "worker")
        if role not in roles:
            continue
        if _path_identity(record.cwd) == workspace_identity:
            return role
    return None


def _active_goals_fanout_launch_plan(
    args: argparse.Namespace,
    report: Any,
    active_goals: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    fanout_goals = _fanout_candidate_active_goals(active_goals)
    targets = [
        target_name
        for goal in fanout_goals
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str) and target_name
    ]
    if len(targets) < 2:
        return None
    goal_plan = {
        "goals": fanout_goals,
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


def _goal_replenishment_wrote_goals(
    goal_replenishment: dict[str, Any] | None,
) -> bool:
    return (
        isinstance(goal_replenishment, dict)
        and goal_replenishment.get("status") == "ok"
        and _int_value(goal_replenishment.get("written_count")) > 0
    )


def _replenished_goal_plan_fanout_launch_plan(
    args: argparse.Namespace,
    report: Any,
    goal_replenishment: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    if not isinstance(goal_replenishment, dict):
        return None
    if goal_replenishment.get("status") != "ok":
        return None
    recommendations = goal_replenishment.get("parallel_recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        return None
    written_goals = goal_replenishment.get("written_goals")
    if not isinstance(written_goals, list) or not written_goals:
        return None
    return build_fanout_launch_plan(
        {
            "goals": written_goals,
            "parallel_recommendations": recommendations,
        },
        limit=getattr(args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT),
        running_target_names=_running_managed_target_names(report),
        requires_human_review=False,
    )


def _fanout_status_payload(
    report: Any,
    *,
    active_goals: list[dict[str, Any]],
    goal_updates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    payload = build_fanout_status_summary(
        active_goals=active_goals,
        goal_updates=goal_updates,
        running_target_names=_running_managed_target_names(report),
    )
    summary = payload.get("summary")
    if not isinstance(summary, dict) or summary.get("total", 0) < 2:
        return None
    if payload.get("status") == "idle":
        return None
    return payload


def _paused_active_goals_fanout_plan(
    args: argparse.Namespace,
    active_goals: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    blocked_targets = {
        target_name
        for goal in active_goals
        for target_name in (goal.get("target_name"),)
        if goal.get("last_status") in {"blocked", "needs_user"}
        and isinstance(target_name, str)
        and target_name
    }
    skipped = [
        {
            "target_name": target_name,
            "reason": "fanout_paused_for_attention",
            "batch": "active_goals",
        }
        for goal in active_goals
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str)
        and target_name
        and target_name not in blocked_targets
    ]
    return {
        "status": "paused",
        "summary": {
            "launchable": 0,
            "skipped": len(skipped),
            "limit": getattr(args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT),
        },
        "launch_specs": [],
        "skipped": skipped,
        "safety": {
            "auto_launch": False,
            "note": "fanout 已暂停，等待 blocked/needs_user worker 处理。",
        },
    }


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


def _fanout_paused_action(fanout_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "monitor",
        "target_name": None,
        "reason": fanout_status.get("message")
        or "fanout 已暂停，等待用户处理 blocked/needs_user worker。",
        "command_suggestion": None,
    }


def _fanout_paused_executed(fanout_status: dict[str, Any]) -> dict[str, Any]:
    action = _fanout_paused_action(fanout_status)
    return {
        "kind": "monitor",
        "skipped": True,
        "reason": action["reason"],
    }


def _fanout_log_payload(
    fanout_plan: dict[str, Any],
    *,
    goal_replenishment: dict[str, Any] | None = None,
    executed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_summary = fanout_plan.get("summary") if isinstance(fanout_plan, dict) else {}
    if not isinstance(plan_summary, dict):
        plan_summary = {}
    log = {
        "status": "executed" if executed is not None else "planned",
        "trigger": _fanout_trigger(goal_replenishment),
        "planned_launches": _int_value(plan_summary.get("launchable")),
        "planned_skips": _int_value(plan_summary.get("skipped")),
        "limit": _int_value(plan_summary.get("limit")),
    }
    if executed is not None:
        executed_summary = executed.get("summary")
        if not isinstance(executed_summary, dict):
            executed_summary = {}
        log["executed_launches"] = _int_value(executed_summary.get("launched"))
        log["executed_skips"] = _int_value(executed_summary.get("skipped"))
    return log


def _fanout_trigger(goal_replenishment: dict[str, Any] | None) -> str:
    if (
        isinstance(goal_replenishment, dict)
        and goal_replenishment.get("trigger") == "low_water"
        and goal_replenishment.get("status") == "ok"
        and _int_value(goal_replenishment.get("written_count")) > 0
    ):
        return "low_water"
    return "active_goals"


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _execute_fanout_launch_actions(
    args: argparse.Namespace,
    fanout_plan: dict[str, Any],
    *,
    report: Any | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_target_names: set[str] = set()
    for launch_spec in fanout_plan.get("launch_specs") or []:
        if not isinstance(launch_spec, dict):
            continue
        target_name = _optional_text(launch_spec.get("target_name"))
        if target_name is not None:
            if target_name in seen_target_names:
                skipped.append(
                    {
                        "kind": "launch_session",
                        "skipped": True,
                        "reason": "duplicate_fanout_target",
                        "target_name": target_name,
                    }
                )
                continue
            seen_target_names.add(target_name)
        result = _execute_failure_guarded_action(
            args,
            report=report,
            payload=payload or {},
            action=launch_spec,
            event_type="worker_launch_failed",
            execute=lambda launch_spec=launch_spec: _execute_launch_action(
                args,
                launch_spec,
            ),
        )
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
    payload["llm_followup_action"] = _decide_action_with_llm(args, report, payload)
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


def _dashboard_payload(
    report: Any,
    *,
    active_goals: list[dict[str, Any]] | None = None,
    decision_requests: list[dict[str, Any]] | None = None,
    notifications: list[dict[str, Any]] | None = None,
    multi_worker: dict[str, Any] | None = None,
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
        "multi_worker": multi_worker or _empty_multi_worker_payload(),
        "decision_requests": decision_requests or [],
        "notifications": notification_items,
        "notification_counts": {
            "total": len(notification_items),
            "unread": sum(1 for item in notification_items if item.get("unread") is True),
        },
    }


def _empty_multi_worker_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "store": {"root": "", "path": "", "format": "file_memory_store"},
        "filters": {"worker": None},
        "summary": {
            "worker_count": 0,
            "memory_records_total": 0,
            "worker_events_total": 0,
            "capacity_calls_total": 0,
            "hidden_workers": 0,
        },
        "workers": [],
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
        "target_name",
        "timeout_seconds",
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
    decision_timeout_alerts = payload.get("decision_timeout_alerts")
    if isinstance(decision_timeout_alerts, list) and decision_timeout_alerts:
        return (
            "supervise",
            "decision_timeout",
            tuple(
                sorted(
                    str(item.get("request_id"))
                    for item in decision_timeout_alerts
                    if isinstance(item, dict)
                )
            ),
        )
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
            webhook_url=args.webhook_url,
            webhook_secret=args.webhook_secret,
        )
        return {
            "status": "ok",
            "answered": answered,
            "decision_requests": _decision_request_dicts(args),
            "recent_decision_answers": _decision_answer_dicts(args),
        }
    raise ValueError(f"unsupported decision command: {args.decision_command}")


def _notify_integration_review_webhooks(
    args: argparse.Namespace,
    payload: dict[str, Any],
) -> None:
    webhook_url = getattr(args, "webhook_url", None)
    if not isinstance(webhook_url, str) or not webhook_url.strip():
        return
    groups = payload.get("groups")
    if not isinstance(groups, dict):
        return
    for group in ("ready_to_integrate", "already_integrated"):
        items = groups.get(group)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            protocol = item.get("supervisor_protocol")
            if not isinstance(protocol, dict):
                continue
            status = protocol.get("status")
            if not isinstance(status, str) or status.lower() != "done":
                continue
            record_id = item.get("record_id")
            if not isinstance(record_id, str) or not record_id.strip():
                continue
            notify_worker_integration_review_passed(
                record_id=record_id,
                group=group,
                status="done",
                webhook_url=webhook_url,
                webhook_secret=getattr(args, "webhook_secret", None),
            )


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



def _lifecycle_trace_payload(
    args: argparse.Namespace,
    *,
    lightweight: bool = False,
) -> dict[str, Any]:
    codex_home = Path(args.codex_home)
    active_goals = _active_goal_dicts_for_codex_home(codex_home, include_status=True)
    records = read_managed_records(default_registry_path(codex_home))
    record_limit = 40 if lightweight else None
    visible_records = records[-record_limit:] if record_limit else records
    active_records = [
        _managed_record_trace_dict(record)
        for record in visible_records
    ]
    archived_events = [
        record
        for record in _latest_managed_record_events(codex_home)
        if record.status == "archived"
    ]
    archive_limit = 20 if lightweight else None
    visible_archived_events = (
        archived_events[-archive_limit:] if archive_limit else archived_events
    )
    archived_records = [
        _managed_record_trace_dict(record)
        for record in visible_archived_events
    ]
    active_decisions = _decision_request_dicts(args)
    recent_decision_answers = _decision_answer_dicts(args)
    merge_workers = [
        record
        for record in active_records
        if record.get("worker_role") == MERGE_DISPATCH_WORKER_ROLE
    ]
    repair_workers = [
        record
        for record in active_records
        if record.get("worker_role") == MERGE_REPAIR_WORKER_ROLE
    ]
    stages = {
        "goal_queue": {
            "active": active_goals,
        },
        "workers": {
            "active": active_records,
        },
        "merge": {
            "merge_workers": merge_workers,
            "repair_workers": repair_workers,
        },
        "decisions": {
            "active": active_decisions,
            "recent_answers": recent_decision_answers,
        },
        "cleanup": {
            "candidates": _cleanup_candidate_dicts(codex_home),
            "archived_workers": archived_records,
        },
    }
    summary = {
        "active_goals": len(active_goals),
        "active_managed_workers": len(records),
        "visible_managed_workers": len(active_records),
        "hidden_managed_workers": len(records) - len(active_records),
        "active_decisions": len(active_decisions),
        "merge_workers": len(merge_workers),
        "repair_workers": len(repair_workers),
        "archived_workers": len(archived_events),
        "visible_archived_workers": len(archived_records),
        "hidden_archived_workers": len(archived_events) - len(archived_records),
    }
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "next_attention": _lifecycle_next_attention(stages),
        "stages": _lightweight_lifecycle_stages(stages) if lightweight else stages,
    }


def _lightweight_lifecycle_stages(stages: dict[str, Any]) -> dict[str, Any]:
    workers = stages.get("workers") if isinstance(stages.get("workers"), dict) else {}
    goals = stages.get("goal_queue") if isinstance(stages.get("goal_queue"), dict) else {}
    decisions = stages.get("decisions") if isinstance(stages.get("decisions"), dict) else {}
    merge = stages.get("merge") if isinstance(stages.get("merge"), dict) else {}
    cleanup = stages.get("cleanup") if isinstance(stages.get("cleanup"), dict) else {}
    return {
        "goal_queue": {
            "active_count": len(goals.get("active", [])),
        },
        "workers": {
            "active_count": len(workers.get("active", [])),
            "active": [
                _lightweight_lifecycle_worker(worker)
                for worker in workers.get("active", [])
                if isinstance(worker, dict)
            ],
        },
        "merge": {
            "merge_worker_count": len(merge.get("merge_workers", [])),
            "repair_worker_count": len(merge.get("repair_workers", [])),
        },
        "decisions": {
            "active_count": len(decisions.get("active", [])),
            "recent_answer_count": len(decisions.get("recent_answers", [])),
        },
        "cleanup": {
            "candidate_count": len(cleanup.get("candidates", [])),
            "candidates": [
                _lightweight_cleanup_candidate(candidate)
                for candidate in cleanup.get("candidates", [])[:20]
                if isinstance(candidate, dict)
            ],
            "archived_worker_count": len(cleanup.get("archived_workers", [])),
        },
    }


def _lightweight_lifecycle_worker(worker: dict[str, Any]) -> dict[str, Any]:
    return _drop_none_values(
        {
            "name": worker.get("name"),
            "record_id": worker.get("record_id"),
            "status": worker.get("status"),
            "worker_role": worker.get("worker_role"),
            "protocol": worker.get("protocol"),
            "still_working": worker.get("still_working"),
        }
    )


def _lightweight_cleanup_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return _drop_none_values(
        {
            "kind": candidate.get("kind"),
            "name": candidate.get("name") or candidate.get("target_name"),
            "goal_id": candidate.get("goal_id"),
            "record_id": candidate.get("record_id"),
            "notification_id": candidate.get("notification_id"),
            "archived": candidate.get("archived"),
        }
    )


def _latest_managed_record_events(codex_home: Path) -> list[Any]:
    latest_by_record_id: dict[str, Any] = {}
    for record in read_managed_record_events(default_registry_path(codex_home)):
        latest_by_record_id[record.record_id] = record
    return list(latest_by_record_id.values())


def _managed_record_trace_dict(record: Any) -> dict[str, Any]:
    protocol = _managed_record_supervisor_protocol(record)
    return _drop_none_values(
        {
            "name": record.name,
            "record_id": record.record_id,
            "cwd": record.cwd,
            "pid": record.pid,
            "backend": record.backend,
            "tmux_session": record.tmux_session,
            "status": record.status,
            "worker_role": getattr(record, "worker_role", "worker"),
            "started_at": record.started_at,
            "resume_session_id": record.resume_session_id,
            "resume_last": record.resume_last or None,
            "protocol": protocol or None,
            "still_working": _managed_record_is_still_working(record),
        }
    )


def _lifecycle_next_attention(stages: dict[str, Any]) -> dict[str, Any]:
    decisions = stages.get("decisions")
    active_decisions = (
        decisions.get("active")
        if isinstance(decisions, dict) and isinstance(decisions.get("active"), list)
        else []
    )
    if active_decisions:
        first = active_decisions[0]
        return {
            "kind": "answer_decision",
            "request_id": first.get("request_id"),
            "target_name": first.get("target_name"),
        }
    cleanup = stages.get("cleanup")
    cleanup_candidates = (
        cleanup.get("candidates")
        if isinstance(cleanup, dict) and isinstance(cleanup.get("candidates"), list)
        else []
    )
    if cleanup_candidates:
        first = cleanup_candidates[0]
        return {
            "kind": "archive_cleanup",
            "target": first.get("name")
            or first.get("goal_id")
            or first.get("notification_id"),
        }
    workers = stages.get("workers")
    active_workers = (
        workers.get("active")
        if isinstance(workers, dict) and isinstance(workers.get("active"), list)
        else []
    )
    waiting_workers = [
        worker
        for worker in active_workers
        if _lifecycle_worker_is_waiting(worker)
    ]
    if waiting_workers:
        return {
            "kind": "wait_workers",
            "active_managed_workers": len(waiting_workers),
        }
    merge = stages.get("merge")
    repair_workers = (
        merge.get("repair_workers")
        if isinstance(merge, dict) and isinstance(merge.get("repair_workers"), list)
        else []
    )
    for worker in repair_workers:
        protocol = worker.get("protocol")
        status = protocol.get("status") if isinstance(protocol, dict) else None
        if status != "done":
            return {
                "kind": "wait_repair",
                "target_name": worker.get("name"),
            }
    goals = stages.get("goal_queue")
    active_goals = (
        goals.get("active")
        if isinstance(goals, dict) and isinstance(goals.get("active"), list)
        else []
    )
    if active_goals:
        return {
            "kind": "continue_goal",
            "target_name": active_goals[0].get("target_name"),
        }
    return {"kind": "idle"}


def _lifecycle_worker_is_waiting(worker: Any) -> bool:
    if not isinstance(worker, dict):
        return False
    protocol = worker.get("protocol")
    protocol_status = (
        protocol.get("status")
        if isinstance(protocol, dict) and isinstance(protocol.get("status"), str)
        else None
    )
    if protocol_status in {"done", "blocked", "needs_user"}:
        return False
    if worker.get("still_working") is True:
        return True
    record_status = worker.get("status")
    return record_status in {"launched", "resumed", "adopted"}


def _print_lifecycle_trace_plain(payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    print("Supervisor 生命周期 trace")
    print(f"- active goals: {summary.get('active_goals', 0)}")
    print(f"- active workers: {summary.get('active_managed_workers', 0)}")
    print(f"- active decisions: {summary.get('active_decisions', 0)}")
    print(f"- merge workers: {summary.get('merge_workers', 0)}")
    print(f"- repair workers: {summary.get('repair_workers', 0)}")
    print(f"- archived workers: {summary.get('archived_workers', 0)}")
    attention = payload.get("next_attention") or {}
    print(f"下一关注：{attention.get('kind', 'unknown')}")


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
    if cleanup_archived := payload.get("cleanup_archived"):
        print()
        print("[自动归档]")
        for item in cleanup_archived:
            target = item.get("name") or item.get("record_id")
            print(f"{item.get('kind', 'item')} {target}")
    if cleanup_deleted_worktrees := payload.get("cleanup_deleted_worktrees"):
        print()
        print("[自动 worktree 清理]")
        for item in cleanup_deleted_worktrees:
            target = item.get("target_name") or item.get("record_id")
            if item.get("deleted_worktree"):
                print(f"{target} / {item['deleted_worktree']}")
            else:
                print(f"{target} / {item.get('reason', 'skipped')}")
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
        print(f"{_llm_action_activity_kind(llm_action)} / {llm_action['reason']}")
        _print_ask_user_action_plain(llm_action)
    if llm_followup_action := payload.get("llm_followup_action"):
        print()
        print("[LLM 同轮后续动作]")
        print(
            f"{_llm_action_activity_kind(llm_followup_action)} / "
            f"{llm_followup_action['reason']}"
        )
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
        payload["llm_action"] = _decide_action_with_llm(args, action_report, payload)
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
        print(f"已跳过：{_executed_activity_detail(executed, executed['reason'])}")
        return
    print(f"已执行：{_executed_activity_detail(executed, executed['command'])}")


def _llm_action_activity_kind(action: dict[str, Any]) -> str:
    kind = str(action.get("kind") or "unknown")
    if _is_merge_dispatch_launch_action(action):
        return "merge_dispatch"
    return kind


def _is_merge_dispatch_launch_action(action: dict[str, Any]) -> bool:
    return (
        action.get("kind") == "launch_session"
        and action.get("source") == "integration_review"
        and action.get("target_name") == MERGE_DISPATCH_TARGET_NAME
    )


def _mark_merge_dispatch_execution(executed: dict[str, Any]) -> dict[str, Any]:
    if executed.get("kind") == "launch_session":
        executed["display_kind"] = "merge_dispatch"
        executed["source"] = "integration_review"
    return executed


def _executed_activity_detail(executed: dict[str, Any], detail: str) -> str:
    display_kind = executed.get("display_kind")
    if isinstance(display_kind, str) and display_kind:
        return f"{display_kind} / {detail}"
    return detail


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
    if _should_wait_for_running_worker(report, active_goals):
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


def _should_wait_for_running_worker(
    report: Any,
    active_goals: list[dict[str, Any]] | None,
) -> bool:
    running_names = _running_managed_target_names(report)
    if MERGE_DISPATCH_TARGET_NAME in running_names:
        return True
    active_target_names = {
        target_name
        for goal in active_goals or []
        if isinstance(goal, dict)
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str) and target_name
    }
    return bool(active_target_names & running_names)


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
        return _execute_failure_guarded_action(
            args,
            report=report,
            payload=payload,
            action=action,
            event_type="resume_failed",
            execute=lambda: _execute_resume_action(args, report, action),
        )
    if kind == "launch_session":
        return _execute_failure_guarded_action(
            args,
            report=report,
            payload=payload,
            action=action,
            event_type="worker_launch_failed",
            execute=lambda: _execute_launch_action(args, action),
        )
    if kind == "request_context":
        if budget_result := _context_request_budget_result(args, payload):
            return budget_result
        return _execute_failure_guarded_action(
            args,
            report=report,
            payload=payload,
            action=action,
            event_type="context_retrieval_failed",
            execute=lambda: _execute_context_action(args, action),
        )
    if kind == "ask_user":
        return _execute_ask_user_action(args, action)
    if kind == "delete_worktree":
        return _execute_delete_worktree_action(args, action)
    return _execute_advice(
        args,
        report,
        payload,
        kind=kind,
        target_name=action.get("target_name"),
    )


def _execute_failure_guarded_action(
    args: argparse.Namespace,
    *,
    report: Any,
    payload: dict[str, Any],
    action: dict[str, Any],
    event_type: str,
    execute: Any,
) -> dict[str, Any]:
    try:
        result = execute()
    except Exception as exc:  # noqa: BLE001 - failed lane should not stop the loop.
        summary = _exception_summary(exc)
        event = _record_failure_event(
            args,
            event_type=event_type,
            report=report,
            payload=payload,
            action=action,
            error_summary=summary,
        )
        if _failure_retry_exhausted(args, event):
            return _execute_ask_user_action(
                args,
                _failure_decision_request_action(
                    event=event,
                    question=_failure_question(event_type),
                    reason=f"{event_type} retry limit exceeded",
                ),
            )
        return {
            "kind": action.get("kind") or event_type,
            "skipped": True,
            "reason": "supervisor action failed",
            "error": summary,
            "failure_event": event,
        }
    if not isinstance(result, dict):
        return result
    skipped_event_type = _failure_event_type_for_skipped_result(
        action,
        result,
        fallback_event_type=event_type,
    )
    if skipped_event_type is None:
        return result
    event = _record_failure_event(
        args,
        event_type=skipped_event_type,
        report=report,
        payload=payload,
        action=action,
        error_summary=str(result.get("reason") or "supervisor action skipped"),
    )
    result = {**result, "failure_event": event}
    if _failure_retry_exhausted(args, event):
        return _execute_ask_user_action(
            args,
            _failure_decision_request_action(
                event=event,
                question=_failure_question(skipped_event_type),
                reason=f"{skipped_event_type} retry limit exceeded",
            ),
        )
    return result


def _failure_event_type_for_skipped_result(
    action: dict[str, Any],
    result: dict[str, Any],
    *,
    fallback_event_type: str,
) -> str | None:
    if result.get("skipped") is not True:
        return None
    reason = result.get("reason")
    if not isinstance(reason, str):
        return None
    if _is_merge_dispatch_launch_action(action):
        return "merge_dispatch_failed"
    if reason in {"launch cwd missing", "worktree setup failed"}:
        return "worker_launch_failed"
    if reason == "resume cwd missing":
        return "resume_failed"
    if reason == "request_context cwd missing":
        return "context_retrieval_failed"
    if reason == "supervisor action failed":
        return fallback_event_type
    return None


def _exception_summary(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return type(exc).__name__
    return f"{type(exc).__name__}: {message}"


def _failure_question(event_type: str) -> str:
    questions = {
        "llm_planner_invalid_response": (
            "Supervisor LLM planner 连续返回无效动作，请确认是否调整配置或改为人工处理当前目标。"
        ),
        "worker_launch_failed": (
            "Supervisor 连续启动 worker 失败，请确认是否修复启动环境或跳过当前目标。"
        ),
        "resume_failed": (
            "Supervisor 连续 resume 会话失败，请确认是否改为重新启动 worker 或人工接管。"
        ),
        "context_retrieval_failed": (
            "Supervisor 连续检索上下文失败，请确认是否修复路径或跳过当前目标。"
        ),
        "merge_dispatch_failed": (
            "Supervisor 连续派发 merge worker 失败，请确认是否人工处理合并。"
        ),
        "worker_retry_failed": (
            "Supervisor 已达到 worker 自动重启上限但仍失败，请确认是否拆分目标、修复环境或人工接管。"
        ),
    }
    return questions.get(
        event_type,
        "Supervisor 连续遇到同类失败，请确认下一步处理方式。",
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
    if failure_state := lane_failure_state(
        codex_home=Path(args.codex_home),
        name=target_name,
    ):
        return {
            "kind": "monitor",
            "skipped": True,
            "reason": "worker failure recorded",
            "degraded_from": "launch_session",
            "target_name": target_name,
            "lane_state": failure_state.to_dict(),
        }
    if run_budget := _run_budget_state(
        codex_home=Path(args.codex_home),
        name=target_name,
        max_run_minutes=args.max_run_minutes,
    ):
        failure_state = record_lane_failure(
            codex_home=Path(args.codex_home),
            name=target_name,
            tmux_session=None,
            reason="timeout",
            stderr_summary="worker exceeded run budget",
        )
        return {
            "kind": "monitor",
            "skipped": True,
            "reason": "worker timeout recorded",
            "degraded_from": "launch_session",
            "target_name": target_name,
            "lane_state": failure_state.to_dict(),
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
    worker_role = _worker_role_for_launch_action(action)
    work_order_prompt = build_launch_work_order_prompt(
        target_name=target_name,
        cwd=worker_cwd,
        goal=prompt,
        allow_remote_push=worker_role == MERGE_DISPATCH_WORKER_ROLE,
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
        worker_role=worker_role,
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
            "worker_role": record.worker_role,
        },
        "worktree": worktree,
    }


def _worker_role_for_launch_action(action: dict[str, Any]) -> str:
    role = action.get("worker_role")
    if isinstance(role, str) and role.strip():
        return role.strip()
    if action.get("source") == "integration_review":
        return MERGE_DISPATCH_WORKER_ROLE
    return "worker"


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
        webhook_url=args.webhook_url,
        webhook_secret=args.webhook_secret,
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


def _execute_delete_worktree_action(
    args: argparse.Namespace,
    action: dict[str, Any],
) -> dict[str, Any]:
    target_name = action.get("target_name") or action.get("name")
    record_id = action.get("record_id")
    if not isinstance(target_name, str) or not target_name.strip():
        raise ValueError("target_name is required for delete_worktree")
    if record_id is not None and not isinstance(record_id, str):
        raise ValueError("record_id must be a string for delete_worktree")
    if action.get("confirm_delete_worktree") is not True:
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "missing delete_worktree confirmation",
        }
    record = _latest_managed_record_event(
        codex_home=Path(args.codex_home),
        target_name=target_name,
        record_id=record_id,
    )
    if record is None:
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "managed worker not found",
        }
    if record.status != "archived":
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "managed worker is not archived",
            "managed": _managed_record_ref(record),
        }
    protocol = _supervisor_protocol_from_text(
        _managed_process_log_excerpt(record.log_path) or ""
    )
    if (protocol.get("status") or "").strip().lower() != "done":
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "managed worker is not done",
            "managed": _managed_record_ref(record),
            "supervisor_protocol": protocol,
        }
    worktree = _supervisor_worktree_root_for_cwd(record.cwd)
    if worktree is None:
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "worktree is outside .worktrees/supervisor",
            "managed": _managed_record_ref(record),
            "cwd": record.cwd,
        }
    if not worktree["worktree_root"].is_dir():
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "worktree missing",
            "managed": _managed_record_ref(record),
            "worktree_root": str(worktree["worktree_root"]),
        }
    integration = review_managed_record_integration(
        record,
        base_ref=str(action.get("base_ref") or "main"),
        run=subprocess.run,
    )
    if not _integration_review_allows_worktree_delete(integration):
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "worker is not integrated",
            "managed": _managed_record_ref(record),
            "integration": _delete_worktree_integration_summary(integration),
        }
    command = [
        "git",
        "-C",
        str(worktree["repo_root"]),
        "worktree",
        "remove",
        str(worktree["worktree_root"]),
    ]
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )
    command_text = shlex.join(command)
    if completed.returncode != 0:
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "command": command_text,
            "skipped": True,
            "reason": "git worktree remove failed",
            "managed": _managed_record_ref(record),
            "worktree_root": str(worktree["worktree_root"]),
            "stderr": (completed.stderr or completed.stdout or "").strip(),
        }
    return {
        "kind": "delete_worktree",
        "target_name": target_name,
        "command": command_text,
        "deleted_worktree": str(worktree["worktree_root"]),
        "managed": _managed_record_ref(record),
        "integration": _delete_worktree_integration_summary(integration),
    }


def _delete_worktree_candidate_payloads(args: argparse.Namespace) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in _latest_managed_record_events(Path(args.codex_home)):
        if record.status != "archived":
            continue
        if _supervisor_worktree_root_for_cwd(record.cwd) is None:
            continue
        protocol = _supervisor_protocol_from_text(
            _managed_process_log_excerpt(record.log_path) or ""
        )
        if (protocol.get("status") or "").strip().lower() != "done":
            continue
        integration = review_managed_record_integration(record, run=subprocess.run)
        if not _integration_review_allows_worktree_delete(integration):
            continue
        candidates.append(
            {
                "name": record.name,
                "target_name": record.name,
                "record_id": record.record_id,
                "cwd": record.cwd,
                "archived": True,
                "integration_group": integration.get("group"),
                "main_contains_worker": integration.get("main_contains_worker"),
                "main_has_worker_patch": integration.get("main_has_worker_patch"),
                "worker_commit": integration.get("worker_commit"),
                "base_ref": integration.get("base_ref"),
            }
        )
    return candidates


def _latest_managed_record_event(
    *,
    codex_home: Path,
    target_name: str,
    record_id: str | None,
) -> Any | None:
    for record in reversed(read_managed_record_events(default_registry_path(codex_home))):
        if record_id is not None and record.record_id != record_id:
            continue
        if record.name == target_name:
            return record
    return None


def _latest_managed_record_events(codex_home: Path) -> list[Any]:
    latest: dict[str, Any] = {}
    for record in read_managed_record_events(default_registry_path(codex_home)):
        latest[record.record_id] = record
    return list(latest.values())


def _managed_record_ref(record: Any) -> dict[str, Any]:
    return {
        "name": record.name,
        "record_id": record.record_id,
        "status": record.status,
        "cwd": record.cwd,
    }


def _supervisor_worktree_root_for_cwd(cwd: str) -> dict[str, Path] | None:
    path = Path(cwd).expanduser().resolve(strict=False)
    parts = path.parts
    for index in range(0, len(parts) - 2):
        if parts[index] != ".worktrees" or parts[index + 1] != "supervisor":
            continue
        repo_root = Path(*parts[:index])
        worktree_root = Path(*parts[: index + 3])
        if worktree_root.parent.name != "supervisor":
            return None
        return {"repo_root": repo_root, "worktree_root": worktree_root}
    return None


def _integration_review_allows_worktree_delete(integration: dict[str, Any]) -> bool:
    return (
        integration.get("group") in {"already_integrated", "merge_workers"}
        and integration.get("dirty") is False
        and (
            integration.get("main_contains_worker") is True
            or integration.get("main_has_worker_patch") is True
        )
    )


def _delete_worktree_integration_summary(integration: dict[str, Any]) -> dict[str, Any]:
    return {
        "group": integration.get("group"),
        "reason": integration.get("reason"),
        "worker_commit": integration.get("worker_commit"),
        "base_ref": integration.get("base_ref"),
        "main_contains_worker": integration.get("main_contains_worker"),
        "main_has_worker_patch": integration.get("main_has_worker_patch"),
        "dirty": integration.get("dirty"),
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


def _decide_action_with_llm(
    args: argparse.Namespace,
    report: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not _has_llm_action_target(
        report,
        payload.get("command_suggestions"),
        payload.get("delete_worktree_candidates"),
    ):
        return generate_llm_action_decision(
            report,
            payload["command_suggestions"],
            _UnavailableSummaryProvider(),
            payload.get("recent_context_results"),
            payload.get("active_goals"),
            payload.get("recent_decision_answers"),
            payload.get("worker_reviews"),
            payload.get("delete_worktree_candidates"),
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
            payload.get("delete_worktree_candidates"),
        )
    except ValueError as exc:
        error = str(exc)
        failure_event = _record_failure_event(
            args,
            event_type="llm_planner_invalid_response",
            report=report,
            payload=payload,
            error_summary=error,
        )
        if _failure_retry_exhausted(args, failure_event):
            return _failure_decision_request_action(
                event=failure_event,
                question="Supervisor LLM planner 连续返回无效动作，请确认是否调整配置或改为人工处理当前目标。",
                reason="LLM planner failure retry limit exceeded",
            )
        reason = f"LLM 动作无效，已跳过执行：{error}"
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": reason,
            "command_suggestion": None,
            "error": error,
        }


def _record_failure_event(
    args: argparse.Namespace,
    *,
    event_type: str,
    report: Any | None = None,
    payload: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
    error_summary: str,
) -> dict[str, Any]:
    ledger = FailureLedger(default_failure_ledger_path(Path(args.codex_home)))
    lane_name = _failure_lane_name(args, report=report, payload=payload, action=action)
    goal_id = _failure_goal_id(payload=payload, action=action, lane_name=lane_name)
    return ledger.record_failure(
        event_type=event_type,
        lane_name=lane_name,
        goal_id=goal_id,
        error_summary=error_summary,
    )


def _failure_retry_exhausted(
    args: argparse.Namespace,
    event: dict[str, Any],
) -> bool:
    retry_count = event.get("retry_count")
    max_retries = getattr(args, "max_failure_retries", DEFAULT_MAX_FAILURE_RETRIES)
    return isinstance(retry_count, int) and retry_count > max_retries


def _failure_decision_request_action(
    *,
    event: dict[str, Any],
    question: str,
    reason: str,
) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "supervisor_failure")
    lane_name = event.get("lane_name")
    lane_text = lane_name if isinstance(lane_name, str) and lane_name else "global"
    goal_id = event.get("goal_id")
    return {
        "kind": "ask_user",
        "session_id": f"failure:{event_type}:{lane_text}",
        "target_name": lane_name if isinstance(lane_name, str) else None,
        **({"goal_id": goal_id} if isinstance(goal_id, str) and goal_id else {}),
        "question": question,
        "reason": reason,
        "context_status": "conflict",
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "command_suggestion": None,
        "failure_event": event,
    }


def _failure_lane_name(
    args: argparse.Namespace,
    *,
    report: Any | None = None,
    payload: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
) -> str | None:
    for value in (
        action.get("target_name") if isinstance(action, dict) else None,
        getattr(args, "name", None),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    if report is not None:
        for session in getattr(report, "sessions", []):
            name = getattr(session, "managed_name", None)
            if isinstance(name, str) and name:
                return name
    if isinstance(payload, dict):
        for goal in payload.get("active_goals") or []:
            if isinstance(goal, dict):
                name = goal.get("target_name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    return None


def _failure_goal_id(
    *,
    payload: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
    lane_name: str | None = None,
) -> str | None:
    if isinstance(action, dict):
        goal_id = action.get("goal_id")
        if isinstance(goal_id, str) and goal_id.strip():
            return goal_id.strip()
    if isinstance(payload, dict):
        for goal in payload.get("active_goals") or []:
            if not isinstance(goal, dict):
                continue
            goal_id = goal.get("goal_id")
            target_name = goal.get("target_name")
            if not isinstance(goal_id, str) or not goal_id.strip():
                continue
            if lane_name is None or target_name == lane_name:
                return goal_id.strip()
    return None


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
    return collect_worker_reviews(codex_home=Path(args.codex_home), lightweight=True)


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
    delete_worktree_candidates: Any = None,
) -> bool:
    if isinstance(delete_worktree_candidates, list) and delete_worktree_candidates:
        return True
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
