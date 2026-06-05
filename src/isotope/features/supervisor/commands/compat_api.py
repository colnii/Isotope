"""Compatibility re-exports for supervisor runner legacy helper symbols."""

from __future__ import annotations

from .main import run_cli as _run_cli
from .parser import (
    _build_parser_impl,
    build_parser as _build_parser,
)
from .cleanup import (
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
from .cleanup.cleanup_worktree import (
    branch_is_merged_into_base as _branch_is_merged_into_base,
    branch_upstream as _branch_upstream,
    delete_integrated_supervisor_branch as _delete_integrated_supervisor_branch,
    delete_worktree_branch_name as _delete_worktree_branch_name,
    delete_worktree_blocker_payloads as _delete_worktree_blocker_payloads,
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
from .auto.auto_cleanup import (
    archive_integrated_merge_worker as _archive_integrated_merge_worker,
    archive_integrated_source_worker as _archive_integrated_source_worker,
    archive_related_merge_goal as _archive_related_merge_goal,
    auto_archive_integrated_merge_workers as _auto_archive_integrated_merge_workers,
    auto_cleanup_integration_summary as _auto_cleanup_integration_summary,
    auto_delete_archived_worktrees_after_cleanup as _auto_delete_archived_worktrees_after_cleanup,
    integration_review_for_cleanup_candidate as _integration_review_for_cleanup_candidate,
    integration_reviews_by_record_ref as _integration_reviews_by_record_ref,
    merge_candidate_record_ids as _merge_candidate_record_ids,
    merge_worker_review_item_is_blocked as _merge_worker_review_item_is_blocked,
    merge_worker_review_item_is_done as _merge_worker_review_item_is_done,
    review_group_items as _review_group_items,
    review_group_record_ids as _review_group_record_ids,
)
from .handlers.capacity import (
    build_supervisor_capacity_plan,
    capacity_call_specs as _capacity_call_specs,
    capacity_decision_goal as _capacity_decision_goal,
    execute_codex_operation_action as _execute_codex_operation_action,
    execute_capacity_action as _execute_capacity_action,
    loop_capacity_decision_payload as _loop_capacity_decision_payload,
    resolve_capacity_calling_provider_from_env,
)
from .auto.auto_action import (
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
from .advice.advice_execution import (
    execute_advice as _execute_advice,
    run_budget_state as _run_budget_state,
    suggestion_by_kind as _suggestion_by_kind,
)
from .llm.action import (
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
from .llm.context import (
    maybe_replan_after_context_request as _maybe_replan_after_context_request,
    planner_context_payload as _planner_context_payload,
)
from .llm.planner import (
    ContextRequiredSummaryProvider as _ContextRequiredSummaryProvider,
    decide_action_with_llm as _decide_action_with_llm,
)
from .failure_guard import (
    failure_decision_request_action as _failure_decision_request_action,
    failure_goal_id as _failure_goal_id,
    failure_lane_name as _failure_lane_name,
    failure_retry_exhausted as _failure_retry_exhausted,
    record_failure_event as _record_failure_event,
)
from .llm.execution import (
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
from .fanout import (
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
from .failure_lifecycle import (
    active_worker_retry_decision_exists as _active_worker_retry_decision_exists,
    auto_retry_exited_process_workers as _auto_retry_exited_process_workers,
    ensure_worker_retry_decision_request as _ensure_worker_retry_decision_request,
    lane_failure_payload as _lane_failure_payload,
    managed_record_exceeded_run_budget as _managed_record_exceeded_run_budget,
    managed_worker_failure_from_record as _managed_worker_failure_from_record,
    nonzero_exit_failure as _nonzero_exit_failure,
    process_worker_needs_retry as _process_worker_needs_retry,
    process_worker_retry_failure as _process_worker_retry_failure,
    stderr_summary_from_excerpt as _stderr_summary_from_excerpt,
    sync_managed_worker_failures as _sync_managed_worker_failures,
    usage_limit_failure as _usage_limit_failure,
    worker_retry_error_summary as _worker_retry_error_summary,
)
from .merge.dispatch import (
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
from .handlers.capacity import handle_capacity_command as _handle_capacity_command
from .handlers.context import handle_context_command as _handle_context_command
from .dashboard import (
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
from .handlers.decision import (
    decision_payload as _decision_payload,
    handle_decision_command as _handle_decision_command,
    print_decision_plain as _print_decision_plain,
)
from .handlers.goal import (
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
from .merge import (
    handle_integration_review_command as _handle_integration_review_command,
    handle_merge_work_order_command as _handle_merge_work_order_command,
)
from .handlers.memory import (
    handle_memory_command as _handle_memory_command,
    handle_worker_event_command as _handle_worker_event_command,
    handle_worker_manager_command as _handle_worker_manager_command,
    json_object_arg as _json_object_arg,
)
from .plain_rendering import (
    executed_activity_detail as _executed_activity_detail,
    llm_action_activity_kind as _llm_action_activity_kind,
    print_advice as _print_advice,
    print_ask_user_action_plain as _print_ask_user_action_plain,
    print_executed_plain as _print_executed_plain,
    print_supervise_plain as _print_supervise_plain,
)
from .onboarding import (
    auto_adopt_discovered_tmux_sessions as _auto_adopt_discovered_tmux_sessions,
    discover_payload as _discover_payload,
    guide_payload as _guide_payload,
    guide_worker_codex_args as _guide_worker_codex_args,
    known_managed_tmux_sessions as _known_managed_tmux_sessions,
    print_discover_plain as _print_discover_plain,
    print_guide_plain as _print_guide_plain,
    print_start_here_plain as _print_start_here_plain,
    selected_discover_candidate as _selected_discover_candidate,
    start_here_payload as _start_here_payload,
)
from .loop_state import (
    IDLE_LOOP_REASON,
    context_cwd_for_actionable_report as _context_cwd_for_actionable_report,
    has_llm_action_target as _has_llm_action_target,
    has_loop_managed_scope as _has_loop_managed_scope,
    idle_loop_llm_action as _idle_loop_llm_action,
    loop_allows_workspace_actions as _loop_allows_workspace_actions,
    loop_without_autonomous_scope as _loop_without_autonomous_scope,
    session_marks_terminal_done as _session_marks_terminal_done,
    target_session as _target_session,
)
from .workspace_scope import (
    action_report_for_workspace as _action_report_for_workspace,
    context_cwd_for_report as _context_cwd_for_report,
    session_in_workspace as _session_in_workspace,
    workspace_root as _workspace_root,
    workspace_scope_payload as _workspace_scope_payload,
)
from .supervise.payload import (
    append_supervise_final_payload as _append_supervise_final_payload,
    build_supervise_base_payload as _build_supervise_base_payload,
    refresh_current_batch_after_execution as _refresh_current_batch_after_execution,
)
from .supervise.planning import (
    append_supervise_planning_payload as _append_supervise_planning_payload,
)
from .supervise.action import (
    append_supervise_llm_action as _append_supervise_llm_action,
)
from .supervise.execution import (
    append_supervise_execution as _append_supervise_execution,
)
from .advice import (
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
from .daemon_command import (
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
    recent_llm_action_from_log as _recent_supervisor_action_from_log,
    recent_llm_action_from_log as _recent_llm_action_from_log,
    recent_worker_payload as _recent_worker_payload,
    run_daemon_watcher as _run_daemon_watcher,
    start_daemon_from_args as _start_daemon_from_args,
    status_detail_from_text as _status_detail_from_text,
    up_payload as _up_payload,
    watcher_payload as _watcher_payload,
)
from .merge.promotion import (
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
from .handlers.replan import (
    handle_replan_command as _handle_replan_command,
    replan_payload as _replan_payload,
)
from .handlers.state import (
    handle_state_command as _handle_state_command,
    print_state_plain as _print_state_plain,
    state_payload as _state_payload,
)
from .handlers.worktree_audit import (
    audit_worktree_records as _audit_worktree_records,
    handle_worktree_audit_command as _handle_worktree_audit_command,
    parse_worktree_list_porcelain as _parse_worktree_list_porcelain,
    print_worktree_audit_plain as _print_worktree_audit_plain,
    topic_tokens_for_text as _topic_tokens_for_text,
    worktree_audit_payload as _worktree_audit_payload,
)
from .scan import (
    emit_terminal_bell as _emit_terminal_bell,
    print_report as _print_report,
    scan_report as _scan_report,
    summarize_with_llm as _summarize_with_llm,
    unknown_tmux_bell_hook as _unknown_tmux_bell_hook,
)
from ..flow import _tmux_capture_pane
from .trace import (
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
from ..planner.goal_scope import (
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

__all__ = tuple(name for name in globals() if not name.startswith("__"))
