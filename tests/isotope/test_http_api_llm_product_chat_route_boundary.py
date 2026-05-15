from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import isotope.integrations.codex.server as codex_server
from isotope.interfaces.http import create_http_app, create_llm_provider_http_app
from isotope.llm.provider import LLMToolCall, LLMToolCallResponse


class FakeCompletedProcess:
    returncode = 0
    stdout = '{"event":"task_complete","secret":"PRODUCT_CHAT_STDOUT_SHOULD_NOT_LEAK"}\n'
    stderr = ""


class RecordingProcessRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return FakeCompletedProcess()


class RecordingToolProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        self.calls.append({"messages": list(messages), "tools": list(tools), "max_tokens": max_tokens})
        return LLMToolCallResponse(
            provider=self.provider,
            model=self.model,
            finish_reason="tool_calls",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            tool_call=LLMToolCall(
                call_id="call_product_chat_should_not_run",
                tool_name="codex_task",
                arguments={"prompt": "PRODUCT_CHAT_PROMPT_SHOULD_NOT_LEAK"},
            ),
        )


def _request(app, method: str, path: str, json_body: Any = None):
    return app.request(method, path, json=json_body)


def _status_code(response) -> int:
    if isinstance(response, Mapping):
        return int(response["status_code"])
    return int(response.status_code)


def _body(response) -> dict[str, Any]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, dict)
    return body


def _create_run(app) -> str:
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="product chat route boundary")
    return run["run_id"]


def _chat_route(run_id: str) -> str:
    return f"/runs/{run_id}/llm/chat-turns"


def _chat_body() -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": "You are a product chat shell."},
            {"role": "user", "content": "PRODUCT_CHAT_MESSAGE_SHOULD_NOT_LEAK"},
        ],
        "max_tool_steps": 2,
    }


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def test_product_llm_chat_route_is_deferred_in_default_http_app_without_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(app, "POST", _chat_route(run_id), _chat_body())

    assert _status_code(response) == 501
    body = _body(response)
    assert body["status"] == "not_enabled"
    assert body["error"]["code"] == "not_enabled"
    assert body["error"]["capability"] == "llm_product_chat_route"
    assert _event_types(app, run_id) == before_events
    assert "PRODUCT_CHAT_MESSAGE_SHOULD_NOT_LEAK" not in repr(body)


def test_product_llm_chat_route_stays_deferred_when_provider_routes_are_enabled(tmp_path):
    provider = RecordingToolProvider()
    runner = RecordingProcessRunner()
    app = create_llm_provider_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
        ),
        provider=provider,
        process_runner=runner,
    )
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(app, "POST", _chat_route(run_id), _chat_body())

    assert _status_code(response) == 501
    body = _body(response)
    assert body["status"] == "not_enabled"
    assert body["error"]["capability"] == "llm_product_chat_route"
    supported_paths = {route["path"] for route in app.list_routes()["routes"] if route["status"] == "supported"}
    assert "/runs/{run_id}/llm/chat-turns" not in supported_paths
    assert provider.calls == []
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events
    assert "PRODUCT_CHAT_MESSAGE_SHOULD_NOT_LEAK" not in repr(body)
