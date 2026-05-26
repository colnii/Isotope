from __future__ import annotations

import json
from types import SimpleNamespace

from isotope.features.supervisor.llm_action.prompt import build_llm_action_messages


class _FakeRecommendation:
    def to_dict(self) -> dict[str, str | None]:
        return {"action": "monitor", "target_session_id": None}


def test_llm_action_prompt_builder_exposes_guarded_prompt_contract():
    report = SimpleNamespace(
        generated_at="2026-05-24T00:00:00Z",
        recommendation=_FakeRecommendation(),
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
