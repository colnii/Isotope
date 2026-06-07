from __future__ import annotations

import json
from types import SimpleNamespace

from isotope.features.supervisor.llm_action.prompt import build_llm_action_messages


class _StubRecommendation:
    def to_dict(self) -> dict[str, str | None]:
        return {"action": "monitor", "target_session_id": None}


def test_llm_action_prompt_builder_exposes_guarded_prompt_contract():
    report = SimpleNamespace(
        generated_at="2026-05-24T00:00:00Z",
        recommendation=_StubRecommendation(),
        sessions=[],
    )

    messages = build_llm_action_messages(
        report,
        [{"kind": "monitor", "label": "继续监控", "command": "true"}],
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    payload = json.loads(messages[1]["content"])
    assert "request_context" in payload["allowed_kinds"]
    assert payload["context_capability"]["kind"] == "request_context"
    assert payload["decision_gate"]["kind"] == "ask_user"
    assert payload["output_schema"]["kind"] == "resume_session"


def test_llm_action_prompt_builder_exposes_worker_lifecycle_contract():
    report = SimpleNamespace(
        generated_at="2026-05-24T00:00:00Z",
        recommendation=_StubRecommendation(),
        sessions=[],
    )
    lifecycle_decision = {
        "kind": "worker_lifecycle_decision",
        "action": "archive_integrated",
        "stage": "archived",
        "next_step": "cleanup_worktree",
        "source": "cleanup",
        "execution": [{"kind": "merge_worker", "record_id": "managed-merge"}],
        "policy": {
            "policy_status": "program_resolved",
            "program_action": "archive_integrated",
            "remaining_step": "cleanup_worktree",
            "blocked_reason": None,
        },
        "timeline": [
            {
                "stage": "archived",
                "action": "archive_integrated",
                "status": "executed",
                "executed": True,
            }
        ],
    }

    messages = build_llm_action_messages(
        report,
        [{"kind": "monitor", "label": "继续监控", "command": "true"}],
        worker_lifecycle_decision=lifecycle_decision,
        worker_lifecycle_execution={
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "next_step": "cleanup_worktree",
            "status": "blocked",
            "delete_worktree_blockers": [
                {
                    "target_name": "dirty-worker",
                    "reason": "worker worktree is dirty",
                }
            ],
        },
        worker_lifecycle_execution_result={
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "skipped": True,
            "reason": "worktree delete blockers require attention",
            "count": 0,
            "blockers": 1,
        },
    )

    payload = json.loads(messages[1]["content"])
    contract = payload["worker_lifecycle_contract"]
    assert contract["kind"] == "worker_lifecycle_contract"
    assert contract["decision"] == lifecycle_decision
    assert contract["execution"] == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "next_step": "cleanup_worktree",
        "status": "blocked",
        "summary": {
            "archivable": 0,
            "delete_ready": 0,
            "delete_blocked": 1,
            "result_actions": 0,
        },
        "recommended_next_step": "delete_blocked",
        "result": {
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "skipped": True,
            "reason": "worktree delete blockers require attention",
            "count": 0,
        },
    }
    assert contract["rules"] == [
        "Treat worker_lifecycle_decision as program-owned lifecycle state.",
        "Do not repeat actions already present in execution.",
        "Do not repeat timeline entries where executed is true.",
        "Use execution.summary before choosing archive, delete, or blocker follow-up.",
        "If policy_status is program_resolved, prefer monitor unless remaining_step names an allowed guarded action.",
        "If policy_status is human_required, use ask_user or request_context only when the decision gate allows it.",
        "If policy_status is model_required, choose from the normal allowed action whitelist.",
        "If next_step is launch_merge_worker, prefer the existing merge dispatch path.",
        "If next_step is archive_worker or cleanup_worktree, prefer monitor unless a matching guarded cleanup candidate is present.",
        "Use LLM actions only for gaps, human decisions, or explicitly allowed follow-up actions.",
    ]


def test_llm_action_prompt_builder_exposes_prepared_action_context():
    report = SimpleNamespace(
        generated_at="2026-05-24T00:00:00Z",
        recommendation=_StubRecommendation(),
        sessions=[],
    )
    prepared_context = {
        "kind": "supervisor_prepared_action_context",
        "source": "program",
        "candidates": [
            {
                "reason": "worker_lifecycle_execution",
                "action": {
                    "kind": "launch_session",
                    "target_name": "supervisor-merge-dispatch",
                },
            }
        ],
    }

    messages = build_llm_action_messages(
        report,
        [{"kind": "monitor", "label": "继续监控", "command": "true"}],
        prepared_action_context=prepared_context,
    )

    payload = json.loads(messages[1]["content"])
    assert payload["prepared_action_context"] == prepared_context


def test_llm_action_prompt_rules_prioritize_prepared_context_without_bloat():
    report = SimpleNamespace(
        generated_at="2026-05-24T00:00:00Z",
        recommendation=_StubRecommendation(),
        sessions=[],
    )
    prepared_context = {
        "kind": "supervisor_prepared_action_context",
        "source": "program",
        "facts": [
            {
                "kind": "decision_requests",
                "count": 1,
                "target_names": ["blocked-worker"],
            }
        ],
    }

    messages = build_llm_action_messages(
        report,
        [{"kind": "monitor", "label": "继续监控", "command": "true"}],
        prepared_action_context=prepared_context,
    )

    payload = json.loads(messages[1]["content"])
    assert payload["action_rules"][0].startswith("先读 prepared_action_context")
    assert len(payload["action_rules"]) <= 18
