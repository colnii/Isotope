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


class PlainTextConversationProvider:
    provider = "deterministic_test"
    model = "plain-text-conversation"

    def __init__(self, response: str) -> None:
        self.response = response
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
            content=self.response,
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={},
        )


class RawSequenceConversationProvider:
    provider = "deterministic_test"
    model = "raw-sequence-conversation"

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
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.responses.pop(0),
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={},
        )


def test_conversation_loop_executes_json_decision_after_leading_model_text(
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
                "kind": "screen_observation",
                "status": "completed",
                "summary": "当前屏幕是 Isotope 桌面对话。",
            }
        )

    monkeypatch.setattr(
        conversation_loop,
        "_execute_capacity_step_with_timeout",
        fake_execute_capacity_step,
    )
    provider = RawSequenceConversationProvider(
        [
            (
                "好的，我先观察一下你的屏幕，看看当前在做什么。\n\n"
                + json.dumps(
                    {
                        "kind": "call_capability",
                        "capacity_id": "screen.observe",
                        "arguments": {
                            "target_selector": {
                                "kind": "window",
                                "app": "",
                                "title_contains": "",
                            },
                            "mode": "non_intrusive",
                            "capture": ["metadata", "screenshot"],
                        },
                        "rationale": "用户要求查看当前屏幕内容。",
                    },
                    ensure_ascii=False,
                )
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer_basis": {
                        "kind": "no_capability_needed",
                        "reason": "测试只验证 capability decision 被执行。",
                    },
                    "answer": "我已经观察过当前屏幕。",
                },
                ensure_ascii=False,
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="看看我的电脑屏幕，我现在在干啥",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert [capacity_id for capacity_id, _inputs in captured_inputs] == [
        "screen.observe"
    ]
    assert events[-1].payload == {"text": "我已经观察过当前屏幕。"}


def test_conversation_loop_rejects_unbased_direct_answer_before_observation(
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
                "answer": "我需要先了解 Isotope 的实际源码后再分析不足。",
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
            user_message="分析 Isotope 当前能力不足",
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
    assert "answer_basis" in second_call_messages


def test_conversation_loop_accepts_no_capability_direct_answer_basis(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            {
                "kind": "direct_answer",
                "answer_basis": {
                    "kind": "no_capability_needed",
                    "reason": "用户只是普通问候。",
                },
                "answer": "你好，有什么需要我帮忙的？",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="你好",
            provider=provider,
            max_turns=2,
        )
    )

    assert [event.event for event in events] == ["delta"]
    assert events[0].payload == {"text": "你好，有什么需要我帮忙的？"}


def test_invalid_direct_answer_observation_does_not_make_next_answer_based(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider(
        [
            {
                "kind": "direct_answer",
                "answer": "我需要先了解 Isotope 的实际源码后再分析不足。",
            },
            {
                "kind": "direct_answer",
                "answer": "我还是直接给结论。",
            },
            {
                "kind": "direct_answer",
                "answer_basis": {
                    "kind": "no_capability_needed",
                    "reason": "用户改为普通闲聊。",
                },
                "answer": "这里只回答普通闲聊。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="分析 Isotope 当前能力不足",
            provider=provider,
            max_turns=4,
        )
    )

    assert [event.event for event in events] == ["delta"]
    assert events[0].payload == {"text": "这里只回答普通闲聊。"}
    assert len(provider.calls) == 3


def test_repeated_invalid_direct_answer_falls_back_before_max_turns(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider(
        [
            {
                "kind": "direct_answer",
                "answer": "我可以直接回答这个普通追问。",
            },
            {
                "kind": "direct_answer",
                "answer": "我还是少了 answer_basis。",
            },
            {
                "kind": "direct_answer",
                "answer": "这次退化为可见回答，不能继续空转。",
            },
            {
                "kind": "direct_answer",
                "answer": "不应该继续请求到这里。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="刚才那个 goal plan 会保存吗？",
            provider=provider,
            max_turns=5,
        )
    )

    assert [event.event for event in events] == ["delta"]
    assert events[0].payload == {"text": "这次退化为可见回答，不能继续空转。"}
    assert events[0].private["decision_kind"] == "direct_answer_recovered"
    assert len(provider.calls) == 3


def test_repeated_non_json_direct_answer_is_returned_instead_of_looping(
    tmp_path,
) -> None:
    provider = PlainTextConversationProvider(
        "`code.read` 有，但只能读取 workspace 内的相对路径，不能读取 UNC 路径。"
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="你不是有 read 能力吗？",
            provider=provider,
            max_turns=10,
        )
    )

    assert [event.event for event in events] == ["delta"]
    assert events[0].payload == {
        "text": "`code.read` 有，但只能读取 workspace 内的相对路径，不能读取 UNC 路径。"
    }
    assert len(provider.calls) == 2
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "invalid_direct_answer" in second_prompt


def test_capability_gap_answer_includes_gap_kind_and_reason(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            {
                "kind": "report_capability_gap",
                "gap": {
                    "missing_capability_kind": "file_read",
                    "reason": (
                        "已有 code.read 只能读取 workspace 内的相对路径，"
                        "不能读取 \\\\wsl.localhost 路径。"
                    ),
                    "needed_context": ["任意本地文件读取能力"],
                },
            }
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="读一下 \\\\wsl.localhost\\Ubuntu\\tmp\\resume62\\6.2.md",
            provider=provider,
            max_turns=2,
        )
    )

    assert [event.event for event in events] == ["capability_gap", "delta"]
    answer = events[1].payload["text"]
    assert "file_read" in answer
    assert "code.read" in answer
    assert "workspace" in answer
    assert "已记录 capability gap" in answer


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
