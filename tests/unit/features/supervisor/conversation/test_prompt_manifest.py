from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor.conversation_loop import (
    SupervisorConversationEvent,
    run_supervisor_conversation_events,
)
from isotope.llm.provider import LLMResponse


class RecordingConversationProvider:
    provider = "deterministic_test"
    model = "stub-conversation"

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


def no_capability_direct_answer(answer: str) -> str:
    return json.dumps(
        {
            "kind": "direct_answer",
            "answer_basis": {
                "kind": "no_capability_needed",
                "reason": "测试场景不需要能力调用。",
            },
            "answer": answer,
        },
        ensure_ascii=False,
    )


def test_conversation_loop_accepts_no_capability_direct_answer(tmp_path) -> None:
    provider = RecordingConversationProvider([no_capability_direct_answer("你好，我在。")])

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
            provider="deterministic_test",
            model="stub-conversation",
            private={"decision_kind": "direct_answer"},
        )
    ]
    assert len(provider.calls) == 1
    messages = provider.calls[0]["messages"]
    assert messages[-1] == {"role": "user", "content": "你好"}
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "capacity_manifest" in rendered
    assert "direct_answer" in rendered
    assert "answer_basis" in rendered
    assert "call_capability" in rendered
    assert "report_capability_gap" in rendered
    assert "raw_response" not in rendered


def test_conversation_loop_manifest_keeps_research_provider_policy_internal(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider([no_capability_direct_answer("你好，我在。")])

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="你好",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]

    assert '"capability_id": "research.search"' in system_prompt
    research_manifest = system_prompt.split('"capability_id": "research.search"', 1)[1]
    research_manifest = research_manifest.split('"capability_id": "research.promote"', 1)[
        0
    ]
    assert '"query"' in research_manifest
    assert '"provider"' not in research_manifest
    assert '"provider_gate"' not in research_manifest
    assert '"allow_network"' not in research_manifest
    assert "provider=tavily" not in system_prompt


def test_conversation_manifest_hides_system_routing_inputs(tmp_path) -> None:
    provider = RecordingConversationProvider([no_capability_direct_answer("你好，我在。")])

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path / "repo",
            user_message="你好",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert '"code.search"' in system_prompt
    assert '"query"' in system_prompt
    assert '"cwd"' not in system_prompt
    assert '"root"' not in system_prompt


def test_conversation_loop_prompt_routes_goal_planning_to_capacity(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [no_capability_direct_answer("这条测试只检查 prompt。")]
    )

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="帮我规划下一步目标",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert "目标规划、拆目标、规划任务" in system_prompt
    assert "supervisor.goal_plan" in system_prompt
    assert "call_capability" in system_prompt
    assert "不要重复调用已经有 observation 的同一个 capability" in system_prompt


def test_conversation_loop_prompt_separates_manifest_from_observation(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider(
        [no_capability_direct_answer("这条测试只检查 prompt。")]
    )

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="根据项目状态总结一下",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert "capacity_manifest 只能用于发现能力和构造调用" in system_prompt
    assert "选择合法 capacity_id" in system_prompt
    assert "capacity_observation / result projection 才是运行时证据" in system_prompt
    assert "`answer_basis.kind=\"observation\"`" in system_prompt


def test_conversation_loop_manifest_exposes_extension_entrypoints_without_skill_registry(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider([no_capability_direct_answer("你好，我在。")])

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="我需要处理 Word 文档",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert '"capability_id": "skills.search"' in system_prompt
    assert '"capability_id": "skills.describe"' in system_prompt
    assert '"capability_id": "mcp.tool.call"' in system_prompt
    assert "llm2docx" not in system_prompt
    assert "SKILL.md" not in system_prompt
    assert "## Checklist" not in system_prompt
