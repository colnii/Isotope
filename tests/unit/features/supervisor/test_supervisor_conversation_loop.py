from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor.conversation_loop import (
    SupervisorConversationEvent,
    run_supervisor_conversation_events,
)
from isotope.llm.provider import LLMResponse


class RecordingConversationProvider:
    provider = "fake"
    model = "fake-conversation"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        content = self.responses.pop(0)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=content,
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={"raw_response": "must not leak"},
        )


def test_conversation_loop_accepts_plain_text_as_direct_answer(tmp_path) -> None:
    provider = RecordingConversationProvider(["你好，我在。"])

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="你好",
            provider=provider,
        )
    )

    assert events == [
        SupervisorConversationEvent(
            event="delta",
            payload={"text": "你好，我在。"},
            provider="fake",
            model="fake-conversation",
        )
    ]
    assert len(provider.calls) == 1
    messages = provider.calls[0]["messages"]
    assert messages[-1] == {"role": "user", "content": "你好"}
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "capacity_manifest" in rendered
    assert "raw_response" not in rendered
