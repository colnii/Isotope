from __future__ import annotations

import http.client
import json
import threading
from typing import Any

from isotope.features.supervisor.web import create_dashboard_server
from isotope.interfaces.http import create_http_app
from isotope.llm.provider import LLMResponse
from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore


class ProductChainProvider:
    provider = "deterministic_product_chain"
    model = "stub-product-chain"

    def __init__(self) -> None:
        self.responses = [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "memory.query",
                    "arguments": {
                        "query": "desktop product chain recall",
                        "run_id": "run_product_chain",
                    },
                    "rationale": "Need local memory before answering.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "我读到了 product chain memory。",
                    "rationale": "The capacity observation included the recalled record.",
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


def test_desktop_chat_capacity_result_can_feed_model_and_http_artifact_content(
    tmp_path,
) -> None:
    _seed_memory(tmp_path)
    provider = ProductChainProvider()
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
        {"question": "查一下 desktop product chain recall，然后回答。"},
    )

    assert response.status == 200
    events = _parse_sse(body)
    assert [event["event"] for event in events] == [
        "start",
        "capacity_start",
        "capacity_result",
        "delta",
        "done",
    ]
    capacity_result = events[2]["data"]
    assert capacity_result["capacity_id"] == "memory.query"
    assert capacity_result["status"] == "ok"
    assert "result" + "_summary" not in capacity_result
    assert capacity_result["result"]["agent_loop_memory_query_status"] == "ok"
    assert capacity_result["result"]["agent_loop_memory_query_result_count"] == 1
    memory_detail = _detail_content(capacity_result, "Memory query result")
    assert memory_detail["results"][0]["record_id"] == "mem_product_chain"
    assert (
        memory_detail["results"][0]["summary"]
        == "Product chain memory is reachable from desktop chat."
    )

    second_turn = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_turn
    assert "mem_product_chain" in second_turn
    assert "Product chain memory is reachable from desktop chat." in second_turn
    assert "Raw product chain memory content." not in second_turn
    assert "raw_response" not in second_turn

    artifact_id = capacity_result["result"]["agent_loop_artifact_id"]
    content_app = create_http_app(tmp_path / "supervisor" / "conversation-loop-runs")
    artifact_response = content_app.request("GET", f"/artifacts/{artifact_id}/content")

    assert artifact_response.status_code == 200
    artifact_body = artifact_response.json()
    assert artifact_body["status"] == "ok"
    artifact_content = json.loads(artifact_body["content"])
    memory_query = artifact_content["capability_run"]["memory_query"]
    assert memory_query["status"] == "ok"
    assert memory_query["results"][0]["record_id"] == "mem_product_chain"
    assert (
        memory_query["results"][0]["summary"]
        == "Product chain memory is reachable from desktop chat."
    )


def _seed_memory(root) -> None:
    FileMemoryStore(root).append_record(
        MemoryRecord(
            memory_id="mem_product_chain",
            scope="run",
            content={
                "kind": "structured_note",
                "text": "Raw product chain memory content.",
            },
            summary="Product chain memory is reachable from desktop chat.",
            source_refs=[
                {
                    "ref_type": "artifact",
                    "artifact_id": "artifact_product_chain_source",
                }
            ],
            provenance={
                "run_id": "run_product_chain",
                "execution_id": "exec_product_chain_seed",
                "action_type": "write_memory",
            },
            created_at="2026-06-04T00:00:00Z",
            supersedes=[],
            quality="verified",
        )
    )


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


def _detail_content(capacity_result: dict[str, Any], label: str) -> dict[str, Any]:
    matching = [
        detail
        for detail in capacity_result["details"]
        if detail["label"] == label
    ]
    assert len(matching) == 1
    assert matching[0]["kind"] == "json"
    return matching[0]["content"]


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
