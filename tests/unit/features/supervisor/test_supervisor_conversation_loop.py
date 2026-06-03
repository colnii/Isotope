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


def test_conversation_loop_calls_capability_then_returns_final_answer(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "artifact.review",
                    "arguments": {},
                    "rationale": "需要试跑 artifact review capability。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "能力已执行，低敏结果已经返回。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path,
            user_message="请 review artifact。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "artifact.review"
    assert events[0].payload["status"] == "running"
    assert events[1].payload["capacity_id"] == "artifact.review"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result_summary"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload == {"text": "能力已执行，低敏结果已经返回。"}
    assert len(provider.calls) == 2
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "raw_response" not in second_prompt
