from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

import isotope.integrations.codex.server as codex_server
from isotope.interfaces.http import HttpApiApp, create_http_app, create_llm_provider_http_app
from isotope.llm.provider import LLMToolCall, LLMToolCallResponse


ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


class StubCompletedProcess:
    def __init__(self, *, stdout: str = "") -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


class RecordingProcessRunner:
    def __init__(self, result: StubCompletedProcess) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return self.result


class RecordingToolProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, response: LLMToolCallResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "max_tokens": max_tokens,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class SequencedToolProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, responses: list[LLMToolCallResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "max_tokens": max_tokens,
            }
        )
        assert self.responses
        return self.responses.pop(0)


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
    run = app.server.create_run(session["session_id"], goal="provider chooses a controlled tool")
    return run["run_id"]


def _provider_route(run_id: str) -> str:
    return f"/runs/{run_id}/llm/tool-calls"


def _followup_route(run_id: str) -> str:
    return f"/runs/{run_id}/llm/tool-result-followups"


def _approval_route(run_id: str, approval_id: str) -> str:
    return f"/runs/{run_id}/approvals/{approval_id}/resolve"


def _approved_body() -> dict[str, str]:
    return {
        "resolution": "approved",
        "reason": "test approval",
        "resolver": "pytest",
    }


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _provider_response(
    prompt: str = "PROVIDER_PROMPT_SHOULD_NOT_LEAK",
    *,
    call_id: str = "call_http_provider",
    summary: str = "provider-selected Codex task",
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="tool_calls",
        usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={
                "prompt": prompt,
                "summary": summary,
            },
        ),
    )


def _messages(secret: str = "HTTP_PROVIDER_MESSAGE_SHOULD_NOT_LEAK") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Select exactly one provided Isotope tool."},
        {"role": "user", "content": f"Use the tool. {secret}"},
    ]


def _provider_http_app(
    tmp_path,
    provider: RecordingToolProvider,
    runner: RecordingProcessRunner,
):
    return create_llm_provider_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=17,
            max_output_bytes=4096,
        ),
        provider=provider,
        process_runner=runner,
    )


def test_default_llm_provider_route_requires_provider_without_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(
        app,
        "POST",
        _provider_route(run_id),
        {"messages": _messages()},
    )

    assert _status_code(response) == 400
    body = _body(response)
    assert body["status"] == "bad_request"
    assert body["error"]["code"] == "bad_request"
    assert body["error"]["capability"] == "llm_provider_tool_call"
    assert _event_types(app, run_id) == before_events


def test_llm_provider_route_is_listed_by_default_and_with_provider(tmp_path):
    default_app = create_http_app(tmp_path / "default")
    provider = RecordingToolProvider(_provider_response())
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _provider_http_app(tmp_path / "provider", provider, runner)

    assert ("POST", "/runs/{run_id}/llm/tool-calls") in default_app.routes()
    assert ("POST", "/runs/{run_id}/llm/tool-calls") in app.routes()
    assert ("POST", "/runs/{run_id}/llm/tool-result-followups") in default_app.routes()
    assert ("POST", "/runs/{run_id}/llm/tool-result-followups") in app.routes()


def test_llm_provider_route_submits_pending_approval_without_starting_codex(tmp_path):
    provider = RecordingToolProvider(_provider_response())
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _provider_http_app(tmp_path, provider, runner)
    run_id = _create_run(app)

    response = _request(
        app,
        "POST",
        _provider_route(run_id),
        {
            "messages": _messages(),
            "max_tokens": 64,
        },
    )

    assert _status_code(response) == 202
    body = _body(response)
    assert body["status"] == "pending_user_approval"
    assert body["provider"] == "deepseek"
    assert body["model"] == "deepseek-v4-flash"
    assert body["finish_reason"] == "tool_calls"
    assert body["tool_name"] == "codex_task"
    assert body["provider_tool_call_id"] == "call_http_provider"
    assert body["approval_id"].startswith("approval_")
    assert body["proposal_id"].startswith("prop_")
    assert body["decision_id"].startswith("dec_")
    assert body["usage"] == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["codex_task"]
    assert provider.calls[0]["max_tokens"] == 64
    assert "PROVIDER_PROMPT_SHOULD_NOT_LEAK" not in repr(body)
    assert "HTTP_PROVIDER_MESSAGE_SHOULD_NOT_LEAK" not in repr(body)
    assert runner.calls == []
    event_types = _event_types(app, run_id)
    assert "approval.requested" in event_types
    assert not ACTION_EXECUTION_EVENTS.intersection(event_types)


@pytest.mark.parametrize(
    "json_body",
    [
        None,
        {},
        {"messages": []},
        {"messages": [{"role": "user", "content": ""}]},
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 0},
    ],
)
def test_llm_provider_route_rejects_malformed_body_without_side_effects(
    tmp_path,
    json_body,
):
    provider = RecordingToolProvider(_provider_response())
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _provider_http_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(app, "POST", _provider_route(run_id), json_body)

    assert _status_code(response) == 400
    body = _body(response)
    assert body["status"] == "bad_request"
    assert body["error"]["code"] == "invalid_request"
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []


def test_llm_provider_route_provider_failure_has_no_action_side_effects(tmp_path):
    provider = RecordingToolProvider(RuntimeError("network failed: SECRET_PROVIDER_TEXT"))
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _provider_http_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(app, "POST", _provider_route(run_id), {"messages": _messages()})

    assert _status_code(response) == 502
    body = _body(response)
    assert body["status"] == "internal"
    assert body["error"]["code"] == "llm_provider_request_failed"
    assert "SECRET_PROVIDER_TEXT" not in repr(body)
    assert _event_types(app, run_id) == before_events
    assert provider.calls
    assert runner.calls == []


def test_llm_provider_route_idempotency_replays_without_duplicate_provider_call(tmp_path):
    provider = RecordingToolProvider(_provider_response())
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _provider_http_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    body = {
        "messages": _messages(),
        "idempotency_key": "provider-tool-call-001",
    }

    first = _request(app, "POST", _provider_route(run_id), body)
    second = _request(app, "POST", _provider_route(run_id), body)

    assert _status_code(first) == 202
    assert _status_code(second) == 202
    assert _body(first) == _body(second)
    assert len(provider.calls) == 1
    assert _event_types(app, run_id).count("approval.requested") == 1
    assert runner.calls == []


def test_llm_tool_result_followup_route_submits_second_pending_approval(tmp_path):
    provider = SequencedToolProvider(
        [
            _provider_response(
                "FOLLOWUP_ROUTE_FIRST_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_http_first",
                summary="first provider-selected Codex task",
            ),
            _provider_response(
                "FOLLOWUP_ROUTE_SECOND_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_http_second",
                summary="second provider-selected Codex task",
            ),
        ]
    )
    runner = RecordingProcessRunner(
        StubCompletedProcess(stdout='{"event":"task_complete","secret":"FOLLOWUP_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    app = _provider_http_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    first = _body(
        _request(
            app,
            "POST",
            _provider_route(run_id),
            {"messages": _messages("FOLLOWUP_ROUTE_MESSAGE_SHOULD_NOT_LEAK"), "complete_run": False},
        )
    )
    first_approved = _body(
        _request(app, "POST", _approval_route(run_id, first["approval_id"]), _approved_body())
    )

    response = _request(
        app,
        "POST",
        _followup_route(run_id),
        {
            "messages": _messages("FOLLOWUP_ROUTE_FOLLOWUP_MESSAGE_SHOULD_NOT_LEAK"),
            "llm_result": first,
            "tool_execution_result": first_approved,
            "max_tokens": 96,
        },
    )

    assert _status_code(response) == 202
    body = _body(response)
    assert body["status"] == "pending_user_approval"
    assert body["provider_status"] == "tool_result_followup_selected"
    assert body["tool_name"] == "codex_task"
    assert body["provider_tool_call_id"] == "call_http_second"
    assert body["previous_provider_tool_call_id"] == "call_http_first"
    assert body["tool_result_status"] == "completed"
    assert body["tool_result_artifact_ref"] == first_approved["artifact_ref"]
    assert body["submission_status"] == "pending_user_approval"
    assert body["requires_approval"] is True
    assert body["approval_id"].startswith("approval_")
    assert len(provider.calls) == 2
    assert provider.calls[1]["max_tokens"] == 96
    assert provider.calls[1]["messages"][-1]["role"] == "tool"
    assert provider.calls[1]["messages"][-1]["tool_call_id"] == "call_http_first"
    assert len(runner.calls) == 1
    event_types = _event_types(app, run_id)
    assert event_types.count("approval.requested") == 2
    assert event_types.count("action.started") == 1
    assert "run.completed" not in event_types
    rendered = repr(body)
    assert "FOLLOWUP_ROUTE_FIRST_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "FOLLOWUP_ROUTE_SECOND_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "FOLLOWUP_ROUTE_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "FOLLOWUP_ROUTE_FOLLOWUP_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "FOLLOWUP_STDOUT_SHOULD_NOT_LEAK" not in rendered

    second_approved = _body(
        _request(app, "POST", _approval_route(run_id, body["approval_id"]), _approved_body())
    )
    assert second_approved["status"] == "completed"
    assert len(runner.calls) == 2


@pytest.mark.parametrize(
    "json_body",
    [
        None,
        {},
        {"messages": _messages()},
        {"messages": _messages(), "llm_result": {}, "tool_execution_result": {}},
        {"messages": [], "llm_result": {}, "tool_execution_result": {}},
    ],
)
def test_llm_tool_result_followup_route_rejects_malformed_body_without_side_effects(
    tmp_path,
    json_body,
):
    provider = RecordingToolProvider(_provider_response())
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _provider_http_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(app, "POST", _followup_route(run_id), json_body)

    assert _status_code(response) == 400
    body = _body(response)
    assert body["status"] == "bad_request"
    assert body["error"]["code"] == "invalid_request"
    assert _event_types(app, run_id) == before_events
    assert provider.calls == []
    assert runner.calls == []


def test_llm_tool_result_followup_route_rejects_completed_run_before_provider_call(tmp_path):
    provider = SequencedToolProvider(
        [
            _provider_response(
                "FOLLOWUP_ROUTE_COMPLETED_FIRST_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_completed_first",
            ),
            _provider_response(
                "FOLLOWUP_ROUTE_COMPLETED_SECOND_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_completed_second",
            ),
        ]
    )
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _provider_http_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    first = _body(_request(app, "POST", _provider_route(run_id), {"messages": _messages()}))
    approved = _body(_request(app, "POST", _approval_route(run_id, first["approval_id"]), _approved_body()))
    before_events = _event_types(app, run_id)

    response = _request(
        app,
        "POST",
        _followup_route(run_id),
        {
            "messages": _messages(),
            "llm_result": first,
            "tool_execution_result": approved,
        },
    )

    assert _status_code(response) == 409
    body = _body(response)
    assert body["status"] == "conflict"
    assert body["error"]["code"] == "run_not_open_for_followup_submission"
    assert len(provider.calls) == 1
    assert _event_types(app, run_id) == before_events
    assert len(runner.calls) == 1
