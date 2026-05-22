from isotope.agents.scheduler.fanout import (
    build_active_goals_fanout_launch_plan,
    build_fanout_launch_plan,
    build_fanout_status_summary,
    build_paused_active_goals_fanout_plan,
    build_replenished_goal_plan_fanout_launch_plan,
)
from isotope.agents.scheduler.goal_queue import (
    build_supervisor_goal_queue_view,
    filter_replenishment_counted_goals,
)


def test_agent_scheduler_plans_fanout_with_running_worker_and_limit_guards():
    goal_plan = {
        "root": "/repo/isotope",
        "goals": [
            {"goal": "实现 A。", "target_name": "worker-a"},
            {"goal": "实现 B。", "target_name": "worker-b"},
            {"goal": "实现 C。", "target_name": "worker-c"},
        ],
        "parallel_recommendations": [
            {
                "batch": "active_goals",
                "targets": ["worker-a", "worker-b", "worker-c"],
                "reason": "同阶段目标可并行。",
            }
        ],
    }

    plan = build_fanout_launch_plan(
        goal_plan,
        limit=1,
        running_target_names={"worker-b"},
        requires_human_review=False,
    )

    assert [item["target_name"] for item in plan["launch_specs"]] == ["worker-a"]
    assert plan["summary"] == {"launchable": 1, "skipped": 2, "limit": 1}
    assert plan["skipped"] == [
        {
            "target_name": "worker-b",
            "reason": "worker_already_running",
            "batch": "active_goals",
        },
        {
            "target_name": "worker-c",
            "reason": "fanout_limit_reached",
            "batch": "active_goals",
        },
    ]


def test_agent_scheduler_selects_active_goal_targets_for_fanout():
    active_goals = [
        {"goal": "实现 A。", "target_name": "worker-a", "cwd": "/repo"},
        {"goal": "实现 B。", "target_name": "worker-b", "cwd": "/repo"},
        {
            "goal": "等待拍板。",
            "target_name": "worker-c",
            "cwd": "/repo",
            "last_status": "needs_user",
        },
    ]

    plan = build_active_goals_fanout_launch_plan(
        active_goals,
        limit=2,
        running_target_names={"worker-b"},
    )

    assert plan is not None
    assert plan["summary"] == {"launchable": 1, "skipped": 1, "limit": 2}
    assert [item["target_name"] for item in plan["launch_specs"]] == ["worker-a"]
    assert plan["skipped"] == [
        {
            "target_name": "worker-b",
            "reason": "worker_already_running",
            "batch": "active_goals",
        }
    ]


def test_agent_scheduler_plans_replenished_goal_recommendations():
    replenishment = {
        "status": "ok",
        "written_goals": [
            {"goal": "实现 A。", "target_name": "worker-a", "cwd": "/repo"},
            {"goal": "实现 B。", "target_name": "worker-b", "cwd": "/repo"},
        ],
        "parallel_recommendations": [
            {
                "batch": "planner",
                "targets": ["worker-b"],
                "reason": "planner 只推荐 B。",
            }
        ],
    }

    plan = build_replenished_goal_plan_fanout_launch_plan(
        replenishment,
        limit=2,
        running_target_names=set(),
    )

    assert plan is not None
    assert [item["target_name"] for item in plan["launch_specs"]] == ["worker-b"]
    assert plan["launch_specs"][0]["batch"] == "planner"


def test_agent_scheduler_builds_paused_plan_without_blocked_targets():
    plan = build_paused_active_goals_fanout_plan(
        [
            {"target_name": "blocked-target", "last_status": "blocked"},
            {"target_name": "pending-target"},
        ],
        limit=3,
    )

    assert plan["status"] == "paused"
    assert plan["summary"] == {"launchable": 0, "skipped": 1, "limit": 3}
    assert plan["skipped"] == [
        {
            "target_name": "pending-target",
            "reason": "fanout_paused_for_attention",
            "batch": "active_goals",
        }
    ]


def test_agent_scheduler_goal_queue_view_and_replenishment_counting():
    active_goals = [
        {
            "goal_id": "goal-a",
            "target_name": "worker-a",
            "created_at": "2026-05-22T01:00:00+00:00",
        },
        {
            "goal_id": "goal-b",
            "target_name": "worker-b",
            "created_at": "2026-05-22T02:00:00+00:00",
        },
        {
            "goal_id": "goal-c",
            "target_name": "worker-c",
            "created_at": "2026-05-22T03:00:00+00:00",
            "last_status": "blocked",
        },
    ]

    view = build_supervisor_goal_queue_view(
        active_goals,
        running_target_names={"worker-b"},
    )
    counted = filter_replenishment_counted_goals(
        active_goals,
        running_target_names={"worker-b"},
    )

    assert [item["goal_id"] for item in view["pending"]] == ["goal-a"]
    assert [item["goal_id"] for item in view["running"]] == ["goal-b"]
    assert [item["goal_id"] for item in view["blocked"]] == ["goal-c"]
    assert [item["goal_id"] for item in counted] == ["goal-a"]


def test_agent_scheduler_status_summary_remains_scheduler_owned():
    summary = build_fanout_status_summary(
        active_goals=[
            {"goal_id": "goal-a", "target_name": "worker-a"},
            {"goal_id": "goal-b", "target_name": "worker-b"},
        ],
        running_target_names={"worker-b"},
    )

    assert summary["status"] == "running"
    assert summary["summary"] == {
        "total": 2,
        "done": 0,
        "blocked": 0,
        "needs_user": 0,
        "running": 1,
        "pending": 1,
    }
