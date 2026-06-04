from __future__ import annotations

import http.client
import json
import threading
from typing import Any

from isotope.features.supervisor.web import create_dashboard_server
from isotope.llm.provider import LLMResponse


class ScreenObserveDecisionProvider:
    provider = "fixture-screen-smoke"
    model = "fixture-screen-smoke-model"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses = [
            {
                "kind": "call_capability",
                "capacity_id": "screen.observe",
                "arguments": {
                    "target_selector": {
                        "kind": "window",
                        "selector": {"app": "notepad.exe"},
                    },
                    "target_allowlist": {"allowed_apps": ["notepad.exe"]},
                    "capture": ["metadata", "screenshot"],
                },
                "rationale": "需要通过屏幕能力观察目标窗口。",
            },
            {
                "kind": "direct_answer",
                "answer": "已读取屏幕原图 artifact。",
            },
        ]

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
            content=json.dumps(self.responses.pop(0), ensure_ascii=False),
            finish_reason="stop",
            usage={},
            raw={},
        )


class FixtureScreenBackend:
    def run(self, request: Any) -> dict[str, Any]:
        return {
            "backend_session_id": "fixture_screen_001",
            "status": "captured",
            "started_at": "2026-06-04T00:00:00Z",
            "finished_at": "2026-06-04T00:00:01Z",
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
                            "width": 1920,
                            "height": 1080,
                            "data": "ZmFrZS1mdWxsLXBuZw==",
                        },
                        sort_keys=True,
                    ),
                },
            ],
            "reason_code": "screen_observe_captured",
            "retryable": False,
            "resource_usage": {"window_count": 1},
        }


def test_desktop_chat_screen_observe_original_image_endpoint_smoke(tmp_path, monkeypatch):
    from isotope.capabilities import screen as screen_capability

    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        FixtureScreenBackend,
        raising=False,
    )
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=ScreenObserveDecisionProvider(),
    )

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        chat_response, chat_body = _post_desktop_chat(
            server,
            {"question": "观察记事本窗口，并确认我能打开原图。"},
        )

        assert chat_response.status == 200
        events = _parse_sse(chat_body)
        assert [event["event"] for event in events] == [
            "start",
            "capacity_start",
            "capacity_result",
            "delta",
            "done",
        ]
        capacity_result = events[2]["data"]
        assert capacity_result["capacity_id"] == "screen.observe"
        assert capacity_result["status"] == "ok"
        assert capacity_result["result_summary"][
            "agent_loop_screen_screenshot_available"
        ] is True
        rendered_events = json.dumps(events, ensure_ascii=False)
        assert "ZmFrZS1mdWxsLXBuZw==" not in rendered_events

        screen_artifacts = next(
            detail
            for detail in capacity_result["details"]
            if detail["label"] == "Screen artifacts"
        )
        screenshot = next(
            artifact
            for artifact in screen_artifacts["content"]["artifacts"]
            if artifact["artifact_type"] == "screen_screenshot"
        )
        artifact_id = screenshot["ref"]["artifact_id"]

        content_response, content_payload = _get_screen_artifact_content(
            server,
            artifact_id,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert content_response.status == 200
    assert content_payload["status"] == "ok"
    assert content_payload["artifact"]["artifactType"] == "screen_screenshot"
    assert content_payload["artifact"]["ref"]["artifact_id"] == artifact_id
    assert content_payload["image"] == {
        "mediaType": "image/png",
        "width": 1920,
        "height": 1080,
        "data": "ZmFrZS1mdWxsLXBuZw==",
        "dataUrl": "data:image/png;base64,ZmFrZS1mdWxsLXBuZw==",
    }
    assert content_payload["file"]["path"].endswith(f"/artifacts/{artifact_id}.json")
    assert content_payload["file"]["directory"].endswith("/artifacts")
    assert content_payload["file"]["downloadFilename"] == f"{artifact_id}.png"


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


def _post_desktop_chat(
    server: Any,
    payload: dict[str, Any],
) -> tuple[http.client.HTTPResponse, str]:
    host, port = server.server_address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request(
        "POST",
        "/desktop/chat",
        body=json.dumps(payload),
        headers={"content-type": "application/json"},
    )
    response = conn.getresponse()
    body = response.read().decode("utf-8")
    return response, body


def _get_screen_artifact_content(
    server: Any,
    artifact_id: str,
) -> tuple[http.client.HTTPResponse, dict[str, Any]]:
    host, port = server.server_address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", f"/desktop/artifacts/{artifact_id}/screen-content")
    response = conn.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    return response, payload
