from __future__ import annotations

import http.client
import json
import time
import threading
from typing import Any

import pytest

from isotope.capabilities.runner import CapabilityRunner
from isotope.features.supervisor.desktop_chat import (
    stream_desktop_chat,
    stream_desktop_chat_events,
)
from isotope.features.supervisor.planner.goal_queue import record_supervisor_goal
from isotope.features.supervisor.web import create_dashboard_server
from isotope.llm.provider import LLMResponse, LLMStreamChunk


class RecordingDesktopChatProvider:
    provider = "deterministic_test"
    model = "stub-desktop-chat"

    def __init__(self, content: str = "loop 正在监督 worker。") -> None:
        self.content = content
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
            content=self.content,
            finish_reason="stop",
            usage={"prompt_tokens": 21, "completion_tokens": 7},
            raw={"id": "stub"},
        )


class StreamingDesktopChatProvider(RecordingDesktopChatProvider):
    provider = "stub-stream"
    model = "stub-stream-chat"

    def __init__(self, chunks: tuple[str, ...] = ("loop ", "正在推进。")) -> None:
        super().__init__(content="")
        self.chunks = chunks

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        raise AssertionError("desktop chat should use provider streaming")

    def stream_generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        for chunk in self.chunks:
            yield LLMStreamChunk(
                provider=self.provider,
                model=self.model,
                content=chunk,
                raw={"id": "stub-stream"},
            )


class SlowDesktopChatProvider(RecordingDesktopChatProvider):
    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        time.sleep(0.2)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.content,
            finish_reason="stop",
            usage={},
            raw={},
        )


class RecordingCapacityProvider:
    provider = "stub-capacity"
    model = "stub-capacity-model"

    def __init__(
        self,
        content: str = (
            '{"capacity_id":"artifact.review","arguments":{},'
            '"confidence":0.9,"rationale":"需要查看 artifact 能力"}'
        ),
    ) -> None:
        self.content = content
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
            content=self.content,
            finish_reason="stop",
            usage={"prompt_tokens": 13, "completion_tokens": 5},
            raw={"id": "stub-capacity"},
        )


class SlowCapacityProvider(RecordingCapacityProvider):
    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        time.sleep(0.2)
        return super().generate(messages, max_tokens=max_tokens)


class MultiResponseDesktopChatProvider(RecordingDesktopChatProvider):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(content="")
        self.responses = list(responses)

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
            usage={},
            raw={"raw_response": "must not leak"},
        )


class StreamingCapableDecisionProvider(MultiResponseDesktopChatProvider):
    def stream_generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ):
        raise AssertionError("desktop chat should route default providers through conversation loop")


class DesktopChatGoalPlanProvider:
    def __init__(self, expected_goal: str) -> None:
        self.expected_goal = expected_goal

    def summarize(self, messages: list[dict[str, str]]) -> str:
        user_payload = json.loads(messages[1]["content"])
        assert user_payload["user_goal"] == self.expected_goal
        assert user_payload["planning_trigger"] == "capacity"
        return json.dumps(
            {
                "plan_summary": "desktop chat 通过 goal_plan capacity 生成目标规划。",
                "goals": [
                    {
                        "goal": "让 desktop chat 调用 supervisor.goal_plan。",
                        "target_name": "desktop-chat-goal-plan",
                        "reason": "用户在 chat 中要求目标规划。",
                    }
                ],
            },
            ensure_ascii=False,
        )


def _write_goal_planning_docs(root) -> None:
    docs = root / "docs" / "current"
    docs.mkdir(parents=True)
    (docs / "status.md").write_text("desktop chat 需要调用目标规划。\n", encoding="utf-8")
    (docs / "agent-task-queue.md").write_text("supervisor.goal_plan 已接入 capacity。\n", encoding="utf-8")
    (docs / "supervisor-capability-map.md").write_text(
        "chat 可以通过 capacity 执行目标规划。\n",
        encoding="utf-8",
    )


def test_desktop_chat_endpoint_streams_real_backend_answer_without_json_result(
    tmp_path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    record_supervisor_goal(
        codex_home=tmp_path,
        goal="检查当前 loop 效果",
        cwd=workspace,
        target_name="loop-check",
    )
    provider = RecordingDesktopChatProvider()
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/desktop/chat",
            body=json.dumps({"question": "loop 现在怎样？"}),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert response.getheader("content-type") == "text/event-stream; charset=utf-8"
    assert response.getheader("access-control-allow-origin") == "*"
    events = _parse_sse(body)
    assert events[0]["event"] == "start"
    assert events[-1]["event"] == "done"
    assert [event["event"] for event in events[1:-1]]
    assert set(event["event"] for event in events[1:-1]) == {"delta"}
    assert "".join(
        event["data"].get("text", "")
        for event in events
        if event["event"] == "delta"
    ) == "loop 正在监督 worker。"
    assert events[-1]["data"] == {
        "status": "ok",
        "provider": "deterministic_test",
        "model": "stub-desktop-chat",
    }
    assert "context" not in body
    assert "messages" not in body
    assert "raw" not in body

    messages = provider.calls[0]["messages"]
    system_prompt = messages[0]["content"]
    assert "产品对话决策层" in system_prompt
    assert "只输出一个低敏 JSON object" in system_prompt
    assert "capacity_manifest" in system_prompt
    assert "supervisor_context" not in system_prompt
    assert "desktop_snapshot" not in system_prompt
    assert "desktop_context" not in system_prompt
    assert "output_requirements" not in system_prompt

    assert messages[1] == {"role": "user", "content": "loop 现在怎样？"}
    assert "检查当前 loop 效果" not in json.dumps(messages, ensure_ascii=False)
    assert "active_goals" not in json.dumps(messages, ensure_ascii=False)
    assert "notifications" not in json.dumps(messages, ensure_ascii=False)

    capacity_manifest = _system_json_section(system_prompt, "capacity_manifest")
    assert capacity_manifest["source"] == "registered_capabilities"
    capacity_ids = [item["capability_id"] for item in capacity_manifest["capabilities"]]
    assert capacity_manifest["capability_count"] == len(capacity_ids)
    assert "supervisor.codex_operation" in capacity_ids
    assert "coding_task.execute" in capacity_ids
    codex_operation = next(
        item
        for item in capacity_manifest["capabilities"]
        if item["capability_id"] == "supervisor.codex_operation"
    )
    assert codex_operation["required_inputs"] == ["operation", "state_root"]
    assert codex_operation["operations"] == [
        "request_context",
        "worker_review",
        "integration_review",
        "launch_worker",
        "resume_worker",
    ]
    assert provider.calls[0]["max_tokens"] == 512


def test_desktop_chat_endpoint_streams_capacity_events_before_answer(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(content="我查到了能力调用结果。")
    capacity_provider = RecordingCapacityProvider()
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
        desktop_chat_capacity_provider=capacity_provider,
    )

    response, body = _post_desktop_chat(
        server,
        {"question": "用 capacity 看一下当前上下文。"},
    )

    assert response.status == 200
    events = _parse_sse(body)
    names = [event["event"] for event in events]
    assert names[0] == "start"
    assert "capacity_start" in names
    assert "capacity_result" in names
    assert names.index("capacity_start") < names.index("delta")
    assert names.index("capacity_result") < names.index("delta")
    assert names[-1] == "done"
    capacity_start = next(
        event["data"] for event in events if event["event"] == "capacity_start"
    )
    assert capacity_start == {
        "id": "capacity_artifact_review",
        "capacity_id": "artifact.review",
        "title": "Artifact Review",
        "status": "running",
        "input_summary": {},
        "result_summary": {},
        "details": [
            {
                "label": "输入",
                "kind": "json",
                "content": {},
            }
        ],
    }
    capacity_result = next(
        event["data"] for event in events if event["event"] == "capacity_result"
    )
    assert capacity_result["id"] == "capacity_artifact_review"
    assert capacity_result["capacity_id"] == "artifact.review"
    assert capacity_result["title"] == "Artifact Review"
    assert capacity_result["status"] == "ok"
    assert capacity_result["result_summary"]["agent_loop_tick_status"] == "executed"
    assert any(section["label"] == "结果摘要" for section in capacity_result["details"])
    assert "我查到了能力调用结果。" == "".join(
        event["data"].get("text", "")
        for event in events
        if event["event"] == "delta"
    )
    assert "raw" not in body
    assert "messages" not in body
    assert capacity_provider.calls[0]["max_tokens"] == 512
    messages = provider.calls[0]["messages"]
    assert messages[-1] == {"role": "user", "content": "用 capacity 看一下当前上下文。"}
    capacity_context = _system_json_section(messages[1]["content"], "capacity_result")
    capacity_call = capacity_context["result"]
    assert capacity_call["capacity_id"] == "artifact.review"
    assert capacity_call["status"] == "ok"


def test_desktop_chat_endpoint_skips_capacity_for_plain_greeting(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(content="你好，我在。")
    capacity_provider = RecordingCapacityProvider(
        json.dumps(
            {
                "capacity_id": None,
                "arguments": {},
                "confidence": 0.91,
                "rationale": "普通问候不需要能力调用。",
            }
        )
    )
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
        desktop_chat_capacity_provider=capacity_provider,
    )

    response, body = _post_desktop_chat(server, {"question": "你好"})

    assert response.status == 200
    events = _parse_sse(body)
    assert [event["event"] for event in events] == ["start", "delta", "done"]
    assert events[1]["data"]["text"] == "你好，我在。"
    assert len(capacity_provider.calls) == 1


def test_desktop_chat_stream_skips_slow_capacity_selection_and_answers(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(content="我先直接回答。")
    capacity_provider = SlowCapacityProvider()

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="用 capacity 看一下当前上下文。",
            provider=provider,
            capacity_provider=capacity_provider,
            capacity_timeout_seconds=0.01,
        )
    )

    assert [event.event for event in events] == ["delta"]
    assert events[0].payload == {"text": "我先直接回答。"}
    assert capacity_provider.calls


def test_desktop_chat_stream_uses_conversation_loop_for_model_capacity_choice(
    tmp_path,
) -> None:
    provider = MultiResponseDesktopChatProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "artifact.review",
                    "arguments": {},
                    "rationale": "用户要求能力执行。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已经通过 Supervisor agent loop 执行 capability。",
                }
            ),
        ]
    )

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="调用 artifact review capacity。",
            provider=provider,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["result_summary"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload["text"] == "已经通过 Supervisor agent loop 执行 capability。"
    assert len(provider.calls) == 2


def test_desktop_chat_endpoint_can_call_goal_plan_capacity(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import supervisor_goal_plan

    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_goal_planning_docs(workspace)
    question = "帮我规划下一步目标"
    monkeypatch.chdir(workspace)
    monkeypatch.setattr(
        supervisor_goal_plan,
        "resolve_summary_provider_from_env",
        lambda **_: DesktopChatGoalPlanProvider(question),
    )
    provider = MultiResponseDesktopChatProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.goal_plan",
                    "arguments": {"goal": question},
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
    server = create_dashboard_server(
        codex_home=tmp_path / "state",
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/desktop/chat",
            body=json.dumps({"question": question}),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    events = _parse_sse(body)
    names = [event["event"] for event in events]
    assert names[:4] == ["start", "capacity_start", "capacity_result", "delta"]
    assert events[1]["data"]["capacity_id"] == "supervisor.goal_plan"
    assert events[2]["data"]["capacity_id"] == "supervisor.goal_plan"
    assert events[2]["data"]["status"] == "ok"
    assert events[3]["data"]["text"] == "已通过目标规划 capacity 生成候选目标。"
    assert len(provider.calls) == 2


def test_desktop_chat_stream_projects_research_search_artifacts(
    tmp_path,
    monkeypatch,
) -> None:
    from isotope.capabilities import research as research_capability

    class RecordingCodexProvider:
        provider_name = "codex_delegated"

        def run(self, query: str) -> dict[str, Any]:
            return {
                "research_id": "research_desktop_chat",
                "query": query,
                "provider": "codex_delegated",
                "created_at": "2026-06-03T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Research source",
                        "url": "https://example.com/research",
                        "snippet": "Research source-backed result.",
                        "why_used": "integration test source",
                        "retrieved_at": "2026-06-03T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Research report summary for desktop chat.",
                    "claims": [
                        {
                            "text": "Research source-backed result.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
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
    provider = MultiResponseDesktopChatProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {"query": "desktop chat research"},
                    "rationale": "用户要求搜索并总结。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已完成搜索并写入 research artifacts。",
                }
            ),
        ]
    )

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="搜索 desktop chat research",
            provider=provider,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    capacity_result = events[1].payload
    assert capacity_result["capacity_id"] == "research.search"
    assert capacity_result["title"] == "Research Search"
    assert capacity_result["status"] == "ok"
    assert capacity_result["input_summary"] == {
        "query": "desktop chat research",
        "root": str(tmp_path),
    }
    assert capacity_result["result_summary"]["agent_loop_research_provider"] == (
        "codex_delegated"
    )
    assert (
        capacity_result["result_summary"]["agent_loop_research_report_summary"]
        == "Research report summary for desktop chat."
    )
    artifact_details = [
        section
        for section in capacity_result["details"]
        if section["label"] == "Research artifacts"
    ]
    assert len(artifact_details) == 1
    assert artifact_details[0]["label"] == "Research artifacts"
    assert artifact_details[0]["kind"] == "json"
    artifacts = artifact_details[0]["content"]["artifacts"]
    assert [artifact["artifact_type"] for artifact in artifacts] == [
        "research.raw_transcript",
        "research.report",
    ]
    assert [artifact["summary"] for artifact in artifacts] == [
        "raw research provider output: desktop chat research",
        "Research report summary for desktop chat.",
    ]
    assert artifacts[0]["run_id"] == artifacts[1]["run_id"]
    for artifact in artifacts:
        assert artifact["artifact_id"].startswith("artifact_")
        assert artifact["run_id"].startswith("run_")
        assert artifact["ref"] == {
            "ref_type": "artifact",
            "scope": "run",
            "run_id": artifact["run_id"],
            "artifact_id": artifact["artifact_id"],
        }
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "Research report summary for desktop chat." in second_prompt
    assert "Research source-backed result." in second_prompt
    assert "raw_output" not in second_prompt
    assert events[2].payload["text"] == "已完成搜索并写入 research artifacts。"


def test_desktop_chat_stream_can_answer_from_project_status_capacity(
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
    provider = MultiResponseDesktopChatProvider(
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
                    "answer": "Desktop chat golden path 正在推进。",
                }
            ),
        ]
    )

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="项目现在什么状态？",
            provider=provider,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "supervisor.project_status"
    assert events[1].payload["result_summary"]["agent_loop_project_status_status"] == (
        "completed"
    )
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "project_state_summary" in second_prompt
    assert "把 Desktop chat 打成黄金路径" in second_prompt
    assert events[2].payload["text"] == "Desktop chat golden path 正在推进。"


def test_desktop_chat_stream_uses_conversation_loop_for_streaming_capable_provider(
    tmp_path,
) -> None:
    provider = StreamingCapableDecisionProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "artifact.review",
                    "arguments": {},
                    "rationale": "用户要求能力执行。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "streaming-capable provider 也走了 capacity loop。",
                }
            ),
        ]
    )

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="调用 artifact review capacity。",
            provider=provider,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["capacity_id"] == "artifact.review"
    assert events[2].payload["text"] == "streaming-capable provider 也走了 capacity loop。"


def test_desktop_chat_stream_times_out_slow_answer_provider(tmp_path) -> None:
    provider = SlowDesktopChatProvider(content="太晚了")

    with pytest.raises(TimeoutError, match="desktop chat response timed out"):
        list(
            stream_desktop_chat_events(
                state_root=tmp_path,
                question="你好",
                provider=provider,
                chat_timeout_seconds=0.01,
            )
        )

    assert provider.calls


def test_desktop_chat_endpoint_sends_developer_capacity_question_to_llm_with_context(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(content="我会按上下文列出 capacity。")
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/desktop/chat",
            body=json.dumps({"question": "直接给我们的接收list，我是开发者"}),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    events = _parse_sse(body)
    assert events[0]["event"] == "start"
    assert events[-1]["event"] == "done"
    answer = "".join(
        event["data"].get("text", "")
        for event in events
        if event["event"] == "delta"
    )
    assert answer == "我会按上下文列出 capacity。"
    assert events[-1]["data"] == {
        "status": "ok",
        "provider": "deterministic_test",
        "model": "stub-desktop-chat",
    }
    messages = provider.calls[0]["messages"]
    assert messages[1] == {"role": "user", "content": "直接给我们的接收list，我是开发者"}
    system_prompt = messages[0]["content"]
    assert "desktop_snapshot" not in system_prompt
    assert "desktop_context" not in system_prompt
    assert "output_requirements" not in system_prompt
    capacity_manifest = _system_json_section(system_prompt, "capacity_manifest")
    capacity_ids = [
        item["capability_id"]
        for item in capacity_manifest["capabilities"]
    ]
    assert capacity_manifest["capability_count"] == len(capacity_ids)
    assert "supervisor.codex_operation" in capacity_ids


def test_desktop_chat_endpoint_includes_session_history_before_current_question(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(content="你的上句话是：之前跑过的 screen run？")
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/desktop/chat",
            body=json.dumps(
                {
                    "question": "我的上句话是什么",
                    "history": [
                        {"role": "user", "content": "之前跑过的 screen run？"},
                        {"role": "assistant", "content": "需要 root 和 run_id。"},
                    ],
                }
            ),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    events = _parse_sse(body)
    assert events[0]["event"] == "start"
    assert events[-1]["event"] == "done"
    messages = provider.calls[0]["messages"]
    assert messages[1:] == [
        {"role": "user", "content": "之前跑过的 screen run？"},
        {"role": "assistant", "content": "需要 root 和 run_id。"},
        {"role": "user", "content": "我的上句话是什么"},
    ]


def test_desktop_chat_keeps_full_history_message_when_context_fits(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(content="我保留了完整历史。")
    long_message = "FULL_HISTORY_MARKER:" + ("0123456789" * 430)

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="刚才那条长消息是什么？",
            provider=provider,
            history=[{"role": "user", "content": long_message}],
        )
    )

    assert [event.event for event in events] == ["delta"]
    messages = provider.calls[0]["messages"]
    assert messages[1] == {"role": "user", "content": long_message}
    assert len(messages[1]["content"]) > 4000


def test_desktop_chat_compacts_oversized_history_instead_of_dropping_old_turns(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(content="我看到了压缩上下文。")
    history = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"HISTORY_MARKER_{index:02d} " + ("长上下文 " * 900),
        }
        for index in range(16)
    ]

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="最早的上下文还在吗？",
            provider=provider,
            history=history,
        )
    )

    assert [event.event for event in events] == ["delta"]
    messages = provider.calls[0]["messages"]
    summary = messages[1]
    assert summary["role"] == "system"
    assert "desktop_chat_history_compaction" in summary["content"]
    assert "HISTORY_MARKER_00" in summary["content"]
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "HISTORY_MARKER_15" in rendered
    assert messages[-1] == {"role": "user", "content": "最早的上下文还在吗？"}


def test_stream_desktop_chat_helper_streams_provider_deltas(tmp_path) -> None:
    provider = StreamingDesktopChatProvider(chunks=("loop ", "实时", "返回。"))
    chunks = list(
        stream_desktop_chat(
            state_root=tmp_path,
            question="loop 现在怎样？",
            provider=provider,
        )
    )

    assert [chunk.content for chunk in chunks] == ["loop ", "实时", "返回。"]
    assert chunks[-1].provider == "stub-stream"
    assert chunks[-1].model == "stub-stream-chat"
    assert provider.calls[0]["max_tokens"] == 512


def test_desktop_chat_endpoint_rejects_empty_question(tmp_path) -> None:
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=RecordingDesktopChatProvider(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/desktop/chat",
            body=json.dumps({"question": "   "}),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 400
    assert payload["status"] == "error"
    assert payload["error"]["message"] == "question must not be empty"


def test_desktop_chat_endpoint_allows_browser_readiness_check(tmp_path) -> None:
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=RecordingDesktopChatProvider(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "OPTIONS",
            "/desktop/chat",
            headers={
                "origin": "http://127.0.0.1:5173",
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            },
        )
        response = conn.getresponse()
        response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 204
    assert response.getheader("access-control-allow-origin") == "*"
    assert "POST" in response.getheader("access-control-allow-methods")
    assert "content-type" in response.getheader("access-control-allow-headers")


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event_line = next(line for line in lines if line.startswith("event: "))
        data_line = next(line for line in lines if line.startswith("data: "))
        events.append(
            {
                "event": event_line.removeprefix("event: "),
                "data": json.loads(data_line.removeprefix("data: ")),
            }
        )
    return events


def _system_json_section(content: str, label: str) -> dict[str, Any]:
    prefix = label + ":\n"
    start = content.index(prefix) + len(prefix)
    return json.loads(content[start:])


def _post_desktop_chat(
    server: Any,
    payload: dict[str, Any],
) -> tuple[http.client.HTTPResponse, str]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/desktop/chat",
            body=json.dumps(payload),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return response, body
