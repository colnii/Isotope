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


def test_supervisor_runner_uses_planner_and_state_helper_modules():
    goal_scope = importlib.import_module("isotope.features.supervisor.planner.goal_scope")
    time_utils = importlib.import_module("isotope.features.supervisor.state.time_utils")

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
