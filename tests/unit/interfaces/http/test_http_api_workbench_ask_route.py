from __future__ import annotations

from typing import Any

from isotope.interfaces.http import create_http_app
from isotope.llm.provider import LLMResponse


class RecordingAskProvider:
    provider = "fake"
    model = "fake-workbench-ask"

    def __init__(self, answer: str = "先整理一个可展示任务。") -> None:
        self.answer = answer
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
            content=self.answer,
            finish_reason="stop",
            usage={"prompt_tokens": 21, "completion_tokens": 9},
            raw={"id": "fake"},
        )


def test_http_api_workbench_ask_route_answers_from_public_metadata_context(tmp_path):
    provider = RecordingAskProvider("建议先把作品集拆成一个可展示任务。")
    app = create_http_app(tmp_path, workbench_ask_provider=provider)
    _successful_json(
        _request(
            app,
            "POST",
            "/projects",
            {"name": "portfolio demo", "summary": "autumn recruiting workspace"},
        )
    )
    _successful_json(
        _request(
            app,
            "POST",
            "/tasks",
            {
                "goal": "build portfolio story",
                "message": "PRIVATE_TASK_NOTE_SHOULD_NOT_LEAK",
            },
        )
    )
    _successful_json(
        _request(
            app,
            "POST",
            "/files",
            {
                "name": "portfolio-notes.md",
                "summary": "portfolio notes",
                "content": "PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK",
            },
        )
    )

    payload = _successful_json(
        _request(
            app,
            "POST",
            "/workbench/ask",
            {"question": "下一步做什么？", "limit": 3, "max_tokens": 128},
        )
    )

    assert payload["status"] == "ok"
    assert payload["answer"]["answer"] == "建议先把作品集拆成一个可展示任务。"
    assert payload["answer"]["provider"] == "fake"
    assert payload["answer"]["model"] == "fake-workbench-ask"
    assert payload["answer"]["context"]["counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 3,
    }
    assert [reference["result_type"] for reference in payload["answer"]["references"]] == [
        "project",
        "task",
        "file",
    ]
    assert payload["answer"]["references"][0]["title"] == "portfolio demo"
    assert provider.calls[0]["max_tokens"] == 128
    _assert_no_private_content(payload)


def test_http_api_workbench_ask_route_is_unavailable_without_provider(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(
        app,
        "POST",
        "/workbench/ask",
        {"question": "下一步做什么？"},
    )

    assert response.status_code == 501
    assert response.body["error"]["code"] == "unavailable"
    assert response.body["error"]["capability"] == "workbench_ask"


def test_http_api_workbench_ask_route_requires_question(tmp_path):
    app = create_http_app(tmp_path, workbench_ask_provider=RecordingAskProvider())

    response = _request(app, "POST", "/workbench/ask", {"max_tokens": 128})

    assert response.status_code == 400
    assert response.body["error"]["code"] == "invalid_request"
    assert response.body["error"]["details"]["field"] == "question"


def _request(app, method: str, path: str, json_body: dict[str, Any] | None = None):
    return app.request(method, path, json=json_body)


def _successful_json(response) -> dict[str, Any]:
    assert response.status_code < 300
    assert isinstance(response.body, dict)
    return response.body


def _assert_no_private_content(value: Any) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _assert_no_private_content(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_private_content(nested)
    elif isinstance(value, str):
        assert "PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK" not in value
        assert "PRIVATE_TASK_NOTE_SHOULD_NOT_LEAK" not in value
