from __future__ import annotations

from isotope.features.supervisor import CurrentBatchView
from isotope.features.supervisor.state.current_batch import build_current_batch_view


def test_current_batch_view_filters_done_stale_noise() -> None:
    active_goals = [
        {
            "goal_id": "goal-current",
            "target_name": "current-worker",
            "goal": "推进当前批次 worker。",
            "last_status": "working",
            "cwd": "/repo/current",
            "cwd_exists": True,
        },
        {
            "goal_id": "goal-done",
            "target_name": "done-worker",
            "goal": "历史已完成目标。",
            "last_status": "done",
            "cwd": "/repo/done",
            "cwd_exists": True,
        },
        {
            "goal_id": "goal-stale",
            "target_name": "stale-worker",
            "goal": "历史 stale 目标。",
            "last_status": "stale",
            "cwd": "/repo/stale",
            "cwd_exists": True,
        },
        {
            "goal_id": "goal-missing",
            "target_name": "missing-worker",
            "goal": "worktree 已缺失目标。",
            "last_status": "working",
            "cwd": "/repo/missing",
            "cwd_exists": False,
        },
    ]
    managed_workers = [
        {
            "record_id": "managed-current",
            "name": "current-worker",
            "cwd": "/repo/current",
            "status": "working",
            "supervisor_status": "working",
            "cwd_exists": True,
        },
        {
            "record_id": "managed-done",
            "name": "done-worker",
            "cwd": "/repo/done",
            "status": "working",
            "supervisor_status": "done",
            "cwd_exists": True,
        },
        {
            "record_id": "managed-stale",
            "name": "stale-worker",
            "cwd": "/repo/stale",
            "status": "stale",
            "cwd_exists": True,
        },
    ]
    worker_reviews = {
        "status": "ok",
        "workers": [
            {
                "record_id": "managed-current",
                "name": "current-worker",
                "cwd": "/repo/current",
                "supervisor_protocol": {"status": "working"},
            },
            {
                "record_id": "managed-done",
                "name": "done-worker",
                "cwd": "/repo/done",
                "supervisor_protocol": {"status": "done"},
            },
            {
                "record_id": "managed-unrelated",
                "name": "unrelated-worker",
                "cwd": "/repo/unrelated",
                "supervisor_protocol": {"status": "working"},
            },
        ],
        "automation_candidates": {
            "continue_or_split": [
                {
                    "record_id": "managed-current",
                    "name": "current-worker",
                    "cwd": "/repo/current",
                    "recommendation": "continue_or_split_task",
                }
            ],
            "archive_or_wait": [
                {
                    "record_id": "managed-done",
                    "name": "done-worker",
                    "cwd": "/repo/done",
                    "recommendation": "archive_or_wait",
                }
            ],
            "review_then_merge": [
                {
                    "record_id": "managed-unrelated",
                    "name": "unrelated-worker",
                    "cwd": "/repo/unrelated",
                    "recommendation": "review_then_merge_candidate",
                }
            ],
        },
    }

    view = build_current_batch_view(
        active_goals=active_goals,
        managed_workers=managed_workers,
        worker_reviews=worker_reviews,
    )

    assert isinstance(view, CurrentBatchView)
    assert view.to_dict() == {
        "active_goals": [active_goals[0]],
        "managed_workers": [managed_workers[0]],
        "worker_reviews": {
            "status": "ok",
            "summary": {"total": 1},
            "workers": [worker_reviews["workers"][0]],
            "automation_candidates": {
                "continue_or_split": [
                    worker_reviews["automation_candidates"]["continue_or_split"][0]
                ]
            },
        },
        "automation_candidates": {
            "continue_or_split": [
                worker_reviews["automation_candidates"]["continue_or_split"][0]
            ]
        },
        "counts": {
            "active_goals": 1,
            "managed_workers": 1,
            "worker_reviews": 1,
            "automation_candidates": 1,
            "total": 2,
        },
        "target_names": ["current-worker"],
        "dependency_batch": {
            "status": "idle",
            "summary": {
                "ready": 0,
                "blocked": 0,
                "running": 1,
                "attention": 0,
                "limit": 2,
            },
            "ready_goals": [],
            "blocked_goals": [],
            "running_goals": [{"target_name": "current-worker", "status": "running"}],
            "attention_goals": [],
        },
    }


def test_current_batch_view_keeps_live_items_without_runner_flags() -> None:
    active_goal = {
        "goal_id": "goal-live",
        "target_name": "live-worker",
        "goal": "尚未汇报状态的新目标。",
        "cwd": "/repo/live",
    }
    managed_worker = {
        "record_id": "managed-live",
        "name": "live-worker",
        "cwd": "/repo/live",
        "status": "launched",
    }

    view = build_current_batch_view(
        active_goals=[active_goal],
        managed_workers=[managed_worker],
        worker_reviews=None,
    )

    assert view.to_dict()["active_goals"] == [active_goal]
    assert view.to_dict()["managed_workers"] == [managed_worker]
    assert view.to_dict()["worker_reviews"] == {
        "summary": {"total": 0},
        "workers": [],
        "automation_candidates": {},
    }
    assert view.to_dict()["target_names"] == ["live-worker"]
    assert view.to_dict()["dependency_batch"]["status"] == "idle"


def test_current_batch_view_exposes_dependency_batch_projection() -> None:
    active_goals = [
        {
            "goal_id": "goal-a",
            "target_name": "worker-a",
            "goal": "完成基础模块。",
            "last_status": "done",
            "merged": True,
            "verified": True,
            "cwd": "/repo",
            "cwd_exists": True,
        },
        {
            "goal_id": "goal-b",
            "target_name": "worker-b",
            "goal": "接入基础模块。",
            "depends_on": ["worker-a"],
            "cwd": "/repo",
            "cwd_exists": True,
        },
        {
            "goal_id": "goal-c",
            "target_name": "worker-c",
            "goal": "等待 worker-b 后做端到端验证。",
            "depends_on": ["worker-b"],
            "cwd": "/repo",
            "cwd_exists": True,
        },
    ]
    managed_workers = [
        {
            "record_id": "managed-b",
            "name": "worker-b",
            "cwd": "/repo",
            "status": "working",
            "cwd_exists": True,
        }
    ]

    payload = build_current_batch_view(
        active_goals=active_goals,
        managed_workers=managed_workers,
        dependency_limit=2,
    ).to_dict()

    assert payload["dependency_batch"]["summary"] == {
        "ready": 0,
        "blocked": 1,
        "running": 1,
        "attention": 0,
        "limit": 2,
    }
    assert payload["dependency_batch"]["running_goals"] == [
        {"target_name": "worker-b", "status": "running"}
    ]
    assert payload["dependency_batch"]["blocked_goals"] == [
        {
            "target_name": "worker-c",
            "reason": "dependency_unmet",
            "dependency": "worker-b",
        }
    ]
