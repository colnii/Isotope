from __future__ import annotations

import importlib

from isotope.features.supervisor import runner


def test_supervisor_runner_uses_command_dispatch_module():
    main_module = importlib.import_module("isotope.features.supervisor.commands.main")

    assert runner._run_cli is main_module.run_cli
    assert runner.main(["guide", "--json"]) == 0


def test_supervisor_runner_uses_planner_and_state_helper_modules():
    goal_scope = importlib.import_module("isotope.features.supervisor.planner.goal_scope")
    time_utils = importlib.import_module("isotope.features.supervisor.state.time_utils")

    assert runner._goal_text is goal_scope._goal_text
    assert runner._goal_workspace is goal_scope._goal_workspace
    assert runner._goal_target_name is goal_scope._goal_target_name
    assert runner._utc_now is time_utils._utc_now
    assert runner._parse_timestamp is time_utils._parse_timestamp
