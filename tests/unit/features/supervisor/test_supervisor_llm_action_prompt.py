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
    )

    payload = json.loads(messages[1]["content"])
    contract = payload["worker_lifecycle_contract"]
    assert contract["kind"] == "worker_lifecycle_contract"
    assert contract["decision"] == lifecycle_decision
    assert contract["rules"] == [
        "Treat worker_lifecycle_decision as program-owned lifecycle state.",
        "Do not repeat actions already present in execution.",
        "Do not repeat timeline entries where executed is true.",
        "If next_step is launch_merge_worker, prefer the existing merge dispatch path.",
        "If next_step is archive_worker or cleanup_worktree, prefer monitor unless a matching guarded cleanup candidate is present.",
        "Use LLM actions only for gaps, human decisions, or explicitly allowed follow-up actions.",
    ]
