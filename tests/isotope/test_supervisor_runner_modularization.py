from __future__ import annotations

import argparse
import importlib
import inspect

from isotope.features.supervisor import runner


def test_supervisor_runner_uses_command_dispatch_module():
    main_module = importlib.import_module("isotope.features.supervisor.commands.main")
    parser_module = importlib.import_module("isotope.features.supervisor.commands.parser")

    assert runner._run_cli is main_module.run_cli
    assert runner._build_parser is parser_module.build_parser
    assert runner.main(["guide", "--json"]) == 0


def test_supervisor_runner_parser_implementation_lives_in_command_module():
    parser_module = importlib.import_module("isotope.features.supervisor.commands.parser")

    assert runner._build_parser_impl is parser_module._build_parser_impl
    assert inspect.getsourcefile(runner._build_parser_impl) == inspect.getsourcefile(
        parser_module._build_parser_impl
    )


def test_supervisor_runner_uses_planner_and_state_helper_modules():
    goal_scope = importlib.import_module("isotope.features.supervisor.planner.goal_scope")
    time_utils = importlib.import_module("isotope.core.time")

    assert runner._goal_text is goal_scope._goal_text
    assert runner._goal_workspace is goal_scope._goal_workspace
    assert runner._goal_target_name is goal_scope._goal_target_name
    assert runner._utc_now is time_utils._utc_now
    assert runner._parse_timestamp is time_utils._parse_timestamp


def test_supervisor_runner_delegates_lifecycle_command_handlers():
    dashboard_module = importlib.import_module("isotope.features.supervisor.commands.dashboard")
    goal_module = importlib.import_module("isotope.features.supervisor.commands.goal")
    cleanup_module = importlib.import_module("isotope.features.supervisor.commands.cleanup")
    merge_module = importlib.import_module("isotope.features.supervisor.commands.merge")
    promotion_module = importlib.import_module("isotope.features.supervisor.commands.promotion")

    assert runner._handle_dashboard_command is dashboard_module.handle_dashboard_command
    assert runner._handle_goal_command is goal_module.handle_goal_command
    assert runner._handle_cleanup_command is cleanup_module.handle_cleanup_command
    assert (
        runner._handle_integration_review_command
        is merge_module.handle_integration_review_command
    )
    assert runner._handle_merge_work_order_command is merge_module.handle_merge_work_order_command
    assert runner._auto_promote_done_merge_workers_to_main is (
        promotion_module.auto_promote_done_merge_workers_to_main
    )

    source = inspect.getsource(runner._run_cli_impl)
    for command in (
        "dashboard",
        "integration-review",
        "merge-work-order",
        "goal",
        "cleanup",
    ):
        assert f'args.command == "{command}"' not in source


def test_supervisor_runner_delegates_cleanup_worktree_helpers():
    cleanup_module = importlib.import_module(
        "isotope.features.supervisor.commands.cleanup_worktree"
    )

    assert (
        runner._execute_delete_worktree_action
        is cleanup_module.execute_delete_worktree_action
    )
    assert (
        runner._delete_worktree_candidate_payloads
        is cleanup_module.delete_worktree_candidate_payloads
    )
    assert runner._managed_record_ref is cleanup_module.managed_record_ref
    assert (
        runner._supervisor_worktree_root_for_cwd
        is cleanup_module.supervisor_worktree_root_for_cwd
    )
    assert (
        runner._integration_review_allows_worktree_delete
        is cleanup_module.integration_review_allows_worktree_delete
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_execute_delete_worktree_action",
        "_delete_worktree_candidate_payloads",
        "_latest_managed_record_event",
        "_managed_record_ref",
        "_supervisor_worktree_root_for_cwd",
        "_integration_review_allows_worktree_delete",
        "_delete_worktree_integration_summary",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_auto_action_helpers():
    auto_action_module = importlib.import_module(
        "isotope.features.supervisor.commands.auto_action"
    )

    assert runner._auto_execute_action is auto_action_module.auto_execute_action
    assert runner._execute_auto_action is auto_action_module.execute_auto_action
    assert (
        runner._executed_action_forces_print
        is auto_action_module.executed_action_forces_print
    )
    assert (
        runner._auto_execute_action_for_managed
        is auto_action_module.auto_execute_action_for_managed
    )
    assert (
        runner._managed_terminal_looks_busy
        is auto_action_module.managed_terminal_looks_busy
    )
    assert (
        runner._supervisor_next_marks_terminal_done
        is auto_action_module.supervisor_next_marks_terminal_done
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_execute_auto_action",
        "_executed_action_forces_print",
        "_auto_execute_action",
        "_auto_action_exhausts_continue_budget",
        "_auto_action_exhausts_run_budget",
        "_auto_action_in_prompt_cooldown",
        "_auto_execute_action_for_managed",
        "_supervisor_next_marks_terminal_done",
        "_managed_terminal_looks_busy",
        "_auto_status_source",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_advice_execution_helpers():
    execution_module = importlib.import_module(
        "isotope.features.supervisor.commands.advice_execution"
    )

    assert runner._execute_advice is execution_module.execute_advice
    assert runner._run_budget_state is execution_module.run_budget_state
    assert runner._suggestion_by_kind is execution_module.suggestion_by_kind

    source = inspect.getsource(runner)
    for function_name in (
        "_execute_advice",
        "_run_budget_state",
        "_suggestion_by_kind",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_llm_action_execution_helpers():
    llm_action_module = importlib.import_module(
        "isotope.features.supervisor.commands.llm_action"
    )

    assert runner._execute_llm_action is llm_action_module.execute_llm_action
    assert (
        runner._execute_failure_guarded_action
        is llm_action_module.execute_failure_guarded_action
    )
    assert (
        runner._context_request_budget_result
        is llm_action_module.context_request_budget_result
    )
    assert (
        runner._resume_action_outside_active_goals
        is llm_action_module.resume_action_outside_active_goals
    )
    assert runner._failure_question is llm_action_module.failure_question

    source = inspect.getsource(runner)
    for function_name in (
        "_execute_llm_action",
        "_execute_failure_guarded_action",
        "_failure_event_type_for_skipped_result",
        "_exception_summary",
        "_failure_question",
        "_resume_action_outside_active_goals",
        "_active_goal_resume_session_ids",
        "_context_request_count",
        "_context_request_budget_result",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_llm_side_effect_execution_helpers():
    execution_module = importlib.import_module(
        "isotope.features.supervisor.commands.llm_execution"
    )

    assert runner._execute_resume_action is execution_module.execute_resume_action
    assert runner._execute_launch_action is execution_module.execute_launch_action
    assert runner._execute_context_action is execution_module.execute_context_action
    assert runner._execute_ask_user_action is execution_module.execute_ask_user_action
    assert runner._prepare_launch_worktree is execution_module.prepare_launch_worktree
    assert runner._worker_codex_model is execution_module.worker_codex_model
    assert runner._worker_codex_config is execution_module.worker_codex_config
    assert (
        runner._running_managed_process_by_name
        is execution_module.running_managed_process_by_name
    )
    assert runner._cwd_is_existing_dir is execution_module.cwd_is_existing_dir

    source = inspect.getsource(runner)
    for function_name in (
        "_execute_resume_action",
        "_execute_launch_action",
        "_execute_context_action",
        "_execute_ask_user_action",
        "_prepare_launch_worktree",
        "_git_root_for_worktree",
        "_safe_worktree_name",
        "_relative_cwd_in_repo",
        "_running_managed_process_by_name",
        "_running_managed_process_for_session",
        "_path_identity",
        "_cwd_is_existing_dir",
        "_worker_profile_from_args",
        "_worker_profile_for_action",
        "_worker_codex_model",
        "_worker_codex_config",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_fanout_orchestration_helpers():
    fanout_module = importlib.import_module("isotope.features.supervisor.commands.fanout")

    assert runner._fanout_candidate_active_goals is fanout_module.fanout_candidate_active_goals
    assert runner._active_goals_fanout_launch_plan is fanout_module.active_goals_fanout_launch_plan
    assert runner._goal_replenishment_wrote_goals is fanout_module.goal_replenishment_wrote_goals
    assert (
        runner._replenished_goal_plan_fanout_launch_plan
        is fanout_module.replenished_goal_plan_fanout_launch_plan
    )
    assert runner._fanout_status_payload is fanout_module.fanout_status_payload
    assert runner._paused_active_goals_fanout_plan is fanout_module.paused_active_goals_fanout_plan
    assert runner._fanout_llm_action is fanout_module.fanout_llm_action
    assert runner._fanout_paused_action is fanout_module.fanout_paused_action
    assert runner._fanout_paused_executed is fanout_module.fanout_paused_executed
    assert runner._fanout_log_payload is fanout_module.fanout_log_payload
    assert runner._execute_fanout_launch_actions is fanout_module.execute_fanout_launch_actions
    assert (
        runner._fanout_execution_launched_workers
        is fanout_module.fanout_execution_launched_workers
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_fanout_candidate_active_goals",
        "_active_goals_fanout_launch_plan",
        "_goal_replenishment_wrote_goals",
        "_replenished_goal_plan_fanout_launch_plan",
        "_fanout_status_payload",
        "_paused_active_goals_fanout_plan",
        "_fanout_llm_action",
        "_fanout_paused_action",
        "_fanout_paused_executed",
        "_fanout_log_payload",
        "_fanout_trigger",
        "_execute_fanout_launch_actions",
        "_fanout_execution_launched_workers",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_merge_dispatch_orchestration_helpers():
    merge_dispatch_module = importlib.import_module(
        "isotope.features.supervisor.commands.merge_dispatch"
    )

    assert (
        runner._integration_merge_dispatch_payload
        is merge_dispatch_module.integration_merge_dispatch_payload
    )
    assert runner._managed_worker_reference is merge_dispatch_module.managed_worker_reference
    assert runner._merge_dispatch_cwd is merge_dispatch_module.merge_dispatch_cwd
    assert (
        runner._recursive_worker_role_guard_payload
        is merge_dispatch_module.recursive_worker_role_guard_payload
    )
    assert (
        runner._recursive_worker_role_guard_action
        is merge_dispatch_module.recursive_worker_role_guard_action
    )
    assert (
        runner._recursive_worker_role_guard_executed
        is merge_dispatch_module.recursive_worker_role_guard_executed
    )
    assert (
        runner._current_workspace_has_worker_role
        is merge_dispatch_module.current_workspace_has_worker_role
    )
    assert (
        runner._current_workspace_worker_role
        is merge_dispatch_module.current_workspace_worker_role
    )
    assert (
        runner._is_merge_dispatch_launch_action
        is merge_dispatch_module.is_merge_dispatch_launch_action
    )
    assert (
        runner._mark_merge_dispatch_execution
        is merge_dispatch_module.mark_merge_dispatch_execution
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_integration_merge_dispatch_payload",
        "_managed_worker_reference",
        "_merge_dispatch_cwd",
        "_recursive_worker_role_guard_payload",
        "_recursive_worker_role_guard_action",
        "_recursive_worker_role_guard_executed",
        "_current_workspace_has_worker_role",
        "_current_workspace_worker_role",
        "_is_merge_dispatch_launch_action",
        "_mark_merge_dispatch_execution",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_merge_promotion_orchestration_helpers():
    promotion_module = importlib.import_module(
        "isotope.features.supervisor.commands.promotion"
    )

    assert (
        runner._auto_repair_blocked_merge_worker_review_item
        is promotion_module.auto_repair_blocked_merge_worker_review_item
    )
    assert (
        runner._auto_promote_merge_worker_review_item
        is promotion_module.auto_promote_merge_worker_review_item
    )
    assert runner._managed_record_by_id is promotion_module.managed_record_by_id
    assert (
        runner._latest_managed_record_by_name
        is promotion_module.latest_managed_record_by_name
    )
    assert runner._blocked_merge_promotion is promotion_module.blocked_merge_promotion
    assert (
        runner._merge_promotion_decision_request
        is promotion_module.merge_promotion_decision_request
    )
    assert (
        runner._launch_merge_promotion_repair_worker
        is promotion_module.launch_merge_promotion_repair_worker
    )
    assert (
        runner._completed_merge_promotion_repair_worker
        is promotion_module.completed_merge_promotion_repair_worker
    )
    assert (
        runner._archive_completed_merge_promotion_repair_worker
        is promotion_module.archive_completed_merge_promotion_repair_worker
    )
    assert (
        runner._merge_promotion_recent_decision_answer
        is promotion_module.merge_promotion_recent_decision_answer
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_auto_repair_blocked_merge_worker_review_item",
        "_auto_promote_merge_worker_review_item",
        "_managed_record_by_id",
        "_latest_managed_record_by_name",
        "_blocked_merge_promotion",
        "_merge_promotion_decision_request",
        "_launch_merge_promotion_repair_worker",
        "_completed_merge_promotion_repair_worker",
        "_archive_completed_merge_promotion_repair_worker",
        "_merge_promotion_recent_decision_answer",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_worker_failure_lifecycle_helpers():
    failure_module = importlib.import_module(
        "isotope.features.supervisor.commands.failure_lifecycle"
    )

    assert runner._sync_managed_worker_failures is failure_module.sync_managed_worker_failures
    assert (
        runner._managed_worker_failure_from_record
        is failure_module.managed_worker_failure_from_record
    )
    assert (
        runner._auto_retry_exited_process_workers
        is failure_module.auto_retry_exited_process_workers
    )
    assert runner._process_worker_retry_failure is failure_module.process_worker_retry_failure
    assert (
        runner._ensure_worker_retry_decision_request
        is failure_module.ensure_worker_retry_decision_request
    )
    assert (
        runner._active_worker_retry_decision_exists
        is failure_module.active_worker_retry_decision_exists
    )
    assert runner._worker_retry_error_summary is failure_module.worker_retry_error_summary
    assert runner._process_worker_needs_retry is failure_module.process_worker_needs_retry
    assert (
        runner._managed_record_exceeded_run_budget
        is failure_module.managed_record_exceeded_run_budget
    )
    assert runner._nonzero_exit_failure is failure_module.nonzero_exit_failure
    assert runner._usage_limit_failure is failure_module.usage_limit_failure
    assert runner._stderr_summary_from_excerpt is failure_module.stderr_summary_from_excerpt
    assert runner._lane_failure_payload is failure_module.lane_failure_payload

    source = inspect.getsource(runner)
    for function_name in (
        "_sync_managed_worker_failures",
        "_managed_worker_failure_from_record",
        "_auto_retry_exited_process_workers",
        "_process_worker_retry_failure",
        "_ensure_worker_retry_decision_request",
        "_active_worker_retry_decision_exists",
        "_worker_retry_error_summary",
        "_process_worker_needs_retry",
        "_managed_record_exceeded_run_budget",
        "_nonzero_exit_failure",
        "_usage_limit_failure",
        "_stderr_summary_from_excerpt",
        "_lane_failure_payload",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_auto_cleanup_lifecycle_helpers():
    cleanup_module = importlib.import_module(
        "isotope.features.supervisor.commands.auto_cleanup"
    )

    assert (
        runner._auto_delete_archived_worktrees_after_cleanup
        is cleanup_module.auto_delete_archived_worktrees_after_cleanup
    )
    assert (
        runner._auto_archive_integrated_merge_workers
        is cleanup_module.auto_archive_integrated_merge_workers
    )
    assert (
        runner._archive_integrated_source_worker
        is cleanup_module.archive_integrated_source_worker
    )
    assert (
        runner._archive_integrated_merge_worker
        is cleanup_module.archive_integrated_merge_worker
    )
    assert runner._archive_related_merge_goal is cleanup_module.archive_related_merge_goal
    assert (
        runner._merge_worker_review_item_is_done
        is cleanup_module.merge_worker_review_item_is_done
    )
    assert (
        runner._merge_worker_review_item_is_blocked
        is cleanup_module.merge_worker_review_item_is_blocked
    )
    assert runner._merge_candidate_record_ids is cleanup_module.merge_candidate_record_ids
    assert runner._review_group_record_ids is cleanup_module.review_group_record_ids
    assert runner._review_group_items is cleanup_module.review_group_items
    assert (
        runner._integration_reviews_by_record_ref
        is cleanup_module.integration_reviews_by_record_ref
    )
    assert (
        runner._integration_review_for_cleanup_candidate
        is cleanup_module.integration_review_for_cleanup_candidate
    )
    assert (
        runner._auto_cleanup_integration_summary
        is cleanup_module.auto_cleanup_integration_summary
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_auto_delete_archived_worktrees_after_cleanup",
        "_auto_archive_integrated_merge_workers",
        "_archive_integrated_source_worker",
        "_archive_integrated_merge_worker",
        "_archive_related_merge_goal",
        "_merge_worker_review_item_is_done",
        "_merge_worker_review_item_is_blocked",
        "_merge_candidate_record_ids",
        "_review_group_record_ids",
        "_review_group_items",
        "_integration_reviews_by_record_ref",
        "_integration_review_for_cleanup_candidate",
        "_auto_cleanup_integration_summary",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_daemon_command_helpers():
    daemon_module = importlib.import_module(
        "isotope.features.supervisor.commands.daemon_command"
    )

    assert runner._daemon_payload is daemon_module.daemon_payload
    assert runner._up_payload is daemon_module.up_payload
    assert runner._watcher_payload is daemon_module.watcher_payload
    assert runner._overnight_check_payload is daemon_module.overnight_check_payload
    assert runner._run_daemon_watcher is daemon_module.run_daemon_watcher
    assert runner._print_daemon_plain is daemon_module.print_daemon_plain
    assert runner._print_watcher_plain is daemon_module.print_watcher_plain
    assert runner._print_overnight_check_plain is daemon_module.print_overnight_check_plain

    source = inspect.getsource(runner)
    for function_name in (
        "_daemon_payload",
        "_up_payload",
        "_watcher_payload",
        "_overnight_check_payload",
        "_print_daemon_plain",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_onboarding_command_helpers():
    onboarding_module = importlib.import_module(
        "isotope.features.supervisor.commands.onboarding"
    )

    assert runner._start_here_payload is onboarding_module.start_here_payload
    assert runner._print_start_here_plain is onboarding_module.print_start_here_plain
    assert runner._guide_payload is onboarding_module.guide_payload
    assert runner._guide_worker_codex_args is onboarding_module.guide_worker_codex_args
    assert runner._print_guide_plain is onboarding_module.print_guide_plain
    assert runner._discover_payload is onboarding_module.discover_payload
    assert runner._selected_discover_candidate is onboarding_module.selected_discover_candidate
    assert runner._print_discover_plain is onboarding_module.print_discover_plain

    source = inspect.getsource(runner)
    for function_name in (
        "_start_here_payload",
        "_guide_payload",
        "_discover_payload",
        "_print_start_here_plain",
        "_print_guide_plain",
        "_print_discover_plain",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_advice_command_helpers():
    advice_module = importlib.import_module("isotope.features.supervisor.commands.advice")

    assert runner._automation_status is advice_module.automation_status
    assert runner._advice_payload is advice_module.advice_payload
    assert runner._command_suggestions is advice_module.command_suggestions
    assert (
        runner._workspace_action_command_suggestions
        is advice_module.workspace_action_command_suggestions
    )
    assert runner._goal_action_command_suggestions is advice_module.goal_action_command_suggestions
    assert (
        runner._active_goal_action_command_suggestions
        is advice_module.active_goal_action_command_suggestions
    )
    assert runner._managed_tmux_command_suggestions is advice_module.managed_tmux_command_suggestions
    assert (
        runner._resume_session_command_suggestions
        is advice_module.resume_session_command_suggestions
    )
    assert runner._watch_command_suggestion is advice_module.watch_command_suggestion

    source = inspect.getsource(runner)
    for function_name in (
        "_automation_status",
        "_advice_payload",
        "_command_suggestions",
        "_workspace_action_command_suggestions",
        "_goal_action_command_suggestions",
        "_active_goal_action_command_suggestions",
        "_managed_tmux_command_suggestions",
        "_resume_session_command_suggestions",
        "_watch_command_suggestion",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_dashboard_command_helpers():
    dashboard_module = importlib.import_module(
        "isotope.features.supervisor.commands.dashboard"
    )

    assert runner._dashboard_payload is dashboard_module.dashboard_payload
    assert runner._current_batch_payload is dashboard_module.current_batch_payload
    assert (
        runner._current_batch_payload_from_display_sessions
        is dashboard_module.current_batch_payload_from_display_sessions
    )
    assert runner._dashboard_item is dashboard_module.dashboard_item
    assert runner._dashboard_display_sessions is dashboard_module.dashboard_display_sessions
    assert runner._print_dashboard_plain is dashboard_module.print_dashboard_plain

    source = inspect.getsource(runner)
    for function_name in (
        "_dashboard_payload",
        "_current_batch_payload",
        "_current_batch_payload_from_display_sessions",
        "_dashboard_item",
        "_dashboard_display_sessions",
        "_print_dashboard_plain",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_lifecycle_trace_helpers():
    trace_module = importlib.import_module("isotope.features.supervisor.commands.trace")

    assert runner._lifecycle_trace_payload is trace_module.lifecycle_trace_payload
    assert runner._lightweight_lifecycle_stages is trace_module.lightweight_lifecycle_stages
    assert runner._managed_record_trace_dict is trace_module.managed_record_trace_dict
    assert runner._lifecycle_next_attention is trace_module.lifecycle_next_attention
    assert runner._print_lifecycle_trace_plain is trace_module.print_lifecycle_trace_plain

    source = inspect.getsource(runner)
    for function_name in (
        "_lifecycle_trace_payload",
        "_lightweight_lifecycle_stages",
        "_managed_record_trace_dict",
        "_lifecycle_next_attention",
        "_print_lifecycle_trace_plain",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_readonly_command_handlers():
    decision_module = importlib.import_module(
        "isotope.features.supervisor.commands.decision"
    )
    context_module = importlib.import_module("isotope.features.supervisor.commands.context")
    replan_module = importlib.import_module("isotope.features.supervisor.commands.replan")
    memory_module = importlib.import_module("isotope.features.supervisor.commands.memory")
    state_module = importlib.import_module("isotope.features.supervisor.commands.state")

    assert runner._handle_decision_command is decision_module.handle_decision_command
    assert runner._decision_payload is decision_module.decision_payload
    assert runner._print_decision_plain is decision_module.print_decision_plain
    assert runner._handle_context_command is context_module.handle_context_command
    assert runner._handle_replan_command is replan_module.handle_replan_command
    assert runner._replan_payload is replan_module.replan_payload
    assert runner._handle_state_command is state_module.handle_state_command
    assert runner._handle_memory_command is memory_module.handle_memory_command
    assert runner._handle_worker_event_command is memory_module.handle_worker_event_command
    assert runner._handle_worker_manager_command is memory_module.handle_worker_manager_command

    source = inspect.getsource(runner._run_cli_impl)
    for command in (
        "decision",
        "context",
        "replan",
        "state",
        "memory",
        "worker-event",
        "worker-manager",
    ):
        assert f'args.command == "{command}"' not in source

    runner_source = inspect.getsource(runner)
    for function_name in (
        "_decision_payload",
        "_print_decision_plain",
        "_replan_payload",
    ):
        assert f"def {function_name}(" not in runner_source


def test_supervisor_runner_uses_memory_worker_event_channel():
    worker_event_channel = importlib.import_module("isotope.memory.worker_event_channel")

    assert runner.publish_worker_event is worker_event_channel.publish_worker_event
    assert runner.list_worker_events is worker_event_channel.list_worker_events
    assert (
        runner.render_worker_event_channel_plain
        is worker_event_channel.render_worker_event_channel_plain
    )


def test_supervisor_runner_delegates_tmux_auto_adoption_helpers():
    onboarding_module = importlib.import_module(
        "isotope.features.supervisor.commands.onboarding"
    )

    assert (
        runner._auto_adopt_discovered_tmux_sessions
        is onboarding_module.auto_adopt_discovered_tmux_sessions
    )
    assert (
        runner._known_managed_tmux_sessions
        is onboarding_module.known_managed_tmux_sessions
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_auto_adopt_discovered_tmux_sessions",
        "_known_managed_tmux_sessions",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_loop_state_helpers():
    loop_state_module = importlib.import_module(
        "isotope.features.supervisor.commands.loop_state"
    )

    assert runner.IDLE_LOOP_REASON == loop_state_module.IDLE_LOOP_REASON
    assert runner._target_session is loop_state_module.target_session
    assert (
        runner._loop_without_autonomous_scope
        is loop_state_module.loop_without_autonomous_scope
    )
    assert (
        runner._loop_allows_workspace_actions
        is loop_state_module.loop_allows_workspace_actions
    )
    assert runner._has_loop_managed_scope is loop_state_module.has_loop_managed_scope
    assert runner._idle_loop_llm_action is loop_state_module.idle_loop_llm_action
    assert runner._has_llm_action_target is loop_state_module.has_llm_action_target
    assert (
        runner._session_marks_terminal_done
        is loop_state_module.session_marks_terminal_done
    )
    assert (
        runner._context_cwd_for_actionable_report
        is loop_state_module.context_cwd_for_actionable_report
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_target_session",
        "_loop_without_autonomous_scope",
        "_loop_allows_workspace_actions",
        "_has_loop_managed_scope",
        "_idle_loop_llm_action",
        "_has_llm_action_target",
        "_session_marks_terminal_done",
        "_context_cwd_for_actionable_report",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_capacity_loop_helpers():
    capacity_module = importlib.import_module(
        "isotope.features.supervisor.commands.capacity"
    )

    assert (
        runner._loop_capacity_decision_payload
        is capacity_module.loop_capacity_decision_payload
    )
    assert runner._capacity_call_specs is capacity_module.capacity_call_specs
    assert runner._capacity_decision_goal is capacity_module.capacity_decision_goal

    source = inspect.getsource(runner)
    for function_name in (
        "_loop_capacity_decision_payload",
        "_capacity_call_specs",
        "_capacity_decision_goal",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_workspace_scope_helpers():
    workspace_scope_module = importlib.import_module(
        "isotope.features.supervisor.commands.workspace_scope"
    )

    assert (
        runner._action_report_for_workspace
        is workspace_scope_module.action_report_for_workspace
    )
    assert (
        runner._workspace_scope_payload
        is workspace_scope_module.workspace_scope_payload
    )
    assert runner._workspace_root is workspace_scope_module.workspace_root
    assert runner._session_in_workspace is workspace_scope_module.session_in_workspace
    assert (
        runner._context_cwd_for_report
        is workspace_scope_module.context_cwd_for_report
    )

    source = inspect.getsource(runner)
    for function_name in (
        "_action_report_for_workspace",
        "_workspace_scope_payload",
        "_workspace_root",
        "_session_in_workspace",
        "_context_cwd_for_report",
    ):
        assert f"def {function_name}(" not in source


def test_supervisor_runner_delegates_supervise_payload_base_builder():
    payload_module = importlib.import_module(
        "isotope.features.supervisor.commands.supervise_payload"
    )

    assert (
        runner._build_supervise_base_payload
        is payload_module.build_supervise_base_payload
    )
    assert (
        runner._refresh_current_batch_after_execution
        is payload_module.refresh_current_batch_after_execution
    )

    source = inspect.getsource(runner)
    assert "def _build_supervise_base_payload(" not in source
    assert "def _refresh_current_batch_after_execution(" not in source


def test_supervisor_runner_delegates_supervise_planning_payload_builder():
    planning_module = importlib.import_module(
        "isotope.features.supervisor.commands.supervise_planning"
    )

    assert (
        runner._append_supervise_planning_payload
        is planning_module.append_supervise_planning_payload
    )

    source = inspect.getsource(runner)
    assert "def _append_supervise_planning_payload(" not in source


def test_supervise_payload_refreshes_current_batch_only_when_execution_requires_print():
    payload_module = importlib.import_module(
        "isotope.features.supervisor.commands.supervise_payload"
    )
    calls: list[tuple[str, object]] = []

    class FakeApi:
        def _executed_action_forces_print(self, executed):
            calls.append(("force", executed))
            return executed.get("force_print") is True

        def _scan_report(self, args):
            calls.append(("scan", args))
            return "refreshed-report"

        def _current_batch_payload(
            self,
            report,
            *,
            active_goals,
            worker_reviews,
            dependency_limit,
        ):
            calls.append(
                (
                    "current_batch",
                    {
                        "report": report,
                        "active_goals": active_goals,
                        "worker_reviews": worker_reviews,
                        "dependency_limit": dependency_limit,
                    },
                )
            )
            return {"target_names": ["new-worker"]}

    args = argparse.Namespace(max_fanout_launches=3)
    payload = {"current_batch": {"target_names": ["old-worker"]}}
    active_goals = [{"goal_id": "goal-1"}]
    worker_reviews = {"workers": []}
    api = FakeApi()

    assert (
        payload_module.refresh_current_batch_after_execution(
            args,
            payload,
            executed={"kind": "monitor"},
            active_goals=active_goals,
            worker_reviews=worker_reviews,
            api=api,
        )
        is False
    )
    assert payload["current_batch"] == {"target_names": ["old-worker"]}
    assert calls == [("force", {"kind": "monitor"})]

    assert (
        payload_module.refresh_current_batch_after_execution(
            args,
            payload,
            executed={"kind": "launch_session", "force_print": True},
            active_goals=active_goals,
            worker_reviews=worker_reviews,
            api=api,
        )
        is True
    )
    assert payload["current_batch"] == {"target_names": ["new-worker"]}
    assert calls[-3:] == [
        ("force", {"kind": "launch_session", "force_print": True}),
        ("scan", args),
        (
            "current_batch",
            {
                "report": "refreshed-report",
                "active_goals": active_goals,
                "worker_reviews": worker_reviews,
                "dependency_limit": 3,
            },
        ),
    ]


def test_supervisor_runner_delegates_supervise_action_selection():
    action_module = importlib.import_module(
        "isotope.features.supervisor.commands.supervise_action"
    )

    assert (
        runner._append_supervise_llm_action
        is action_module.append_supervise_llm_action
    )

    source = inspect.getsource(runner)
    assert "def _append_supervise_llm_action(" not in source
