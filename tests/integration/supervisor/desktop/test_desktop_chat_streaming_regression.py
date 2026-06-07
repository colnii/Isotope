from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor.desktop_chat import stream_desktop_chat_events
from isotope.llm.provider import LLMResponse, LLMStreamChunk


class DirectDecisionStreamingAnswerProvider:
    provider = "deterministic_test"
    model = "stub-streaming-answer"

    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.generate_calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "决策层允许直接回答，但这段不应该作为流式正文。",
                    "rationale": "不需要能力调用。",
                },
                ensure_ascii=False,
            ),
            finish_reason="stop",
            usage={},
            raw={},
        )

    def stream_generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ):
        self.stream_calls.append({"messages": messages, "max_tokens": max_tokens})
        for content in ("真实", "逐段", "返回。"):
            yield LLMStreamChunk(
                provider=self.provider,
                model=self.model,
                content=content,
                raw={},
            )


def test_desktop_chat_direct_answer_uses_provider_stream_after_model_decision(
    tmp_path,
) -> None:
    provider = DirectDecisionStreamingAnswerProvider()

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="简单解释一下现在状态",
            provider=provider,
        )
    )

    deltas = [event.payload["text"] for event in events if event.event == "delta"]
    assert deltas == ["真实", "逐段", "返回。"]
    assert provider.generate_calls
    assert provider.stream_calls
    decision_prompt = json.dumps(
        provider.generate_calls[0]["messages"],
        ensure_ascii=False,
    )
    answer_prompt = json.dumps(
        provider.stream_calls[0]["messages"],
        ensure_ascii=False,
    )
    assert "你是 Isotope Supervisor 的产品对话决策层" in decision_prompt
    assert "capacity_manifest" in decision_prompt
    assert "你是 Isotope 的产品内 AI 助手" in answer_prompt
    assert "真实逐段返回" not in decision_prompt
