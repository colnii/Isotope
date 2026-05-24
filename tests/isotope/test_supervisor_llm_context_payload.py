from __future__ import annotations

import argparse

from isotope.features.supervisor.commands import llm_context


class FakeLlmContextApi:
    def __init__(self) -> None:
        self.context_report = None
        self.capacity_kwargs = None

    def _recent_context_results(self, args, report):
        self.context_report = report
        return [{"query": "capacity", "summary": "recent context"}]

    def _decision_answer_dicts(self, args):
        return [{"request_id": "decision-1", "answer": "继续"}]

    def _loop_capacity_decision_payload(self, args, *, active_goals, explicit_goal):
        self.capacity_kwargs = {
            "active_goals": active_goals,
            "explicit_goal": explicit_goal,
        }
        return {
            "status": "ok",
            "reason": "ready",
            "goal": explicit_goal,
            "capacity_decisions": [
                {
                    "kind": "supervisor_capacity_decision",
                    "next_action": "call_capacity",
                    "capacity_id": "supervisor.request_context",
                    "can_execute_agent_loop": True,
                }
            ],
            "capacity_call_specs": [
                {
                    "capacity_id": "supervisor.request_context",
                    "goal": explicit_goal,
                    "inputs": {"query": "capacity"},
                }
            ],
        }

    def _worker_review_context(self, args):
        return {"workers": [{"name": "worker-a"}]}

    def _delete_worktree_candidate_payloads(self, args):
        return [{"path": ".worktrees/old-worker"}]


def test_llm_context_payload_collects_planner_context_and_capacity_status():
    api = FakeLlmContextApi()
    args = argparse.Namespace(capacity_decisions=True)
    report = object()
    action_report = object()
    active_goals = [{"goal": "补齐上下文"}]

    payload = llm_context.planner_context_payload(
        args,
        report,
        action_report=action_report,
        active_goals=active_goals,
        explicit_goal="补齐上下文",
        api=api,
    )

    assert api.context_report is action_report
    assert api.capacity_kwargs == {
        "active_goals": active_goals,
        "explicit_goal": "补齐上下文",
    }
    assert payload == {
        "recent_context_results": [{"query": "capacity", "summary": "recent context"}],
        "recent_decision_answers": [{"request_id": "decision-1", "answer": "继续"}],
        "capacity_decisions": [
            {
                "kind": "supervisor_capacity_decision",
                "next_action": "call_capacity",
                "capacity_id": "supervisor.request_context",
                "can_execute_agent_loop": True,
            }
        ],
        "capacity_call_specs": [
            {
                "capacity_id": "supervisor.request_context",
                "goal": "补齐上下文",
                "inputs": {"query": "capacity"},
            }
        ],
        "capacity_decision_status": {
            "status": "ok",
            "reason": "ready",
            "goal": "补齐上下文",
        },
        "worker_reviews": {"workers": [{"name": "worker-a"}]},
        "delete_worktree_candidates": [{"path": ".worktrees/old-worker"}],
    }
