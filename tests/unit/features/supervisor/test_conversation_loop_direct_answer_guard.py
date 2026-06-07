from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor import conversation_loop
from isotope.features.supervisor.conversation_loop import run_supervisor_conversation_events
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


def test_conversation_loop_rejects_direct_answer_that_promises_tool_call(
    tmp_path,
    monkeypatch,
) -> None:
    captured_inputs: list[tuple[str, dict[str, Any]]] = []

    def fake_execute_capacity_step(**kwargs: Any) -> dict[str, Any]:
        capacity_id = kwargs["capability_id"]
        inputs = dict(kwargs["inputs"])
        captured_inputs.append((capacity_id, inputs))
        return _agent_loop(
            {
                "kind": "project_state",
                "status": "completed",
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
                "kind": "direct_answer",
                "answer": "现在我来正确调用：先搜索 Isotope 的核心模块结构。",
            },
            {
                "kind": "call_capability",
                "capacity_id": "supervisor.project_status",
                "arguments": {},
                "rationale": "需要实际读取项目态势后再回答。",
            },
            {
                "kind": "direct_answer",
                "answer": "已查看项目态势，可以继续分析不足。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="先搜索 Isotope 的核心模块结构",
            provider=provider,
            max_turns=4,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert [capacity_id for capacity_id, _inputs in captured_inputs] == [
        "supervisor.project_status"
    ]
    assert events[-1].payload == {"text": "已查看项目态势，可以继续分析不足。"}
    second_call_messages = json.dumps(
        provider.calls[1]["messages"],
        ensure_ascii=False,
    )
    assert "invalid_direct_answer" in second_call_messages
    assert "call_capability" in second_call_messages


def _agent_loop(capability_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "tick_result": {
            "planner_result": {
                "step_result": {
                    "action_result": {
                        "capability_run": capability_run,
                    }
                }
            }
        }
    }
