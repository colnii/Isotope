from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import time
from typing import Any

from isotope.capabilities.runner import CapabilityRunner
from isotope.features.supervisor.conversation_loop import (
    run_supervisor_conversation_events,
)
from isotope.features.supervisor.planner.goal_queue import (
    read_active_supervisor_goals,
    record_supervisor_goal,
)
from isotope.features.supervisor.registry import (
    ManagedCodexRecord,
    append_managed_record,
    default_registry_path,
)
from isotope.llm.provider import LLMResponse
from isotope.platform.schemas.memory import MemoryRecord


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


class NativeCodingSequenceProvider:
    provider = "deterministic_test"
    model = "stub-native-coding"

    def __init__(
        self,
        planner_steps: list[tuple[str, dict[str, Any]]],
        *,
        goal: str = "Change src/app.py value to 2.",
        coding_arguments: dict[str, Any] | None = None,
    ) -> None:
        self.goal = goal
        self.coding_arguments = coding_arguments or {"goal": goal}
        self.planner_steps = list(planner_steps)
        self.conversation_calls = 0
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        planner_prompt = _planner_prompt_payload(messages)
        if planner_prompt is not None:
            capability_id, inputs = self.planner_steps.pop(0)
            return LLMResponse(
                provider=self.provider,
                model=self.model,
                content=json.dumps(
                    {
                        "planner_run_id": f"planner-{len(self.calls)}",
                        "basis": {
                            "run_id": planner_prompt["control"]["run_id"],
                            "last_event_id": planner_prompt["control"]["last_event_id"],
                        },
                        "decision": {
                            "step": "call_capability",
                            "request": {
                                "capability_id": capability_id,
                                "inputs": inputs,
                            },
                        },
                    }
                ),
                finish_reason="stop",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
                raw={"raw_response": "must not leak"},
            )

        self.conversation_calls += 1
        if self.conversation_calls == 1:
            content = json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "coding_task.run",
                    "arguments": dict(self.coding_arguments),
                    "rationale": "Use native coding.",
                }
            )
        else:
            content = json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "改动已验证，等待你审阅。",
                }
            )
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=content,
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={"raw_response": "must not leak"},
        )


def _planner_prompt_payload(messages: list[dict[str, str]]) -> dict[str, Any] | None:
    if len(messages) < 2:
        return None
    try:
        payload = json.loads(messages[1]["content"])
    except (KeyError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if "control" not in payload or "default_context" not in payload:
        return None
    return payload


class ConversationGoalPlanProvider:
    def __init__(self, expected_goal: str) -> None:
        self.expected_goal = expected_goal

    def summarize(self, messages: list[dict[str, str]]) -> str:
        user_payload = json.loads(messages[1]["content"])
        assert user_payload["user_goal"] == self.expected_goal
        assert user_payload["planning_trigger"] == "capacity"
        return json.dumps(
            {
                "plan_summary": "chat 已通过 capacity 生成目标规划。",
                "goals": [
                    {
                        "goal": "把 chat 目标规划接入 supervisor.goal_plan capacity。",
                        "target_name": "chat-goal-plan-capacity",
                        "reason": "用户在 chat 里要求规划下一步目标。",
                    }
                ],
            },
            ensure_ascii=False,
        )


def _write_goal_planning_docs(root) -> None:
    docs = root / "docs" / "current"
    docs.mkdir(parents=True)
    (docs / "status.md").write_text("chat 需要复用目标规划能力。\n", encoding="utf-8")
    (docs / "agent-task-queue.md").write_text("目标规划已是 capacity。\n", encoding="utf-8")
    (docs / "supervisor-capability-map.md").write_text(
        "supervisor.goal_plan 可生成目标规划。\n",
        encoding="utf-8",
    )


def _write_memory_record(memory_dir, record: MemoryRecord) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.joinpath(f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )


def test_conversation_loop_does_not_add_goal_plan_capacity_timeout() -> None:
    from isotope.features.supervisor import conversation_loop

    assert conversation_loop._capacity_timeout_seconds("artifact.review", 4) == 4
    assert conversation_loop._capacity_timeout_seconds("supervisor.goal_plan", 4) is None
    assert (
        conversation_loop._capacity_timeout_seconds("supervisor.goal_plan", None)
        is None
    )


def test_conversation_loop_goal_plan_write_route_respects_preview_request() -> None:
    from isotope.features.supervisor import conversation_loop

    assert conversation_loop._explicit_goal_plan_write_requested(
        "帮我规划下一步目标，先预览，" + "不" + "要写入目标队列"
    ) is False
    assert conversation_loop._explicit_goal_plan_write_requested(
        "帮我规划下一步目标，并写入目标队列"
    ) is True


def test_conversation_loop_goal_plan_write_route_uses_execution_language() -> None:
    from isotope.features.supervisor import conversation_loop

    source = Path(conversation_loop.__file__).read_text(encoding="utf-8")

    for term in (
        "guard" + "rail",
        "不" + "要写",
        "不" + "要入队",
        "不" + "写入",
    ):
        assert term not in source


def test_conversation_loop_uses_longer_timeout_for_research_search_capacity() -> None:
    from isotope.features.supervisor import conversation_loop

    assert conversation_loop._capacity_timeout_seconds("artifact.review", 18) == 18
    assert conversation_loop._capacity_timeout_seconds("research.search", 18) >= 90


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
                    "answer": "能力已执行，结果已经返回。",
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
    assert events[1].payload["result"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload == {"text": "能力已执行，结果已经返回。"}
    assert len(provider.calls) == 2
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "raw_response" not in second_prompt


def test_conversation_loop_executes_goal_plan_capacity_from_chat(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import supervisor_goal_plan

    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_goal_planning_docs(workspace)
    state_root = tmp_path / "state"
    user_goal = "帮我规划下一步目标"
    monkeypatch.setattr(
        supervisor_goal_plan,
        "resolve_summary_provider_from_env",
        lambda **_: ConversationGoalPlanProvider(user_goal),
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.goal_plan",
                    "arguments": {"goal": user_goal},
                    "rationale": "用户要求目标规划。",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已通过目标规划 capacity 生成候选目标。",
                },
                ensure_ascii=False,
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=state_root,
            cwd=workspace,
            user_message=user_goal,
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "supervisor.goal_plan"
    assert events[0].payload["inputs"] == {
        "state_root": str(state_root),
        "cwd": str(workspace),
        "goal": user_goal,
    }
    assert events[1].payload["capacity_id"] == "supervisor.goal_plan"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload["text"] == "已通过目标规划 capacity 生成候选目标。"
    assert read_active_supervisor_goals(codex_home=state_root) == ()
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "chat-goal-plan-capacity" in second_prompt
    assert "raw_response" not in second_prompt


def test_conversation_loop_writes_goal_plan_when_user_explicitly_requests_queue(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import supervisor_goal_plan

    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_goal_planning_docs(workspace)
    state_root = tmp_path / "state"
    user_goal = "帮我规划下一步目标，并写入目标队列"
    monkeypatch.setattr(
        supervisor_goal_plan,
        "resolve_summary_provider_from_env",
        lambda **_: ConversationGoalPlanProvider(user_goal),
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.goal_plan",
                    "arguments": {"goal": user_goal},
                    "rationale": "用户要求目标规划并入队。",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已写入目标队列。",
                },
                ensure_ascii=False,
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=state_root,
            cwd=workspace,
            user_message=user_goal,
            provider=provider,
            max_turns=3,
        )
    )

    assert events[0].payload["inputs"]["write"] is True
    assert events[1].payload["status"] == "ok"
    active_goals = read_active_supervisor_goals(codex_home=state_root)
    assert len(active_goals) == 1
    assert active_goals[0].goal == "把 chat 目标规划接入 supervisor.goal_plan capacity。"
    observation_content = provider.calls[1]["messages"][1]["content"]
    observation_payload = json.loads(observation_content.split(":\n", 1)[1])
    assert observation_payload["items"][0]["result"]["written_count"] == 1


def test_conversation_loop_recalls_existing_state_root_memory_without_run_id(
    tmp_path,
) -> None:
    memory_dir = tmp_path / "state" / "memory"
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_desktop_recall",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="Desktop chat should recall this state-root memory preview.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_real_memory",
                "execution_id": "exec_real_memory",
                "action_type": "write_memory",
            },
            created_at="2026-06-04T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "memory.recall",
                    "arguments": {
                        "query": "state-root memory preview",
                        "scope": "run",
                    },
                    "rationale": "Recall public memory preview.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "找到了相关记忆。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path / "repo",
            user_message="查一下 state-root memory preview 的记忆",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "memory.recall"
    assert events[0].payload["inputs"] == {
        "query": "state-root memory preview",
        "root": str(tmp_path / "state"),
        "scope": "run",
    }
    assert events[1].payload["status"] == "ok"
    result = events[1].payload["result"]
    assert result["agent_loop_memory_recall_status"] == "ok"
    assert result["agent_loop_memory_recall_result_count"] == 1
    rendered_events = json.dumps([event.payload for event in events], ensure_ascii=False)
    assert "Desktop chat should recall this state-root memory preview." in rendered_events
    assert "raw memory content must not leak" not in rendered_events


def test_conversation_loop_filters_model_supplied_inputs_to_capability_contract(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import research as research_capability
    from isotope.features.supervisor import conversation_loop

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(conversation_loop, "tavily_api_key_from_config", lambda: None)

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query: str) -> dict[str, Any]:
            return {
                "research_id": "research_contract_filter_unit",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [],
                "report": {
                    "summary": "Filtered research input summary.",
                    "claims": [],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        lambda provider_id, **kwargs: RecordingCodexProvider(),
    )

    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {
                        "query": "capacity research integration",
                        "provider": "tavily",
                        "provider_gate": "tavily_research",
                        "root": "/",
                        "cwd": "/tmp/model-cwd",
                        "state_root": "/tmp/model-state-root",
                    },
                    "rationale": "需要试跑 research capability。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "research.search 已执行。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="测试一下 research.search",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    inputs = events[0].payload["inputs"]
    assert inputs == {
        "query": "capacity research integration",
        "root": str(tmp_path),
    }
    assert events[1].payload["capacity_id"] == "research.search"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result"]["agent_loop_research_provider"] == (
        "codex_delegated"
    )
    assert events[2].payload == {"text": "research.search 已执行。"}


def test_conversation_loop_uses_internal_research_provider_policy(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import research as research_capability
    from isotope.features.supervisor import conversation_loop

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(conversation_loop, "tavily_api_key_from_config", lambda: None)
    provider_calls: list[dict[str, Any]] = []

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query: str) -> dict[str, Any]:
            return {
                "research_id": "research_codex_unit",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Codex delegated source",
                        "url": "https://example.com/research",
                        "snippet": "Codex delegated research returns cited snippets.",
                        "why_used": "unit test Codex provider",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Codex delegated research summary.",
                    "claims": [
                        {
                            "text": "Codex delegated research returns cited snippets.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "codex_delegated"},
            }

    def build_provider(provider_id: str, **kwargs: Any) -> RecordingCodexProvider:
        provider_calls.append({"provider_id": provider_id, **kwargs})
        return RecordingCodexProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )

    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {
                        "query": "https://example.com/research",
                        "provider": "codex",
                        "provider_gate": "codex_research",
                        "allow_network": True,
                    },
                    "rationale": "需要 research.search。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "research.search 已执行。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="访问网页并总结",
            provider=provider,
            max_turns=3,
        )
    )

    inputs = events[0].payload["inputs"]
    assert inputs == {"query": "https://example.com/research", "root": str(tmp_path)}
    assert events[0].event == "capacity_start"
    assert events[1].event == "capacity_result"
    assert events[1].payload["result"]["agent_loop_research_provider"] == (
        "codex_delegated"
    )
    assert provider_calls == [
        {
            "provider_id": "codex",
            "workspace_root": str(tmp_path),
        }
    ]


def test_conversation_loop_uses_configured_tavily_without_exposing_policy_inputs(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import research as research_capability

    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    provider_calls: list[dict[str, Any]] = []

    class RecordingTavilyProvider:
        provider_name = "tavily"

        def run(self, query: str) -> dict[str, Any]:
            return {
                "research_id": "research_tavily_unit",
                "query": query,
                "provider": "tavily",
                "created_at": "2026-06-04T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Tavily source",
                        "url": "https://example.com/tavily",
                        "snippet": "Tavily returned source-backed search data.",
                        "why_used": "unit test Tavily provider",
                        "retrieved_at": "2026-06-04T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Tavily search summary.",
                    "claims": [
                        {
                            "text": "Tavily returned source-backed search data.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "tavily"},
            }

    def build_provider(provider_id: str, **kwargs: Any) -> RecordingTavilyProvider:
        provider_calls.append({"provider_id": provider_id, **kwargs})
        return RecordingTavilyProvider()

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        build_provider,
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {"query": "OpenAI news"},
                    "rationale": "需要 research.search。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "research.search 已执行。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="搜索 OpenAI news",
            provider=provider,
            max_turns=3,
        )
    )

    assert events[0].payload["inputs"] == {
        "query": "OpenAI news",
        "root": str(tmp_path),
    }
    assert events[1].payload["result"]["agent_loop_research_provider"] == "tavily"
    assert provider_calls == [
        {
            "provider_id": "tavily",
            "workspace_root": str(tmp_path),
            "tavily_enable_network": True,
        }
    ]


def test_conversation_loop_can_use_project_status_without_fixed_route(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    record_supervisor_goal(
        codex_home=tmp_path,
        goal="把 Desktop chat 打成黄金路径",
        cwd=workspace,
        target_name="desktop-chat",
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.project_status",
                    "arguments": {},
                    "rationale": "需要读取当前项目态势。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "当前有 Desktop chat 目标正在推进。",
                    "rationale": "基于项目态势 observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=workspace,
            user_message="现在项目态势怎么样？",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "supervisor.project_status"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result"]["agent_loop_project_status_status"] == (
        "completed"
    )
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "project_state" in second_prompt
    assert "把 Desktop chat 打成黄金路径" in second_prompt
    assert events[2].payload == {"text": "当前有 Desktop chat 目标正在推进。"}


def test_conversation_loop_project_status_observes_self_repair_worker_status(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    worker_cwd = workspace / ".worktrees" / "supervisor" / "desktop-self-repair"
    worker_cwd.mkdir(parents=True)
    log_path = tmp_path / "supervisor" / "logs" / "managed-self-repair.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: done",
                "SUPERVISOR_SUMMARY: 已修复 Desktop chat 项目态势读取。",
                "SUPERVISOR_NEXT: 等待主线合并。",
            ]
        ),
        encoding="utf-8",
    )
    append_managed_record(
        default_registry_path(tmp_path),
        ManagedCodexRecord(
            record_id="managed-self-repair",
            name="desktop-self-repair",
            cwd=str(worker_cwd),
            prompt="Isotope self-repair request must stay private.",
            command=("codex", "exec", "-C", str(worker_cwd), "prompt"),
            pid=0,
            started_at="2026-06-04T00:00:00+00:00",
            log_path=str(log_path),
            status="launched",
            backend="process",
            worker_role="self_repair",
        ),
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.project_status",
                    "arguments": {},
                    "rationale": "需要读取自修复 worker 状态。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "自修复 worker 已完成，等待主线合并。",
                    "rationale": "基于项目态势 observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=workspace,
            user_message="自修复现在怎么样了？",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["result"][
        "agent_loop_project_status_self_repair_count"
    ] == 1
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    observation_message = provider.calls[1]["messages"][1]["content"]
    assert "self_repair_workers" in second_prompt
    assert "desktop-self-repair" in second_prompt
    assert "已修复 Desktop chat 项目态势读取。" in second_prompt
    assert "Isotope self-repair request" not in observation_message
    assert events[2].payload == {"text": "自修复 worker 已完成，等待主线合并。"}


def test_conversation_loop_project_status_observes_latest_self_repair_summary(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    worker_cwd = workspace / ".worktrees" / "supervisor" / "desktop-self-repair"
    worker_cwd.mkdir(parents=True)
    log_path = tmp_path / "supervisor" / "logs" / "managed-self-repair.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: done",
                "SUPERVISOR_SUMMARY: 已补齐最新自修复结果摘要。",
                "SUPERVISOR_NEXT: 等待主线合并。",
            ]
        ),
        encoding="utf-8",
    )
    append_managed_record(
        default_registry_path(tmp_path),
        ManagedCodexRecord(
            record_id="managed-self-repair",
            name="desktop-self-repair",
            cwd=str(worker_cwd),
            prompt="Isotope self-repair request must stay private.",
            command=("codex", "exec", "-C", str(worker_cwd), "prompt"),
            pid=0,
            started_at="2026-06-04T01:00:00+00:00",
            log_path=str(log_path),
            status="launched",
            backend="process",
            worker_role="self_repair",
        ),
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.project_status",
                    "arguments": {},
                    "rationale": "需要读取最近自修复结果。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "最近一次自修复已完成，建议先复查 diff 再合并。",
                    "rationale": "基于 latest_self_repair observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=workspace,
            user_message="最近一次自修复能不能合？",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    result = events[1].payload["result"]
    assert result["agent_loop_project_status_latest_self_repair_status"] == "done"
    assert result["agent_loop_project_status_latest_self_repair_name"] == (
        "desktop-self-repair"
    )
    assert result["agent_loop_project_status_latest_self_repair_merge_suitable"] is True
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    observation_message = provider.calls[1]["messages"][1]["content"]
    assert "latest_self_repair" in second_prompt
    assert "已补齐最新自修复结果摘要。" in second_prompt
    assert "review_then_merge_candidate" in second_prompt
    assert "Isotope self-repair request" not in observation_message
    assert events[2].payload == {
        "text": "最近一次自修复已完成，建议先复查 diff 再合并。"
    }


def test_conversation_loop_project_status_observes_open_capability_gaps(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    gap_dir = tmp_path / "supervisor" / "capability-gaps"
    gap_dir.mkdir(parents=True)
    (gap_dir / "gap_skills.json").write_text(
        json.dumps(
            {
                "kind": "capability_gap",
                "gap_id": "gap_skills",
                "status": "recorded",
                "missing_capability_kind": "skills.mcp.install",
                "reason": "需要安装 skills MCP，但当前没有安全安装能力。",
                "needed_context": ["skills registry", "mcp config"],
                "suggested_next_capability": "isotope.self_repair",
                "source_entrypoint": "desktop_chat",
                "user_goal": "private gap user goal should not be projected",
                "created_at": "2026-06-04T02:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.project_status",
                    "arguments": {},
                    "rationale": "需要读取未解决能力缺口。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "当前有 skills MCP 安装能力缺口，可用自修复继续处理。",
                    "rationale": "基于 open_capability_gaps observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=workspace,
            user_message="Isotope 现在缺什么能力？",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    result = events[1].payload["result"]
    assert result["agent_loop_project_status_open_capability_gap_count"] == 1
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    observation_message = provider.calls[1]["messages"][1]["content"]
    assert "open_capability_gaps" in second_prompt
    assert "gap_skills" in second_prompt
    assert "skills.mcp.install" in second_prompt
    assert "需要安装 skills MCP" in second_prompt
    assert "private gap user goal" not in observation_message
    assert events[2].payload == {
        "text": "当前有 skills MCP 安装能力缺口，可用自修复继续处理。"
    }


def test_conversation_loop_can_launch_codex_assisted_self_repair(
    tmp_path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()

    def fake_prepare_launch_worktree(*, cwd, target_name, api=None):
        repair_root = workspace / ".worktrees" / "supervisor" / target_name
        repair_root.mkdir(parents=True)
        return {
            "enabled": True,
            "source_cwd": str(cwd),
            "cwd": str(repair_root),
            "worktree_root": str(repair_root),
            "branch": f"codex/{target_name}",
        }

    class FakeRecord:
        name = "desktop-self-repair"
        record_id = "managed-self-repair"
        pid = 12345
        backend = "process"
        worker_role = "self_repair"
        cwd = str(workspace / ".worktrees" / "supervisor" / "desktop-self-repair")
        log_path = str(tmp_path / "self-repair.log")

    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.prepare_launch_worktree",
        fake_prepare_launch_worktree,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.launch_managed_codex",
        lambda **kwargs: FakeRecord(),
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "isotope.self_repair",
                    "arguments": {
                        "user_goal": "让 Desktop chat 能回答项目态势。",
                        "failure_summary": "缺少项目态势读取能力。",
                        "suggested_fix_summary": "接入 supervisor.project_status。",
                    },
                    "rationale": "需要 Codex 辅助修复 Isotope 自身缺口。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已启动 Codex 自修复 worker。",
                    "rationale": "基于 self-repair observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=workspace,
            user_message="这个缺口让 Isotope 自己修一下。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "isotope.self_repair"
    assert "state_root" not in events[0].payload["inputs"]
    assert events[1].payload["result"]["agent_loop_self_repair_status"] == (
        "launched"
    )
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    observation_message = provider.calls[1]["messages"][1]["content"]
    assert "self_repair" in second_prompt
    assert "desktop-self-repair" in second_prompt
    assert "Isotope self-repair request" not in observation_message
    assert "不要合入 main" not in observation_message
    assert events[2].payload == {"text": "已启动 Codex 自修复 worker。"}


def test_conversation_loop_returns_capacity_error_when_execution_times_out(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.features.supervisor import conversation_loop

    def slow_capacity_step(**kwargs: Any) -> dict[str, Any]:
        time.sleep(0.2)
        return {}

    monkeypatch.setattr(
        conversation_loop,
        "_execute_agent_loop_capacity_step",
        slow_capacity_step,
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {"query": "https://example.com/research"},
                    "rationale": "需要调用 research.search。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "research.search 执行超时，未拿到网页内容。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="访问网页并总结",
            provider=provider,
            max_turns=3,
            timeout_seconds=0.05,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["status"] == "error"
    assert events[1].payload["result"] == {
        "error_type": "TimeoutError",
        "message": "research.search capacity execution timed out after 0.05s",
        "capacity_id": "research.search",
        "timeout_seconds": 0.05,
    }
    assert events[2].payload == {
        "text": "research.search 执行超时，未拿到网页内容。"
    }


def test_conversation_loop_stops_when_model_repeats_failed_capacity(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.features.supervisor import conversation_loop

    def failing_capacity_step(**kwargs: Any) -> dict[str, Any]:
        raise TimeoutError("capacity execution timed out")

    monkeypatch.setattr(
        conversation_loop,
        "_execute_agent_loop_capacity_step",
        failing_capacity_step,
    )
    repeated_call = json.dumps(
        {
            "kind": "call_capability",
            "capacity_id": "research.search",
            "arguments": {"query": "OpenAI news"},
            "rationale": "需要调用 research.search。",
        }
    )
    provider = RecordingConversationProvider([repeated_call, repeated_call])

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="实际搜索 OpenAI news",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["status"] == "error"
    assert events[2].payload == {
        "text": "research.search 执行失败：research.search capacity execution timed out after 120s"
    }
    assert len(provider.calls) == 2


def test_conversation_loop_records_public_metadata_capability_gap(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "report_capability_gap",
                    "gap": {
                        "missing_capability_kind": "supervisor.discovery.worker_list",
                        "reason": "需要查询 worker 列表，但没有对应 discovery capability。",
                        "needed_context": ["worker list", "active run state"],
                    },
                    "rationale": "缺少基础 discovery 能力。",
                }
            )
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path,
            user_message="看看哪个 worker 卡住了",
            provider=provider,
        )
    )

    assert [event.event for event in events] == ["capability_gap", "delta"]
    gap = events[0].payload
    assert gap["missing_capability_kind"] == "supervisor.discovery.worker_list"
    assert gap["source_entrypoint"] == "desktop_chat"
    assert gap["status"] == "recorded"
    assert events[1].payload["text"] == "我缺少对应的基础能力，已记录 capability gap。"
    gap_files = list((tmp_path / "supervisor" / "capability-gaps").glob("*.json"))
    assert len(gap_files) == 1
    saved = json.loads(gap_files[0].read_text(encoding="utf-8"))
    assert saved["missing_capability_kind"] == "supervisor.discovery.worker_list"
    rendered = json.dumps(saved, ensure_ascii=False)
    assert "raw_response" not in rendered
    assert "messages" not in rendered
def test_conversation_loop_executes_native_coding_capacity_with_safe_observation(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "coding_task.execute",
                    "arguments": {
                        "workspace_id": "workspace_desktop_native_coding",
                        "goal": "Change value to 2.",
                        "patch": (
                            "--- a/src/app.py\n"
                            "+++ b/src/app.py\n"
                            "@@ -1 +1 @@\n"
                            "-value = 1\n"
                            "+value = 2\n"
                        ),
                        "argv": [
                            "python3",
                            "-c",
                            "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
                        ],
                        "allowed_commands": ["python3"],
                        "include_paths": ["src"],
                    },
                    "rationale": "Use native coding capacity.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已完成 native coding capacity。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=workspace,
            user_message="把 src/app.py 的 value 改成 2。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "coding_task.execute"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload["text"] == "已完成 native coding capacity。"
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    materialized = (
        tmp_path
        / "state"
        / "workspaces"
        / "workspace_desktop_native_coding"
        / "src"
        / "app.py"
    )
    assert materialized.read_text(encoding="utf-8") == "value = 2\n"
    rendered_events = json.dumps(
        [event.payload for event in events],
        ensure_ascii=False,
    )
    assert "value = 1" not in rendered_events
    assert "value = 2" not in rendered_events
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "value = 1" not in second_prompt
    assert "value = 2" not in second_prompt

def test_conversation_loop_runs_coding_task_run_through_existing_agent_loop(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    provider = NativeCodingSequenceProvider(
        [
            ("code.search", {"query": "value", "include_paths": ["src"]}),
            ("code.read", {"path": "src/app.py"}),
            (
                "coding_task.execute",
                {
                    "goal": "Change src/app.py value to 2.",
                    "patch": (
                        "--- a/src/app.py\n"
                        "+++ b/src/app.py\n"
                        "@@ -1 +1 @@\n"
                        "-value = 1\n"
                        "+value = 2\n"
                    ),
                    "argv": [
                        "python3",
                        "-c",
                        "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
                    ],
                    "allowed_commands": ["python3"],
                    "include_paths": ["src"],
                },
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=workspace,
            user_message="把 src/app.py 的 value 改成 2。",
            provider=provider,
            max_turns=4,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "coding_task.run"
    assert events[1].payload["status"] == "ok"
    summary = events[1].payload["result"]
    assert summary["agent_loop_coding_status"] == "verified"
    assert summary["agent_loop_coding_context_calls"] >= 2
    assert summary["agent_loop_coding_review_handle_available"] is True
    assert (
        summary["agent_loop_coding_reviewed_apply_capability_id"]
        == "coding_task.apply_reviewed_diff"
    )
    assert summary["agent_loop_coding_reviewed_apply_changed_file_count"] == 1
    second_prompt = provider.calls[-1]["messages"][1]["content"]
    assert '"suggested_next_call"' in second_prompt
    assert '"coding_task.apply_reviewed_diff"' in second_prompt
    assert '"review_handle_id"' in second_prompt
    assert '"expected_source_digests"' not in second_prompt
    assert str(workspace) not in second_prompt
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    rendered = json.dumps([event.payload for event in events], ensure_ascii=False)
    assert "value = 1" not in rendered
    assert "value = 2" not in rendered
    assert "argv" not in rendered


def test_coding_task_run_allows_scoped_revision_after_failed_verification(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    provider = NativeCodingSequenceProvider(
        [
            (
                "coding_task.execute",
                {
                    "goal": "Wrong attempt.",
                    "patch": (
                        "--- a/src/app.py\n"
                        "+++ b/src/app.py\n"
                        "@@ -1 +1 @@\n"
                        "-value = 1\n"
                        "+value = 3\n"
                    ),
                    "argv": [
                        "python3",
                        "-c",
                        "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
                    ],
                    "allowed_commands": ["python3"],
                    "include_paths": ["src"],
                },
            ),
            (
                "coding_task.execute",
                {
                    "goal": "Correct attempt.",
                    "patch": (
                        "--- a/src/app.py\n"
                        "+++ b/src/app.py\n"
                        "@@ -1 +1 @@\n"
                        "-value = 1\n"
                        "+value = 2\n"
                    ),
                    "argv": [
                        "python3",
                        "-c",
                        "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
                    ],
                    "allowed_commands": ["python3"],
                    "include_paths": ["src"],
                },
            ),
        ],
        coding_arguments={"goal": "Change value to 2.", "max_steps": 4},
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=workspace,
            user_message="把 value 改成 2。",
            provider=provider,
            max_turns=4,
        )
    )

    summary = events[1].payload["result"]
    assert events[1].payload["status"] == "ok"
    assert summary["agent_loop_coding_status"] == "verified"
    assert summary["agent_loop_coding_tick_count"] == 2
    assert summary["agent_loop_coding_source_workspace_write"] == "not_performed"
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"

def test_conversation_loop_applies_reviewed_native_coding_diff(tmp_path) -> None:
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    root = tmp_path / "state"
    execute_result = CapabilityRunner().run_capability(
        "coding_task.execute",
        inputs={
            "root": str(root),
            "cwd": str(workspace),
            "workspace_id": "workspace_conversation_apply",
            "goal": "Change value to 2.",
            "patch": (
                "--- a/src/app.py\n"
                "+++ b/src/app.py\n"
                "@@ -1 +1 @@\n"
                "-value = 1\n"
                "+value = 2\n"
            ),
            "argv": [
                "python3",
                "-c",
                "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
            ],
            "allowed_commands": ["python3"],
            "run_id": "run_conversation_apply",
            "execution_id": "execution_conversation_apply",
            "include_paths": ["src"],
        },
    )
    reviewed_apply = execute_result["coding_execution"]["reviewed_apply"]
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "coding_task.apply_reviewed_diff",
                    "arguments": {
                        "review_handle_id": reviewed_apply["review_handle_id"],
                        "include_paths": ["src"],
                    },
                }
            ),
            json.dumps({"kind": "direct_answer", "answer": "已应用。"}),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=root,
            cwd=workspace,
            user_message="应用刚才审阅通过的改动。",
            provider=provider,
            max_turns=3,
        )
    )

    assert events[1].payload["status"] == "ok"
    summary = events[1].payload["result"]
    assert summary["agent_loop_reviewed_apply_status"] == "applied"
    assert summary["agent_loop_reviewed_apply_source_workspace_write"] == "performed"
    assert summary["agent_loop_reviewed_apply_applied_files"] == ["src/app.py"]
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    rendered = json.dumps([event.payload for event in events], ensure_ascii=False)
    assert str(root) not in rendered
    assert str(workspace) not in rendered
    assert "expected_source_digests" not in rendered
    assert "value = 2" not in rendered


def test_conversation_loop_feeds_skill_search_metadata_to_next_turn(tmp_path) -> None:
    skill_root = tmp_path / "skills"
    _write_test_skill(
        skill_root,
        "llm2docx",
        description="Use for Word report automation.",
        body="## Checklist\n- Inspect the Word document before editing.\n",
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "skills.search",
                    "arguments": {
                        "query": "docx",
                        "roots": [str(skill_root)],
                        "limit": 5,
                    },
                    "rationale": "Find a relevant local skill.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已找到可用 skill。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="处理 Word 文档。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["capacity_id"] == "skills.search"
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "skill_search_result" in second_prompt
    assert "llm2docx" in second_prompt
    assert "Use for Word report automation." in second_prompt
    assert "## Checklist" not in second_prompt
    assert "Inspect the Word document before editing." not in second_prompt


def test_conversation_loop_feeds_described_skill_body_to_next_turn(tmp_path) -> None:
    skill_root = tmp_path / "skills"
    _write_test_skill(
        skill_root,
        "llm2docx",
        description="Use for Word report automation.",
        body="## Checklist\n- Inspect the Word document before editing.\n",
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "skills.describe",
                    "arguments": {
                        "skill_id": "llm2docx",
                        "roots": [str(skill_root)],
                        "max_body_chars": 2000,
                    },
                    "rationale": "Load the selected skill guide.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已加载 skill 指南。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="处理 Word 文档。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["capacity_id"] == "skills.describe"
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "skill_description" in second_prompt
    assert "llm2docx" in second_prompt
    assert "## Checklist" in second_prompt
    assert "Inspect the Word document before editing." in second_prompt


def _write_test_skill(
    root,
    name: str,
    *,
    description: str,
    body: str,
) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                body,
            ]
        ),
        encoding="utf-8",
    )


def test_conversation_loop_executes_screen_observe_capacity_with_generic_events(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import screen as screen_capability

    class StubScreenBackend:
        def run(self, request):
            return {
                "backend_session_id": "stub_screen_001",
                "status": "captured",
                "started_at": "2026-05-24T00:00:00Z",
                "finished_at": "2026-05-24T00:00:01Z",
                "summary": "screen observe captured",
                "output_artifacts": [
                    {
                        "artifact_type": "screen_metadata",
                        "summary": "screen metadata captured",
                        "content": json.dumps(
                            {
                                "matched_count": 1,
                                "selected_window_id": "window_001",
                                "selection_reason": "first_match",
                                "target": {
                                    "window_id": "window_001",
                                    "title": "Notes",
                                    "app": "notepad.exe",
                                    "is_minimized": False,
                                },
                            },
                            sort_keys=True,
                        ),
                    },
                    {
                        "artifact_type": "screen_screenshot",
                        "summary": "screen screenshot captured",
                        "content": json.dumps(
                            {
                                "encoding": "base64",
                                "media_type": "image/png",
                                "width": 64,
                                "height": 32,
                                "data": "ZmFrZS1pbWFnZS1ieXRlcw==",
                            },
                            sort_keys=True,
                        ),
                    },
                ],
                "reason_code": "screen_observe_captured",
                "retryable": False,
                "resource_usage": {"window_count": 1},
            }

    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        StubScreenBackend,
        raising=False,
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "screen.observe",
                    "arguments": {
                        "target_selector": {
                            "kind": "window",
                            "selector": {"app": "notepad.exe"},
                        },
                        "target_allowlist": {"allowed_apps": ["notepad.exe"]},
                    },
                    "rationale": "Observe the allowed target window.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已完成屏幕观察。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="看看记事本窗口。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "screen.observe"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result"]["agent_loop_tick_status"] == "executed"
    assert events[1].payload["result"]["agent_loop_screen_report_status"] == "ok"
    assert events[1].payload["result"]["agent_loop_screen_observe_status"] == "captured"
    assert events[1].payload["result"][
        "agent_loop_screen_screenshot_available"
    ] is True
    screen_artifact_details = [
        detail
        for detail in events[1].payload["details"]
        if detail["label"] == "Screen artifacts"
    ]
    assert screen_artifact_details
    assert screen_artifact_details[0]["content"]["artifacts"][1]["artifact_type"] == (
        "screen_screenshot"
    )
    assert screen_artifact_details[0]["content"]["artifacts"][1]["ref"]["artifact_id"].startswith(
        "artifact_"
    )
    assert events[2].payload["text"] == "已完成屏幕观察。"
    rendered_events = json.dumps(
        [event.payload for event in events],
        ensure_ascii=False,
    )
    assert "raw screenshot bytes" not in rendered_events
    second_messages = provider.calls[1]["messages"]
    second_prompt = json.dumps(second_messages, ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    image_urls = _message_image_urls(second_messages)
    assert image_urls == ["data:image/png;base64,ZmFrZS1pbWFnZS1ieXRlcw=="]
    assert "ZmFrZS1pbWFnZS1ieXRlcw==" not in rendered_events


def _message_image_urls(messages: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "image_url":
                continue
            image_url = block.get("image_url")
            if isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
                urls.append(image_url["url"])
    return urls
