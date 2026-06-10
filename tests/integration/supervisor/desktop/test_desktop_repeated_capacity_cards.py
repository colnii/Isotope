from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from isotope.capabilities import research as research_capability
from isotope.features.research.providers import ResearchProviderError
from isotope.features.supervisor.web import create_dashboard_server
from isotope.llm.provider import LLMResponse


class ParallelResearchDecisionProvider:
    provider = "deterministic_parallel_research_smoke"
    model = "desktop-parallel-research-smoke"

    def __init__(self) -> None:
        self.responses = [
            json.dumps(
                {
                    "kind": "call_capabilities",
                    "calls": [
                        {
                            "capacity_id": "research.search",
                            "arguments": {"query": "desktop research first failure"},
                            "rationale": "Try the first search.",
                        },
                        {
                            "capacity_id": "research.search",
                            "arguments": {"query": "desktop research second success"},
                            "rationale": "Try the second search.",
                        },
                    ],
                    "rationale": "Run related searches in parallel.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "Parallel research returned.",
                    "rationale": "Answer from research.search observations.",
                }
            ),
        ]

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.responses.pop(0),
            finish_reason="stop",
            usage={},
            raw={},
        )


def test_desktop_chat_preserves_repeated_capacity_cards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")

    class MixedTavilyResearchProvider:
        provider_name = "tavily"

        def run(self, query: str) -> dict[str, Any]:
            if query == "desktop research first failure":
                raise ResearchProviderError(
                    "tavily request failed",
                    details={
                        "provider_id": "tavily",
                        "error_code": "network_error",
                        "retryable": True,
                    },
                    retryable=True,
                )
            return {
                "research_id": "desktop_parallel_success",
                "query": query,
                "provider": "tavily",
                "created_at": "2026-06-11T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [
                    {
                        "source_id": "src_001",
                        "title": "Parallel desktop source",
                        "url": "https://example.com/parallel-desktop",
                        "snippet": "Second parallel search succeeded.",
                        "why_used": "integration test Tavily provider",
                        "retrieved_at": "2026-06-11T00:00:00Z",
                    }
                ],
                "report": {
                    "summary": "Second parallel search summary.",
                    "claims": [],
                    "limitations": [],
                    "next_queries": [],
                },
                "provenance": {"provider": "tavily"},
            }

    monkeypatch.setattr(
        research_capability,
        "build_research_provider",
        lambda *args, **kwargs: MixedTavilyResearchProvider(),
    )
    provider = ParallelResearchDecisionProvider()
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
        {"question": "Run parallel searches and keep each record."},
    )

    assert response.status == 200
    events = _parse_sse(body)
    capacity_starts = [
        event["data"] for event in events if event["event"] == "capacity_start"
    ]
    capacity_results = [
        event["data"] for event in events if event["event"] == "capacity_result"
    ]
    assert len(capacity_starts) == 2
    assert len(capacity_results) == 2
    assert len({event["id"] for event in capacity_starts}) == 2
    assert {event["id"] for event in capacity_starts} == {
        event["id"] for event in capacity_results
    }
    assert {event["status"] for event in capacity_results} == {"blocked", "ok"}
    assert {event["inputs"]["query"] for event in capacity_results} == {
        "desktop research first failure",
        "desktop research second success",
    }


def _post_desktop_chat(
    server: ThreadingHTTPServer,
    payload: dict[str, Any],
) -> tuple[http.client.HTTPResponse, str]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_address[1],
            timeout=5,
        )
        conn.request(
            "POST",
            "/desktop/chat",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        conn.close()
        return response, body
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            if line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))
        events.append(
            {
                "event": event_name,
                "data": json.loads("\n".join(data_lines)),
            }
        )
    return events
