from __future__ import annotations

import http.client
import json
import time
import threading
from typing import Any

import pytest

from isotope.capabilities.runner import CapabilityRunner
from isotope.features.supervisor.desktop_chat import stream_desktop_chat_events
from isotope.features.supervisor.planner.goal_queue import record_supervisor_goal
from isotope.features.supervisor.web import create_dashboard_server
from isotope.llm.provider import LLMResponse, LLMStreamChunk


class RecordingDesktopChatProvider:
    provider = "fake"
    model = "fake-desktop-chat"

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
            raw={"id": "fake"},
        )


class StreamingDesktopChatProvider(RecordingDesktopChatProvider):
    provider = "fake-stream"
    model = "fake-stream-chat"

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
                raw={"id": "fake-stream"},
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
    provider = "fake-capacity"
    model = "fake-capacity-model"

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
            raw={"id": "fake-capacity"},
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
        "provider": "fake",
        "model": "fake-desktop-chat",
    }
    assert "context" not in body
    assert "messages" not in body
    assert "raw" not in body

    messages = provider.calls[0]["messages"]
    system_prompt = messages[0]["content"]
    assert "产品内 AI 助手" in system_prompt
    assert "正在开发和调试 Isotope" in system_prompt
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
                "label": "Inputs",
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
    assert any(section["label"] == "Result summary" for section in capacity_result["details"])
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
        "provider": "fake",
        "model": "fake-desktop-chat",
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


def test_desktop_chat_endpoint_streams_provider_deltas(tmp_path) -> None:
    provider = StreamingDesktopChatProvider(chunks=("loop ", "实时", "返回。"))
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
    events = _parse_sse(body)
    assert [event["data"]["text"] for event in events if event["event"] == "delta"] == [
        "loop ",
        "实时",
        "返回。",
    ]
    assert events[-1]["data"] == {
        "status": "ok",
        "provider": "fake-stream",
        "model": "fake-stream-chat",
    }
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


def test_desktop_chat_endpoint_allows_browser_preflight(tmp_path) -> None:
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
