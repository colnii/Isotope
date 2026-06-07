from __future__ import annotations

import inspect
import json
import time
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


def test_goal_plan_write_true_from_model_is_ignored_without_explicit_user_request(
    tmp_path,
    monkeypatch,
) -> None:
    captured_inputs: list[dict[str, Any]] = []

    def fake_execute_capacity_step(**kwargs: Any) -> dict[str, Any]:
        inputs = dict(kwargs["inputs"])
        captured_inputs.append(inputs)
        return _agent_loop(
            {
                "goal_plan": {
                    "status": "ok",
                    "mode": "preview",
                    "planning_trigger": "capacity",
                    "candidates": [
                        {
                            "goal": "整理下一步开发方向。",
                            "target_name": "plan-next-development",
                        }
                    ],
                    "written_goals": [],
                }
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
                "capacity_id": "supervisor.goal_plan",
                "arguments": {
                    "goal": "规划 Isotope 下一步开发方向。",
                    "write": True,
                },
                "rationale": "模型误判为需要写入。",
            },
            {
                "kind": "direct_answer",
                "answer": "已生成候选目标，未写入目标队列。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="规划 Isotope 下一步开发方向。",
            provider=provider,
            max_turns=3,
        )
    )

    assert "write" not in captured_inputs[0]
    assert "write" not in events[0].payload["inputs"]
    assert events[-1].payload == {"text": "已生成候选目标，未写入目标队列。"}


def test_goal_plan_confirmation_followup_writes_goal_queue(
    tmp_path,
    monkeypatch,
) -> None:
    captured_inputs: list[dict[str, Any]] = []

    def fake_execute_capacity_step(**kwargs: Any) -> dict[str, Any]:
        inputs = dict(kwargs["inputs"])
        captured_inputs.append(inputs)
        return _agent_loop(
            {
                "goal_plan": {
                    "status": "ok",
                    "mode": "write",
                    "planning_trigger": "capacity",
                    "candidates": [
                        {
                            "goal": "整理 Agent OS 调研结果。",
                            "target_name": "document-agent-os-research",
                        }
                    ],
                    "written_goals": [
                        {
                            "goal": "整理 Agent OS 调研结果。",
                            "target_name": "document-agent-os-research",
                        }
                    ],
                }
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
                "capacity_id": "supervisor.goal_plan",
                "arguments": {
                    "goal": "基于 Agent OS 前沿设计调研结果，推进 Isotope 开发规划"
                },
                "rationale": "用户确认写入上一轮规划。",
            },
            {
                "kind": "direct_answer",
                "answer": "已写入目标队列。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="可以写入",
            provider=provider,
            max_turns=3,
        )
    )

    assert captured_inputs[0]["write"] is True
    assert events[0].payload["inputs"]["write"] is True
    assert events[-1].payload == {"text": "已写入目标队列。"}


def test_conversation_loop_answers_instead_of_repeating_completed_capacity(
    tmp_path,
    monkeypatch,
) -> None:
    execute_count = 0

    def fake_execute_capacity_step(**_kwargs: Any) -> dict[str, Any]:
        nonlocal execute_count
        execute_count += 1
        return _agent_loop(
            {
                "goal_plan": {
                    "status": "ok",
                    "mode": "preview",
                    "planning_trigger": "capacity",
                    "plan_summary": "下一步应先修复桌面 chat 的收束问题。",
                    "candidates": [
                        {
                            "goal": "修复桌面 chat capacity loop 收束。",
                            "target_name": "fix-chat-loop",
                        }
                    ],
                    "written_goals": [],
                }
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
                "capacity_id": "supervisor.goal_plan",
                "arguments": {"goal": "规划下一步"},
                "rationale": "先规划。",
            },
            {
                "kind": "call_capability",
                "capacity_id": "supervisor.goal_plan",
                "arguments": {"goal": "规划下一步"},
                "rationale": "重复调用同一能力。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="规划下一步",
            provider=provider,
            max_turns=2,
        )
    )

    assert execute_count == 1
    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert "supervisor.goal_plan 已完成" in events[-1].payload["text"]
    assert "修复桌面 chat capacity loop 收束" in events[-1].payload["text"]


def test_conversation_loop_default_max_turns_is_300() -> None:
    signature = inspect.signature(run_supervisor_conversation_events)

    assert signature.parameters["max_turns"].default == 300


def test_conversation_loop_runs_parallel_capacity_decision_with_updates(
    tmp_path,
    monkeypatch,
) -> None:
    captured_inputs: list[tuple[str, dict[str, Any]]] = []

    def fake_execute_capacity_step(**kwargs: Any) -> dict[str, Any]:
        capacity_id = kwargs["capability_id"]
        inputs = dict(kwargs["inputs"])
        captured_inputs.append((capacity_id, inputs))
        if capacity_id == "supervisor.project_status":
            time.sleep(0.05)
        return _agent_loop(
            {
                "kind": capacity_id.replace(".", "_"),
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
                "kind": "call_capabilities",
                "calls": [
                    {
                        "capacity_id": "supervisor.project_status",
                        "arguments": {},
                    },
                    {
                        "capacity_id": "memory.recall",
                        "arguments": {"query": "capacity loop"},
                    },
                ],
                "rationale": "状态和记忆可以并行获取。",
            },
            {
                "kind": "direct_answer",
                "answer": "并行能力调用已完成。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="同时看项目状态和记忆",
            provider=provider,
            max_turns=3,
        )
    )

    names = [event.event for event in events]
    assert names.count("capacity_start") == 2
    assert names.count("capacity_update") >= 2
    assert names.count("capacity_result") == 2
    assert names[-1] == "delta"
    assert {capacity_id for capacity_id, _inputs in captured_inputs} == {
        "supervisor.project_status",
        "memory.recall",
    }
    first_result_index = names.index("capacity_result")
    assert names[:first_result_index].count("capacity_start") == 2
    assert events[-1].payload == {"text": "并行能力调用已完成。"}


def test_goal_plan_receives_prior_research_observation_context(
    tmp_path,
    monkeypatch,
) -> None:
    captured_inputs: list[tuple[str, dict[str, Any]]] = []

    def fake_execute_capacity_step(**kwargs: Any) -> dict[str, Any]:
        capacity_id = kwargs["capability_id"]
        inputs = dict(kwargs["inputs"])
        captured_inputs.append((capacity_id, inputs))
        if capacity_id == "research.search":
            return _agent_loop(
                {
                    "capability_id": "research.search",
                    "research_search": {
                        "status": "ok",
                        "provider": "tavily",
                        "source_count": 2,
                        "artifact_count": 2,
                        "report_summary": "Agent OS 前沿强调 sandbox runtime、persistent memory 和多 agent 调度。",
                        "source_previews": [
                            {
                                "source_id": "src_001",
                                "title": "Agent OS Runtime Design",
                                "url": "https://example.test/agent-os-runtime",
                                "snippet": "Sandbox runtime becomes the execution boundary.",
                            },
                            {
                                "source_id": "src_002",
                                "title": "Persistent Agent Memory",
                                "url": "https://example.test/agent-memory",
                                "snippet": "Memory and task state make agents resumable.",
                            },
                        ],
                    },
                }
            )
        return _agent_loop(
            {
                "goal_plan": {
                    "status": "ok",
                    "mode": "preview",
                    "planning_trigger": "capacity",
                    "plan_summary": "基于调研规划 Isotope。",
                    "candidates": [
                        {
                            "goal": "把 sandbox runtime 作为 Isotope 下一阶段规划输入。",
                            "target_name": "plan-sandbox-runtime",
                        }
                    ],
                    "written_goals": [],
                }
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
                "arguments": {
                    "query": "Agent OS 前沿设计 sandbox runtime persistent memory"
                },
                "rationale": "先调研。",
            },
            {
                "kind": "call_capability",
                "capacity_id": "supervisor.goal_plan",
                "arguments": {"goal": "基于调研结果继续推进 Isotope 开发规划"},
                "rationale": "再规划。",
            },
            {
                "kind": "direct_answer",
                "answer": "已基于调研生成规划。",
            },
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="调研 Agent OS 前沿设计，继续推进 Isotope 开发规划",
            provider=provider,
            max_turns=4,
        )
    )

    goal_plan_inputs = [
        inputs
        for capacity_id, inputs in captured_inputs
        if capacity_id == "supervisor.goal_plan"
    ][0]
    assert "research_context" in goal_plan_inputs
    assert "sandbox runtime" in goal_plan_inputs["research_context"]
    assert "Persistent Agent Memory" in goal_plan_inputs["research_context"]
    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "capacity_start",
        "capacity_result",
        "delta",
    ]


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
