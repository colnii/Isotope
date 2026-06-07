from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from isotope.capabilities import research as research_capability
from isotope.features.research.providers import (
    ResearchProviderError,
    build_research_provider,
)
from isotope.features.supervisor.web import create_dashboard_server
from isotope.llm.provider import LLMResponse


class ResearchDecisionProvider:
    provider = "deterministic_research_smoke"
    model = "desktop-research-smoke"

    def __init__(self, *, query: str) -> None:
        self.responses = [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "research.search",
                    "arguments": {"query": query},
                    "rationale": "用户要求搜索并总结。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "搜索能力已返回可见状态。",
                    "rationale": "基于 research.search observation 回答。",
                }
            ),
        ]
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, Any]],
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


class FailingCodexResearchProvider:
    provider_name = "codex_delegated"

    def run(self, query: str) -> dict[str, Any]:
        raise ResearchProviderError(
            "codex delegated research provider is not configured",
            details={
                "provider_id": "codex",
                "error_code": "codex_cli_not_configured",
                "retryable": False,
            },
            retryable=False,
        )


def test_desktop_chat_research_search_reports_default_codex_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from isotope.features.supervisor import conversation_loop

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(conversation_loop, "tavily_api_key_from_config", lambda: None)
    provider_calls: list[dict[str, Any]] = []

    def build_provider(provider_id: str, **kwargs: Any) -> FailingCodexResearchProvider:
        provider_calls.append({"provider_id": provider_id, **kwargs})
        return FailingCodexResearchProvider()

    monkeypatch.setattr(research_capability, "build_research_provider", build_provider)
    provider = ResearchDecisionProvider(query="desktop codex default failure")
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
    )

    response, body = _post_desktop_chat(
        server,
        {"question": "搜索 desktop codex default failure"},
    )

    assert response.status == 200
    events = _parse_sse(body)
    assert [event["event"] for event in events[:4]] == [
        "start",
        "capacity_start",
        "capacity_update",
        "capacity_result",
    ]
    assert events[-1]["event"] == "done"
    capacity_result = events[3]["data"]
    assert capacity_result["capacity_id"] == "research.search"
    assert capacity_result["title"] == "Research Search"
    assert capacity_result["status"] == "blocked"
    assert capacity_result["inputs"] == {
        "query": "desktop codex default failure",
        "root": str(tmp_path),
    }
    assert capacity_result["result"]["agent_loop_research_search_status"] == (
        "provider_failed"
    )
    assert capacity_result["result"]["agent_loop_research_error_code"] == (
        "research_provider_failed"
    )
    assert (
        capacity_result["result"]["agent_loop_research_error_message"]
        == "codex delegated research provider is not configured"
    )
    assert provider_calls == [{"provider_id": "codex", "workspace_root": str(tmp_path)}]
    second_turn = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "provider_failed" in second_turn
    assert "codex delegated research provider is not configured" in second_turn
    assert "raw_response" not in second_turn


def test_desktop_chat_research_search_uses_configured_tavily_internally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    provider_calls: list[dict[str, Any]] = []

    class RecordingTavilyResearchProvider:
        provider_name = "tavily"

        def run(self, query: str) -> dict[str, Any]:
            return {
                "research_id": "desktop_tavily_policy",
                "query": query,
                "provider": "tavily",
                "created_at": "2026-06-04T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Tavily desktop source",
                        "url": "https://example.com/desktop-tavily",
                        "snippet": "Desktop chat used Tavily internally.",
                        "why_used": "integration test Tavily provider",
                        "retrieved_at": "2026-06-04T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Desktop chat Tavily summary.",
                    "claims": [
                        {
                            "text": "Desktop chat used Tavily internally.",
                            "source_ids": ["src_001"],
                            "confidence": "medium",
                        }
                    ],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "tavily"},
            }

    def build_provider(
        provider_id: str,
        **kwargs: Any,
    ) -> RecordingTavilyResearchProvider:
        provider_calls.append({"provider_id": provider_id, **kwargs})
        return RecordingTavilyResearchProvider()

    monkeypatch.setattr(research_capability, "build_research_provider", build_provider)
    provider = ResearchDecisionProvider(query="desktop tavily configured policy")
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
    )

    response, body = _post_desktop_chat(
        server,
        {"question": "搜索 desktop tavily configured policy"},
    )

    assert response.status == 200
    events = _parse_sse(body)
    assert [event["event"] for event in events[:4]] == [
        "start",
        "capacity_start",
        "capacity_update",
        "capacity_result",
    ]
    assert events[-1]["event"] == "done"
    capacity_start = events[1]["data"]
    assert capacity_start["inputs"] == {
        "query": "desktop tavily configured policy",
        "root": str(tmp_path),
    }
    capacity_result = events[3]["data"]
    assert capacity_result["status"] == "ok"
    assert capacity_result["result"]["agent_loop_research_provider"] == "tavily"
    assert provider_calls == [
        {
            "provider_id": "tavily",
            "workspace_root": str(tmp_path),
            "tavily_enable_network": True,
        }
    ]


def test_research_runtime_private_tavily_readiness_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        lambda provider_id, **kwargs: build_research_provider(
            provider_id,
            tavily_config_path=tmp_path / "missing_research_tavily.toml",
            **kwargs,
        ),
    )

    result = research_capability.run_research_search(
        inputs={
            "root": str(tmp_path),
            "query": "desktop tavily readiness failure",
            "provider": "tavily",
        }
    )

    research_search = result["research_search"]
    assert research_search["status"] == "provider_failed"
    assert research_search["provider"] == "tavily"
    assert research_search["error"] == {
        "code": "research_provider_failed",
        "message": "tavily provider requires TAVILY_API_KEY",
        "retryable": False,
    }
    assert [artifact["artifact_type"] for artifact in research_search["artifacts"]] == [
        "research.provider_trace"
    ]


def test_research_runtime_private_tavily_exact_url_writes_artifacts(
    tmp_path: Path,
    local_research_url: str,
) -> None:
    result = research_capability.run_research_search(
        inputs={
            "root": str(tmp_path),
            "query": local_research_url,
            "provider": "tavily",
            "allow_network": True,
        }
    )

    research_search = result["research_search"]
    assert research_search["status"] == "ok"
    assert research_search["provider"] == "tavily"
    assert research_search["source_count"] == 1
    assert "Local desktop research content" in research_search["report_summary"]
    assert [artifact["artifact_type"] for artifact in research_search["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]
    report_artifact = research_search["artifacts"][1]
    assert report_artifact["summary"] == (
        f"Research report for {local_research_url}: "
        f"{research_search['report_summary']}"
    )


@pytest.fixture
def local_research_url() -> str:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = (
                "<html><head><title>Desktop Research Fixture</title></head>"
                "<body><main><h1>Desktop Research Fixture</h1>"
                "<p>Local desktop research content for source-backed artifacts.</p>"
                "</main></body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/research"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
