from __future__ import annotations

from isotope.features.supervisor.llm_action_guards import (
    delete_worktree_candidate,
    goal_requests_user_decision,
    has_context_check_for_goal,
)


def test_llm_action_guards_detect_goal_user_decision_requests():
    assert goal_requests_user_decision(
        {
            "last_status": "blocked",
            "last_next": "等待用户确认是否继续合并",
        }
    )
    assert not goal_requests_user_decision(
        {
            "last_status": "blocked",
            "last_next": "等待 worker 下一轮输出",
        }
    )


def test_llm_action_guards_match_context_and_delete_worktree_candidates():
    goal = {"goal_id": "goal-1", "cwd": "/repo/current"}
    assert has_context_check_for_goal(
        [{"cwd": "/repo/current", "query": "goal"}],
        goal,
    )
    assert not has_context_check_for_goal(
        [{"cwd": "/repo/other", "query": "goal"}],
        goal,
    )

    candidate = delete_worktree_candidate(
        [
            {"name": "worker-a", "record_id": "record-a"},
            {"target_name": "worker-b", "record_id": "record-b"},
        ],
        target_name="worker-b",
        record_id="record-b",
    )

    assert candidate == {"target_name": "worker-b", "record_id": "record-b"}
