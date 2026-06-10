from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from isotope.features.supervisor import conversation_loop
from isotope.features.supervisor.conversation_loop import (
    run_supervisor_conversation_events,
)
from isotope.llm.provider import LLMResponse


class RecordingConversationProvider:
    provider = "deterministic_test"
    model = "stub-conversation"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(self.responses.pop(0), ensure_ascii=False),
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={},
        )


def test_conversation_loop_allows_research_repeat_with_new_query(
    tmp_path,
    monkeypatch,
) -> None:
    executed_inputs: list[dict[str, Any]] = []

    def fake_execute_capacity_step(**kwargs: Any) -> dict[str, Any]:
        inputs = dict(kwargs["inputs"])
        executed_inputs.append(inputs)
        return _agent_loop(
            {
                "capability_id": "research.search",
                "research_search": {
                    "status": "ok",
                    "provider": "tavily",
                    "source_count": 2,
                    "artifact_count": 1,
                    "report_summary": f"summary for {inputs['query']}",
                },
            }
        )

    monkeypatch.setattr(
        conversation_loop,
        "_execute_capacity_step_with_timeout",
        fake_execute_capacity_step,
    )
    provider = RecordingConversationProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "research.search",
                "arguments": {"query": "AI OS agent runtime"},
            },
            {
                "kind": "call_capability",
                "capacity_id": "research.search",
                "arguments": {"query": "Agent OS MCP A2A sandbox memory"},
            },
            {
                "kind": "direct_answer",
                "answer": "已基于两次不同方向的调研收束。",
                "answer_basis": {
                    "kind": "observation",
                    "capacity_ids": ["research.search"],
                },
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="调研 AI OS 和 Agent OS 最新实践",
            provider=provider,
            max_turns=4,
        )
    )

    assert [inputs["query"] for inputs in executed_inputs] == [
        "AI OS agent runtime",
        "Agent OS MCP A2A sandbox memory",
    ]
    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[-1].payload["text"] == "已基于两次不同方向的调研收束。"


def test_conversation_loop_reprompts_on_same_research_repeat_without_status_answer(
    tmp_path,
    monkeypatch,
) -> None:
    execute_count = 0

    def fake_execute_capacity_step(**_kwargs: Any) -> dict[str, Any]:
        nonlocal execute_count
        execute_count += 1
        return _agent_loop(
            {
                "capability_id": "research.search",
                "research_search": {
                    "status": "ok",
                    "provider": "tavily",
                    "source_count": 1,
                    "artifact_count": 1,
                    "report_summary": "summary for AI OS agent runtime",
                },
            }
        )

    monkeypatch.setattr(
        conversation_loop,
        "_execute_capacity_step_with_timeout",
        fake_execute_capacity_step,
    )
    provider = RecordingConversationProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "research.search",
                "arguments": {"query": "AI OS agent runtime"},
            },
            {
                "kind": "call_capability",
                "capacity_id": "research.search",
                "arguments": {"query": "AI OS agent runtime"},
            },
            {
                "kind": "direct_answer",
                "answer": "已基于第一次 research.search 的观察结果收束。",
                "answer_basis": {
                    "kind": "observation",
                    "capacity_ids": ["research.search"],
                },
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="调研 AI OS 和 Agent OS 最新实践",
            provider=provider,
            max_turns=4,
        )
    )

    assert execute_count == 1
    assert len(provider.calls) == 3
    assert "invalid_repeated_capability_call" in json.dumps(
        provider.calls[2]["messages"],
        ensure_ascii=False,
    )
    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[-1].payload["text"] == "已基于第一次 research.search 的观察结果收束。"
    assert "research.search 已完成" not in events[-1].payload["text"]


def _agent_loop(capability_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "tick_result": {
            "tick_status": "executed",
            "planner_result": {
                "step_result": {
                    "action_result": {
                        "capability_run": capability_run,
                    }
                }
            },
        }
    }
