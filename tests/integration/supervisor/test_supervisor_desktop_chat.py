from __future__ import annotations

import http.client
import json
import threading
from typing import Any

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

    prompt_payload = json.loads(provider.calls[0]["messages"][1]["content"])
    assert prompt_payload["question"] == "loop 现在怎样？"
    assert prompt_payload["desktop_snapshot"]["activeGoal"]["title"] == "检查当前 loop 效果"
    assert provider.calls[0]["max_tokens"] == 512


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
