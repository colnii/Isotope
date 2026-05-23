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
from pathlib import Path
from typing import Any

from isotope.capabilities.runner import CapabilityRunner
from .context import read_recent_context_results, request_project_context
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
from .state.projection import build_supervisor_state_snapshot
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
from .commands.cleanup_worktree import (
    branch_is_merged_into_base as _branch_is_merged_into_base,
    branch_upstream as _branch_upstream,
    delete_integrated_supervisor_branch as _delete_integrated_supervisor_branch,
    delete_worktree_branch_name as _delete_worktree_branch_name,
    delete_worktree_candidate_payloads as _delete_worktree_candidate_payloads,
    delete_worktree_integration_summary as _delete_worktree_integration_summary,
    execute_delete_worktree_action as _execute_delete_worktree_action,
    integration_review_allows_worktree_delete as _integration_review_allows_worktree_delete,
    is_deletable_supervisor_branch as _is_deletable_supervisor_branch,
    is_deletable_supervisor_upstream as _is_deletable_supervisor_upstream,
    latest_managed_record_event as _latest_managed_record_event,
    managed_record_ref as _managed_record_ref,
    supervisor_worktree_root_for_cwd as _supervisor_worktree_root_for_cwd,
)
from .commands.auto_action import (
    auto_action_exhausts_continue_budget as _auto_action_exhausts_continue_budget,
    auto_action_exhausts_run_budget as _auto_action_exhausts_run_budget,
    auto_action_in_prompt_cooldown as _auto_action_in_prompt_cooldown,
    auto_execute_action as _auto_execute_action,
    auto_execute_action_for_managed as _auto_execute_action_for_managed,
    auto_status_source as _auto_status_source,
    execute_auto_action as _execute_auto_action,
    executed_action_forces_print as _executed_action_forces_print,
    managed_terminal_looks_busy as _managed_terminal_looks_busy,
    supervisor_next_marks_terminal_done as _supervisor_next_marks_terminal_done,
)
from .commands.llm_action import (
    active_goal_resume_session_ids as _active_goal_resume_session_ids,
    context_request_budget_result as _context_request_budget_result,
    context_request_count as _context_request_count,
    exception_summary as _exception_summary,
    execute_failure_guarded_action as _execute_failure_guarded_action,
    execute_llm_action as _execute_llm_action,
    failure_event_type_for_skipped_result as _failure_event_type_for_skipped_result,
    failure_question as _failure_question,
    resume_action_outside_active_goals as _resume_action_outside_active_goals,
)
from .commands.llm_execution import (
    context_from_capability_result as _context_from_capability_result,
    cwd_is_existing_dir as _cwd_is_existing_dir,
    execute_ask_user_action as _execute_ask_user_action,
    execute_context_action as _execute_context_action,
    execute_launch_action as _execute_launch_action,
    execute_resume_action as _execute_resume_action,
    git_root_for_worktree as _git_root_for_worktree,
    path_identity as _path_identity,
    prepare_launch_worktree as _prepare_launch_worktree,
    relative_cwd_in_repo as _relative_cwd_in_repo,
    running_managed_process_by_name as _running_managed_process_by_name,
    running_managed_process_for_session as _running_managed_process_for_session,
    safe_worktree_name as _safe_worktree_name,
    worker_codex_config as _worker_codex_config,
    worker_codex_model as _worker_codex_model,
    worker_profile_defaults as _worker_profile_defaults,
    worker_profile_for_action as _worker_profile_for_action,
    worker_profile_from_args as _worker_profile_from_args,
    worker_role_for_launch_action as _worker_role_for_launch_action,
)
from .commands.fanout import (
    active_goals_fanout_launch_plan as _active_goals_fanout_launch_plan,
    execute_fanout_launch_actions as _execute_fanout_launch_actions,
    fanout_candidate_active_goals as _fanout_candidate_active_goals,
    fanout_execution_launched_workers as _fanout_execution_launched_workers,
    fanout_llm_action as _fanout_llm_action,
    fanout_log_payload as _fanout_log_payload,
    fanout_paused_action as _fanout_paused_action,
    fanout_paused_executed as _fanout_paused_executed,
    fanout_status_payload as _fanout_status_payload,
    fanout_trigger as _fanout_trigger,
    goal_replenishment_wrote_goals as _goal_replenishment_wrote_goals,
    int_value as _int_value,
    paused_active_goals_fanout_plan as _paused_active_goals_fanout_plan,
    replenished_goal_plan_fanout_launch_plan as _replenished_goal_plan_fanout_launch_plan,
)
from .commands.merge_dispatch import (
    current_workspace_has_worker_role as _current_workspace_has_worker_role,
    current_workspace_worker_role as _current_workspace_worker_role,
    integration_merge_dispatch_payload as _integration_merge_dispatch_payload,
    is_merge_dispatch_launch_action as _is_merge_dispatch_launch_action,
    managed_worker_reference as _managed_worker_reference,
    mark_merge_dispatch_execution as _mark_merge_dispatch_execution,
    merge_dispatch_cwd as _merge_dispatch_cwd,
    recursive_worker_role_guard_action as _recursive_worker_role_guard_action,
    recursive_worker_role_guard_executed as _recursive_worker_role_guard_executed,
    recursive_worker_role_guard_payload as _recursive_worker_role_guard_payload,
)
from .commands.capacity import handle_capacity_command as _handle_capacity_command
from .commands.context import handle_context_command as _handle_context_command
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
from .commands.decision import (
    decision_payload as _decision_payload,
    handle_decision_command as _handle_decision_command,
    print_decision_plain as _print_decision_plain,
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
from .commands.memory import (
    handle_memory_command as _handle_memory_command,
    handle_worker_event_command as _handle_worker_event_command,
    handle_worker_manager_command as _handle_worker_manager_command,
    json_object_arg as _json_object_arg,
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
    MERGE_PROMOTION_DECISION_QUESTION as _MERGE_PROMOTION_DECISION_QUESTION,
    MERGE_REPAIR_WORKER_ROLE,
    archive_completed_merge_promotion_repair_worker as _archive_completed_merge_promotion_repair_worker,
    auto_promote_merge_worker_review_item as _auto_promote_merge_worker_review_item,
    auto_promote_done_merge_workers_to_main as _auto_promote_done_merge_workers_to_main,
    auto_repair_blocked_merge_worker_review_item as _auto_repair_blocked_merge_worker_review_item,
    blocked_merge_promotion as _blocked_merge_promotion,
    completed_merge_promotion_repair_worker as _completed_merge_promotion_repair_worker,
    latest_managed_record_by_name as _latest_managed_record_by_name,
    launch_merge_promotion_repair_worker as _launch_merge_promotion_repair_worker,
    managed_record_by_id as _managed_record_by_id,
    merge_promotion_decision_request as _merge_promotion_decision_request,
    merge_promotion_recent_decision_answer as _merge_promotion_recent_decision_answer,
)
from .commands.replan import (
    handle_replan_command as _handle_replan_command,
    replan_payload as _replan_payload,
)
from .commands.state import (
    handle_state_command as _handle_state_command,
    print_state_plain as _print_state_plain,
    state_payload as _state_payload,
)
from .commands.trace import (
    latest_managed_record_events as _latest_managed_record_events,
    lifecycle_next_attention as _lifecycle_next_attention,
    lifecycle_trace_payload as _lifecycle_trace_payload,
    lifecycle_worker_is_waiting as _lifecycle_worker_is_waiting,
    lightweight_cleanup_candidate as _lightweight_cleanup_candidate,
    lightweight_lifecycle_stages as _lightweight_lifecycle_stages,
    lightweight_lifecycle_worker as _lightweight_lifecycle_worker,
    managed_record_trace_dict as _managed_record_trace_dict,
    print_lifecycle_trace_plain as _print_lifecycle_trace_plain,
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
from isotope.platform.state.worker_event_channel import (
    list_worker_events,
    publish_worker_event,
    render_worker_event_channel_plain,
)

EXECUTABLE_ADVICE_KINDS = {"send_status", "send_continue"}
MERGE_DISPATCH_WORKER_ROLE = "merge_dispatch"
RECURSIVE_WORKER_ROLES = {MERGE_DISPATCH_WORKER_ROLE, MERGE_REPAIR_WORKER_ROLE, "cleanup"}
DEFAULT_MAX_CONTEXT_REQUESTS = 0
DEFAULT_MAX_FAILURE_RETRIES = 3
DEFAULT_MAX_RUN_MINUTES = 0
DEFAULT_MAX_WORKER_RETRY_COUNT = 2
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
    "context": _handle_context_command,
    "decision": _handle_decision_command,
    "memory": _handle_memory_command,
    "replan": _handle_replan_command,
    "state": _handle_state_command,
    "worker-event": _handle_worker_event_command,
    "worker-manager": _handle_worker_manager_command,
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
    state_snapshot = build_supervisor_state_snapshot(codex_home=Path(args.codex_home))
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
        state_snapshot = build_supervisor_state_snapshot(codex_home=Path(args.codex_home))
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
    payload["state_snapshot"] = state_snapshot
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
            capacity_decisions=payload.get("capacity_decisions"),
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
            capacity_decisions=payload.get("capacity_decisions"),
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
