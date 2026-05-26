from __future__ import annotations

import isotope.features.supervisor.planner.goal_planner as supervisor_goal_planner
import isotope.features.supervisor.planner.goal_planner as planner_goal_planner


def test_goal_planner_root_module_reexports_planner_implementation():
    assert (
        supervisor_goal_planner.plan_supervisor_goals
        is planner_goal_planner.plan_supervisor_goals
    )
    assert (
        supervisor_goal_planner.build_goal_planning_messages
        is planner_goal_planner.build_goal_planning_messages
    )
    assert (
        supervisor_goal_planner.parse_goal_candidates
        is planner_goal_planner.parse_goal_candidates
    )
    assert (
        supervisor_goal_planner.parse_goal_planning_result
        is planner_goal_planner.parse_goal_planning_result
    )
