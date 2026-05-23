from __future__ import annotations

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


def test_supervisor_runner_uses_memory_worker_event_channel():
    worker_event_channel = importlib.import_module("isotope.memory.worker_event_channel")

    assert runner.publish_worker_event is worker_event_channel.publish_worker_event
    assert runner.list_worker_events is worker_event_channel.list_worker_events
    assert (
        runner.render_worker_event_channel_plain
        is worker_event_channel.render_worker_event_channel_plain
    )
