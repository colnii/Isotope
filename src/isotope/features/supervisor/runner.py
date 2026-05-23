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

from isotope.capabilities.runner import CapabilityRunner
from .context import (
    read_recent_context_results,
    request_project_context,
)
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
    build_active_goals_fanout_launch_plan,
    build_fanout_launch_plan,
    build_fanout_status_summary,
    build_paused_active_goals_fanout_plan,
    build_replenished_goal_plan_fanout_launch_plan,
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
from ...agents.scheduler.goal_queue import (
    active_goal_is_deferred,
    filter_fanout_candidate_goals,
    filter_replenishment_counted_goals,
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
    build_merge_dispatch_payload,
    merge_dispatch_already_running_action as _merge_dispatch_already_running_action,
    merge_dispatch_already_running_executed as _merge_dispatch_already_running_executed,
    merge_dispatch_planned_executed as _merge_dispatch_planned_executed,
)
from .merge_promotion import (
    check_main_promotion_preconditions as _check_main_promotion_preconditions,
    ci_run_is_terminal as _ci_run_is_terminal,
    ci_run_succeeded as _ci_run_succeeded,
    git_text as _git_text,
    latest_ci_run_for_ref as _latest_ci_run_for_ref,
    merge_promotion_decision_intent as _merge_promotion_decision_intent,
    merge_promotion_repair_prompt as _merge_promotion_repair_prompt,
    run_checked as _run_checked,
    view_ci_run as _view_ci_run,
)
from .merge_repair import (
    blocked_merge_worker_cwd as _blocked_merge_worker_cwd,
    merge_dispatch_conflict_repair_prompt as _merge_dispatch_conflict_repair_prompt,
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
from .commands.parser import (
    _build_parser_impl,
    build_parser as _build_parser,
)
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
from .commands.capacity import handle_capacity_command as _handle_capacity_command
from .commands.dashboard import (
    best_linked_session_for_managed as _best_linked_session_for_managed,
    best_linked_sessions_for_managed_lanes as _best_linked_sessions_for_managed_lanes,
    dashboard_active_goal_item as _dashboard_active_goal_item,
    dashboard_current_payload as _dashboard_current_payload,
    dashboard_display_sessions as _dashboard_display_sessions,
    dashboard_group_for as _dashboard_group_for,
    dashboard_item as _dashboard_item,
    dashboard_item_is_current as _dashboard_item_is_current,
    dashboard_item_suffix as _dashboard_item_suffix,
    dashboard_notification_dict as _dashboard_notification_dict,
    dashboard_notification_source_ref as _dashboard_notification_source_ref,
    dashboard_payload as _dashboard_payload,
    dashboard_status_source as _dashboard_status_source,
    dependency_batch_items as _dependency_batch_items,
    dependency_blocked_text as _dependency_blocked_text,
    dependency_item_name as _dependency_item_name,
    empty_multi_worker_payload as _empty_multi_worker_payload,
    handle_dashboard_command as _handle_dashboard_command,
    is_current_managed_worker as _is_current_managed_worker,
    is_missing_supervisor_worktree as _is_missing_supervisor_worktree,
    managed_link_analysis as _managed_link_analysis,
    managed_link_score as _managed_link_score,
    normalize_match_text as _normalize_match_text,
    notification_dicts as _notification_dicts,
    print_dashboard_dependency_batch as _print_dashboard_dependency_batch,
    print_dashboard_plain as _print_dashboard_plain,
    current_batch_payload as _current_batch_payload,
    current_batch_payload_from_display_sessions as _current_batch_payload_from_display_sessions,
)
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
from .commands.onboarding import (
    discover_payload as _discover_payload,
    guide_payload as _guide_payload,
    guide_worker_codex_args as _guide_worker_codex_args,
    print_discover_plain as _print_discover_plain,
    print_guide_plain as _print_guide_plain,
    print_start_here_plain as _print_start_here_plain,
    selected_discover_candidate as _selected_discover_candidate,
    start_here_payload as _start_here_payload,
)
from .commands.advice import (
    active_goal_action_command_suggestions as _active_goal_action_command_suggestions,
    advice_payload as _advice_payload,
    automation_status as _automation_status,
    command_suggestions as _command_suggestions,
    dedupe_command_suggestions as _dedupe_command_suggestions,
    first_managed_tmux_session as _first_managed_tmux_session,
    goal_action_command_suggestions as _goal_action_command_suggestions,
    is_active_managed_process_session as _is_active_managed_process_session,
    is_active_managed_tmux_session as _is_active_managed_tmux_session,
    is_completed_session as _is_completed_session,
    is_resume_capable_session as _is_resume_capable_session,
    managed_tmux_command_suggestions as _managed_tmux_command_suggestions,
    managed_tmux_session_by_name as _managed_tmux_session_by_name,
    resume_managed_name_for_session as _resume_managed_name_for_session,
    resume_session_command_suggestion as _resume_session_command_suggestion,
    resume_session_command_suggestions as _resume_session_command_suggestions,
    running_managed_target_names as _running_managed_target_names,
    running_managed_target_names_from_registry as _running_managed_target_names_from_registry,
    should_wait_for_running_worker as _should_wait_for_running_worker,
    watch_command_suggestion as _watch_command_suggestion,
    workspace_action_command_suggestions as _workspace_action_command_suggestions,
    workspace_context_command_suggestion as _workspace_context_command_suggestion,
    workspace_cwds as _workspace_cwds,
    workspace_launch_command_suggestion as _workspace_launch_command_suggestion,
)
from .commands.daemon_command import (
    codex_worker_options_from_command as _codex_worker_options_from_command,
    daemon_activity_payload as _daemon_activity_payload,
    daemon_integration_reviews as _daemon_integration_reviews,
    daemon_managed_worker_payload as _daemon_managed_worker_payload,
    daemon_managed_worker_payloads as _daemon_managed_worker_payloads,
    daemon_payload as _daemon_payload,
    max_run_minutes_from_daemon_command as _max_run_minutes_from_daemon_command,
    overnight_check_payload as _overnight_check_payload,
    print_daemon_activity_plain as _print_daemon_activity_plain,
    print_daemon_plain as _print_daemon_plain,
    print_overnight_check_plain as _print_overnight_check_plain,
    print_watcher_plain as _print_watcher_plain,
    print_watcher_run_plain as _print_watcher_run_plain,
    queue_daemon_goal_from_args as _queue_daemon_goal_from_args,
    read_tail_text as _read_tail_text,
    recent_ci_from_log as _recent_ci_from_log,
    recent_execution_from_log as _recent_execution_from_log,
    recent_llm_action_from_log as _recent_llm_action_from_log,
    recent_worker_payload as _recent_worker_payload,
    run_daemon_watcher as _run_daemon_watcher,
    start_daemon_from_args as _start_daemon_from_args,
    status_detail_from_text as _status_detail_from_text,
    up_payload as _up_payload,
    watcher_payload as _watcher_payload,
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
from isotope.core.time import (
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
from isotope.memory.worker_event_channel import (
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


def main(argv: list[str] | None = None) -> int:
    return _run_cli(argv)


_COMMAND_HANDLERS = {
    "dashboard": _handle_dashboard_command,
    "integration-review": _handle_integration_review_command,
    "merge-work-order": _handle_merge_work_order_command,
    "goal": _handle_goal_command,
    "cleanup": _handle_cleanup_command,
    "capacity": _handle_capacity_command,
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
        if failure is not None and failure.get("reason") == "usage_limit":
            _ensure_worker_retry_decision_request(
                args,
                record=record,
                state=state,
                failure=failure,
                max_retries=max_retries,
            )
            continue
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
    usage_limit = _usage_limit_failure(excerpt)
    if usage_limit is not None:
        return usage_limit
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


def _usage_limit_failure(excerpt: str) -> dict[str, Any] | None:
    lowered = excerpt.lower()
    if (
        "you've hit your usage limit" not in lowered
        and "you have hit your usage limit" not in lowered
    ):
        return None
    return {
        "reason": "usage_limit",
        "exit_code": None,
        "stderr_summary": _stderr_summary_from_excerpt(excerpt),
    }


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


def _auto_repair_blocked_merge_worker_review_item(
    item: dict[str, Any],
    *,
    args: argparse.Namespace,
    codex_home: Path,
) -> dict[str, Any] | None:
    if not _merge_worker_review_item_is_blocked(item):
        return None
    name = _non_empty_text(item.get("name")) or MERGE_DISPATCH_TARGET_NAME
    record_id = _non_empty_text(item.get("record_id"))
    if not record_id:
        return None
    repair_name = f"{name}-repair"
    record = _managed_record_by_id(codex_home=codex_home, record_id=record_id)
    if record is not None and record.backend != "tmux" and _pid_is_running(record.pid):
        return {
            "kind": "merge_worker_conflict_repair",
            "name": name,
            "record_id": record_id,
            "status": "merge_worker_still_running",
        }
    if running_worker := _running_managed_process_by_name(
        codex_home=codex_home,
        name=repair_name,
    ):
        return {
            "kind": "merge_worker_conflict_repair",
            "name": name,
            "record_id": record_id,
            "status": "repair_already_running",
            "repair": _managed_worker_reference(running_worker),
        }
    if previous_repair := _latest_managed_record_by_name(
        codex_home=codex_home,
        name=repair_name,
    ):
        protocol = _supervisor_protocol_from_text(
            _managed_process_log_excerpt(previous_repair.log_path) or ""
        )
        status = str(protocol.get("status") or "").strip().lower()
        if status in {"done", "blocked", "needs_user"}:
            return {
                "kind": "merge_worker_conflict_repair",
                "name": name,
                "record_id": record_id,
                "status": f"repair_{status}",
                "repair": _managed_worker_reference(previous_repair),
            }
    if cooldown_state := prompt_cooldown_state(
        codex_home=codex_home,
        name=repair_name,
        cooldown_seconds=getattr(args, "prompt_cooldown", DEFAULT_PROMPT_COOLDOWN_SECONDS),
    ):
        return {
            "kind": "merge_worker_conflict_repair",
            "name": name,
            "record_id": record_id,
            "status": "repair_cooldown_active",
            "repair": {
                "kind": "launch_session",
                "skipped": True,
                "reason": "launch prompt cooldown active",
                "lane_state": cooldown_state.to_dict(),
            },
        }
    cwd = _blocked_merge_worker_cwd(item, record=record)
    if cwd is None:
        return {
            "kind": "merge_worker_conflict_repair",
            "name": name,
            "record_id": record_id,
            "status": "repair_blocked",
            "reason": "merge worker cwd missing",
        }
    repair_prompt = _merge_dispatch_conflict_repair_prompt(item=item, cwd=cwd)
    work_order_prompt = build_launch_work_order_prompt(
        target_name=repair_name,
        cwd=str(cwd),
        goal=repair_prompt,
        allow_remote_push=True,
    )
    launched = launch_managed_codex(
        codex_home=codex_home,
        cwd=cwd,
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
        name=launched.name,
        tmux_session=None,
        status="launch_session",
        prompt_kind="merge_conflict_repair",
    )
    return {
        "kind": "merge_worker_conflict_repair",
        "name": name,
        "record_id": record_id,
        "branch": _non_empty_text(item.get("branch")),
        "worker_commit": _non_empty_text(item.get("worker_commit")),
        "status": "repair_launched",
        "repair": {
            "kind": "launch_session",
            "target_name": repair_name,
            "worker_role": launched.worker_role,
            "text": work_order_prompt,
            "managed": {
                "name": launched.name,
                "record_id": launched.record_id,
                "pid": launched.pid,
                "backend": launched.backend,
                "worker_role": launched.worker_role,
            },
            "cwd": str(cwd),
        },
    }


def _managed_record_by_id(*, codex_home: Path, record_id: str) -> Any | None:
    for record in reversed(read_managed_records(default_registry_path(codex_home))):
        if record.record_id == record_id:
            return record
    return None


def _latest_managed_record_by_name(*, codex_home: Path, name: str) -> Any | None:
    for record in reversed(read_managed_records(default_registry_path(codex_home))):
        if record.name == name:
            return record
    return None


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


def _merge_worker_review_item_is_blocked(item: dict[str, Any]) -> bool:
    protocol = item.get("supervisor_protocol")
    if not isinstance(protocol, dict):
        return False
    status = protocol.get("status")
    return isinstance(status, str) and status.lower() == "blocked"


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
    return filter_replenishment_counted_goals(
        active_goals,
        running_target_names=running_target_names or set(),
    )


def _fanout_candidate_active_goals(
    active_goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return filter_fanout_candidate_goals(active_goals)


def _active_goal_is_deferred(goal: dict[str, Any]) -> bool:
    return active_goal_is_deferred(goal)


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
        dependency_limit=getattr(args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT),
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
                    dependency_limit=getattr(
                        args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT
                    ),
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
                    dependency_limit=getattr(
                        args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT
                    ),
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
    running_worker = _running_managed_process_by_name(
        codex_home=Path(args.codex_home),
        name=MERGE_DISPATCH_TARGET_NAME,
    )
    return build_merge_dispatch_payload(
        review_payload,
        cwd=_merge_dispatch_cwd(args),
        running_worker=running_worker,
        managed_worker_reference=_managed_worker_reference,
    )


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
    return build_active_goals_fanout_launch_plan(
        active_goals,
        limit=getattr(args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT),
        running_target_names=_running_managed_target_names(report),
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
    return build_replenished_goal_plan_fanout_launch_plan(
        goal_replenishment,
        limit=getattr(args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT),
        running_target_names=_running_managed_target_names(report),
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
    return build_paused_active_goals_fanout_plan(
        active_goals,
        limit=getattr(args, "max_fanout_launches", DEFAULT_FANOUT_LIMIT),
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
        if _is_active_managed_process_session(session):
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
    result = CapabilityRunner().run_capability(
        "supervisor.request_context",
        inputs={
            "codex_home": str(Path(args.codex_home)),
            "cwd": cwd,
            "query": query,
        },
    )
    return {
        "kind": "request_context",
        "command": command,
        "cwd": cwd,
        "query": query,
        "context": _context_from_capability_result(result),
    }


def _context_from_capability_result(result: dict[str, Any]) -> dict[str, Any]:
    context_result = result.get("context_result")
    if not isinstance(context_result, dict):
        raise ValueError("supervisor.request_context did not return context_result")
    context = dict(context_result)
    context.pop("item_count", None)
    return context


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
    result = {
        "kind": "delete_worktree",
        "target_name": target_name,
        "command": command_text,
        "deleted_worktree": str(worktree["worktree_root"]),
        "managed": _managed_record_ref(record),
        "integration": _delete_worktree_integration_summary(integration),
    }
    branch = _delete_worktree_branch_name(integration)
    if branch is not None:
        result["branch_cleanup"] = _delete_integrated_supervisor_branch(
            repo_root=worktree["repo_root"],
            branch=branch,
            base_ref=str(action.get("base_ref") or "main"),
            run=subprocess.run,
        )
    return result


def _delete_worktree_branch_name(integration: dict[str, Any]) -> str | None:
    branch = integration.get("branch")
    if isinstance(branch, str) and branch.strip():
        return branch.strip()
    return None


def _delete_integrated_supervisor_branch(
    *,
    repo_root: Path,
    branch: str,
    base_ref: str,
    run: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {"branch": branch}
    if not _is_deletable_supervisor_branch(branch):
        result.update({"skipped": True, "reason": "branch is outside supervisor namespace"})
        return result
    upstream = _branch_upstream(repo_root=repo_root, branch=branch, run=run)
    if upstream is not None:
        result["upstream"] = upstream
    if not _branch_is_merged_into_base(
        repo_root=repo_root,
        branch=branch,
        base_ref=base_ref,
        run=run,
    ):
        result.update({"skipped": True, "reason": "branch is not merged into base"})
        return result
    local_delete = run(
        ["git", "-C", str(repo_root), "branch", "-d", branch],
        check=False,
        text=True,
        capture_output=True,
    )
    if local_delete.returncode != 0:
        result.update(
            {
                "skipped": True,
                "reason": "git branch delete failed",
                "stderr": (local_delete.stderr or local_delete.stdout or "").strip(),
            }
        )
        return result
    result["deleted_local_branch"] = branch
    if upstream is not None and _is_deletable_supervisor_upstream(upstream):
        remote, remote_branch = upstream.split("/", 1)
        remote_delete = run(
            ["git", "-C", str(repo_root), "push", remote, "--delete", remote_branch],
            check=False,
            text=True,
            capture_output=True,
        )
        if remote_delete.returncode == 0:
            result["deleted_upstream_branch"] = upstream
        else:
            result["upstream_delete_skipped"] = True
            result["upstream_delete_reason"] = "git push --delete failed"
            result["upstream_delete_stderr"] = (
                remote_delete.stderr or remote_delete.stdout or ""
            ).strip()
    return result


def _is_deletable_supervisor_branch(branch: str) -> bool:
    return branch.startswith("supervisor/") and branch not in {"supervisor/main"}


def _is_deletable_supervisor_upstream(upstream: str) -> bool:
    return upstream.startswith("origin/supervisor/")


def _branch_upstream(*, repo_root: Path, branch: str, run: Any) -> str | None:
    completed = run(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            f"{branch}@{{upstream}}",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    upstream = (completed.stdout or "").strip()
    return upstream or None


def _branch_is_merged_into_base(
    *,
    repo_root: Path,
    branch: str,
    base_ref: str,
    run: Any,
) -> bool:
    completed = run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", branch, base_ref],
        check=False,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0


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
        integration = review_managed_record_integration(
            record,
            run=subprocess.run,
            run_test_gate=False,
            run_candidate_validation=False,
        )
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
