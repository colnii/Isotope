from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from isotope_kernel import codex_server
from isotope_kernel import http_api
from isotope_kernel.http_api import create_http_app
from isotope_kernel import llm_provider
from isotope_kernel.llm_provider import LLMToolCall, LLMToolCallResponse


ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


class FakeCompletedProcess:
    def __init__(self, *, stdout: str = "") -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


class RecordingProcessRunner:
    def __init__(self, result: FakeCompletedProcess) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return self.result


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
        self.calls.append({"messages": list(messages), "tools": list(tools), "max_tokens": max_tokens})
        assert self.responses
        return self.responses.pop(0)


class SequencedChatProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ):
        self.calls.append({"messages": list(messages), "tools": list(tools), "max_tokens": max_tokens})
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
    run = app.server.create_run(session["session_id"], goal="product chat route contract")
    return run["run_id"]


def _chat_route(run_id: str) -> str:
    return f"/runs/{run_id}/llm/chat-turns"


def _approval_route(run_id: str, approval_id: str) -> str:
    return f"/runs/{run_id}/approvals/{approval_id}/resolve"


def _approved_body() -> dict[str, str]:
    return {
        "resolution": "approved",
        "reason": "operator approved product chat tool call",
        "resolver": "pytest",
    }


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _messages(secret: str = "PRODUCT_CHAT_MESSAGE_SHOULD_NOT_LEAK") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Use Isotope tools when needed."},
        {"role": "user", "content": f"Inspect the workspace. {secret}"},
    ]


def _provider_response(
    prompt: str,
    *,
    call_id: str,
    summary: str,
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="tool_calls",
        usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={"prompt": prompt, "summary": summary},
        ),
    )


def _terminal_provider_response(
    output: str,
    *,
    call_id: str,
    summary: str,
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="tool_calls",
        usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="terminal_exec",
            arguments={"argv": ["printf", output], "summary": summary},
        ),
    )


def _final_answer_response(content: str = "The safe final answer.") -> Any:
    return llm_provider.LLMFinalAnswerResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="stop",
        usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        content=content,
    )


def _product_chat_app(
    tmp_path,
    provider: Any,
    runner: RecordingProcessRunner,
    *,
    tool_names: tuple[str, ...] = ("codex_task",),
):
    return http_api.create_llm_product_chat_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=17,
            max_output_bytes=4096,
        ),
        provider=provider,
        process_runner=runner,
        tool_names=tool_names,
    )


def test_product_chat_route_is_listed_only_when_explicitly_enabled(tmp_path):
    default_app = create_http_app(tmp_path / "default")
    provider = SequencedToolProvider(
        [_provider_response("PRODUCT_CHAT_PROMPT_SHOULD_NOT_LEAK", call_id="call_product", summary="chat task")]
    )
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _product_chat_app(tmp_path / "product", provider, runner)

    assert ("POST", "/runs/{run_id}/llm/chat-turns") not in default_app.routes()
    assert ("POST", "/runs/{run_id}/llm/chat-turns") in app.routes()
    assert ("POST", "/runs/{run_id}/llm/tool-calls") not in app.routes()
    assert ("POST", "/runs/{run_id}/llm/tool-result-followups") not in app.routes()


def test_product_chat_initial_turn_submits_one_pending_approval_without_starting_codex(tmp_path):
    provider = SequencedToolProvider(
        [
            _provider_response(
                "PRODUCT_CHAT_INITIAL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_initial",
                summary="initial product chat task",
            )
        ]
    )
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)

    response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {
            "messages": _messages("PRODUCT_CHAT_INITIAL_MESSAGE_SHOULD_NOT_LEAK"),
            "max_tokens": 64,
            "complete_run": False,
        },
    )

    assert _status_code(response) == 202
    body = _body(response)
    assert body["status"] == "pending_user_approval"
    assert body["provider_status"] == "tool_call_selected"
    assert body["turn_kind"] == "initial"
    assert body["tool_name"] == "codex_task"
    assert body["provider_tool_call_id"] == "call_initial"
    assert body["approval_id"].startswith("approval_")
    assert body["requires_approval"] is True
    assert provider.calls[0]["max_tokens"] == 64
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["codex_task"]
    assert runner.calls == []
    event_types = _event_types(app, run_id)
    assert "approval.requested" in event_types
    assert not ACTION_EXECUTION_EVENTS.intersection(event_types)
    rendered = repr(body)
    assert "PRODUCT_CHAT_INITIAL_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_INITIAL_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_resume_turn_uses_safe_tool_result_and_submits_next_pending_approval(tmp_path):
    provider = SequencedToolProvider(
        [
            _provider_response(
                "PRODUCT_CHAT_FIRST_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_first",
                summary="first product chat task",
            ),
            _provider_response(
                "PRODUCT_CHAT_SECOND_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_second",
                summary="second product chat task",
            ),
        ]
    )
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"event":"task_complete","secret":"PRODUCT_CHAT_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    first = _body(
        _request(
            app,
            "POST",
            _chat_route(run_id),
            {
                "messages": _messages("PRODUCT_CHAT_FIRST_MESSAGE_SHOULD_NOT_LEAK"),
                "complete_run": False,
            },
        )
    )
    first_approved = _body(_request(app, "POST", _approval_route(run_id, first["approval_id"]), _approved_body()))

    response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {
            "messages": _messages("PRODUCT_CHAT_RESUME_MESSAGE_SHOULD_NOT_LEAK"),
            "llm_result": first,
            "tool_execution_result": first_approved,
            "max_tokens": 96,
            "complete_run": True,
        },
    )

    assert _status_code(response) == 202
    body = _body(response)
    assert body["status"] == "pending_user_approval"
    assert body["provider_status"] == "tool_result_followup_selected"
    assert body["turn_kind"] == "tool_result_followup"
    assert body["tool_name"] == "codex_task"
    assert body["provider_tool_call_id"] == "call_second"
    assert body["previous_provider_tool_call_id"] == "call_first"
    assert body["tool_result_status"] == "completed"
    assert body["tool_result_artifact_ref"] == first_approved["artifact_ref"]
    assert body["submission_status"] == "pending_user_approval"
    assert provider.calls[1]["max_tokens"] == 96
    assert provider.calls[1]["messages"][-2]["role"] == "assistant"
    assert provider.calls[1]["messages"][-2]["tool_calls"] == [
        {
            "id": "call_first",
            "type": "function",
            "function": {"name": "codex_task", "arguments": "{}"},
        }
    ]
    assert provider.calls[1]["messages"][-1]["role"] == "tool"
    assert provider.calls[1]["messages"][-1]["tool_call_id"] == "call_first"
    assert len(runner.calls) == 1
    event_types = _event_types(app, run_id)
    assert event_types.count("approval.requested") == 2
    assert event_types.count("action.started") == 1
    assert "run.completed" not in event_types
    rendered = repr(body)
    assert "PRODUCT_CHAT_FIRST_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_SECOND_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_FIRST_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_RESUME_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_STDOUT_SHOULD_NOT_LEAK" not in rendered

    second_approved = _body(_request(app, "POST", _approval_route(run_id, body["approval_id"]), _approved_body()))
    assert second_approved["status"] == "completed"
    assert _event_types(app, run_id).count("run.completed") == 1
    assert len(runner.calls) == 2


def test_product_chat_route_rejects_multi_step_loop_in_one_request_without_side_effects(tmp_path):
    provider = SequencedToolProvider(
        [_provider_response("PRODUCT_CHAT_PROMPT_SHOULD_NOT_LEAK", call_id="call_product", summary="chat task")]
    )
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {
            "messages": _messages(),
            "max_tool_steps": 2,
        },
    )

    assert _status_code(response) == 400
    body = _body(response)
    assert body["status"] == "bad_request"
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["details"]["field"] == "max_tool_steps"
    assert provider.calls == []
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events


def test_product_chat_initial_turn_can_return_final_answer_and_complete_run(tmp_path):
    provider = SequencedChatProvider([_final_answer_response("Safe final answer for the user.")])
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)

    response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {
            "messages": _messages("PRODUCT_CHAT_FINAL_MESSAGE_SHOULD_NOT_LEAK"),
            "max_tokens": 72,
        },
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert body["status"] == "completed"
    assert body["provider_status"] == "final_answer"
    assert body["turn_kind"] == "initial"
    assert body["assistant_message"] == {
        "role": "assistant",
        "content": "Safe final answer for the user.",
    }
    assert body["artifact_ref"]["ref_type"] == "artifact"
    assert body["tool_execution_status"] == "completed"
    assert body["run_state"]["status"] == "completed"
    assert provider.calls[0]["max_tokens"] == 72
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["codex_task"]
    assert runner.calls == []
    event_types = _event_types(app, run_id)
    assert "approval.requested" not in event_types
    assert event_types.count("action.started") == 1
    assert event_types.count("artifact.created") == 1
    assert event_types.count("action.completed") == 1
    assert event_types.count("run.completed") == 1
    rendered = repr(body)
    assert "PRODUCT_CHAT_FINAL_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_final_answer_requires_non_empty_content_without_side_effects(tmp_path):
    provider = SequencedChatProvider([_final_answer_response("   ")])
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {
            "messages": _messages("PRODUCT_CHAT_EMPTY_FINAL_MESSAGE_SHOULD_NOT_LEAK"),
        },
    )

    assert _status_code(response) == 400
    body = _body(response)
    assert body["status"] == "bad_request"
    assert body["error"]["code"] == "llm_final_answer_invalid_response"
    assert provider.calls
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events
    rendered = repr(body)
    assert "PRODUCT_CHAT_EMPTY_FINAL_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_resume_turn_can_return_final_answer_after_safe_tool_result(tmp_path):
    provider = SequencedChatProvider(
        [
            _provider_response(
                "PRODUCT_CHAT_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_needs_tool",
                summary="tool before final answer",
            ),
            _final_answer_response("Final answer after reading the tool result."),
        ]
    )
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"event":"task_complete","secret":"PRODUCT_CHAT_FINAL_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    first = _body(
        _request(
            app,
            "POST",
            _chat_route(run_id),
            {
                "messages": _messages("PRODUCT_CHAT_TOOL_MESSAGE_SHOULD_NOT_LEAK"),
                "complete_run": False,
            },
        )
    )
    first_approved = _body(_request(app, "POST", _approval_route(run_id, first["approval_id"]), _approved_body()))

    response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {
            "messages": _messages("PRODUCT_CHAT_FINAL_RESUME_MESSAGE_SHOULD_NOT_LEAK"),
            "llm_result": first,
            "tool_execution_result": first_approved,
        },
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert body["status"] == "completed"
    assert body["provider_status"] == "final_answer"
    assert body["turn_kind"] == "tool_result_followup"
    assert body["previous_provider_tool_call_id"] == "call_needs_tool"
    assert body["tool_result_status"] == "completed"
    assert body["tool_result_artifact_ref"] == first_approved["artifact_ref"]
    assert body["assistant_message"]["content"] == "Final answer after reading the tool result."
    assert provider.calls[1]["messages"][-2]["role"] == "assistant"
    assert provider.calls[1]["messages"][-2]["tool_calls"] == [
        {
            "id": "call_needs_tool",
            "type": "function",
            "function": {"name": "codex_task", "arguments": "{}"},
        }
    ]
    assert provider.calls[1]["messages"][-1]["role"] == "tool"
    assert provider.calls[1]["messages"][-1]["tool_call_id"] == "call_needs_tool"
    assert len(runner.calls) == 1
    event_types = _event_types(app, run_id)
    assert event_types.count("approval.requested") == 1
    assert event_types.count("run.completed") == 1
    rendered = repr(body)
    assert "PRODUCT_CHAT_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_TOOL_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_FINAL_RESUME_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_FINAL_STDOUT_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_route_can_offer_terminal_exec_and_resume_with_safe_tool_result(tmp_path):
    provider = SequencedChatProvider(
        [
            _terminal_provider_response(
                "PRODUCT_CHAT_TERMINAL_STDOUT_SHOULD_NOT_LEAK",
                call_id="call_terminal_exec",
                summary="model-selected terminal command",
            ),
            _final_answer_response("Final answer after safe terminal result."),
        ]
    )
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _product_chat_app(tmp_path, provider, runner, tool_names=("terminal_exec",))
    run_id = _create_run(app)

    first_response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {
            "messages": _messages("PRODUCT_CHAT_TERMINAL_MESSAGE_SHOULD_NOT_LEAK"),
            "complete_run": False,
        },
    )

    assert _status_code(first_response) == 200
    first = _body(first_response)
    assert first["status"] == "running"
    assert first["provider_status"] == "tool_call_selected"
    assert first["turn_kind"] == "initial"
    assert first["tool_name"] == "terminal_exec"
    assert first["provider_tool_call_id"] == "call_terminal_exec"
    assert first["requires_approval"] is False
    assert first["tool_execution_status"] == "completed"
    assert first["artifact_ref"]["ref_type"] == "artifact"
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["terminal_exec"]
    assert runner.calls == []

    terminal_content = json.loads(
        app.server.artifact_store.get_content(app.server.artifact_store.list_artifacts(run_id)[-1].ref)
    )
    assert terminal_content["stdout"] == "PRODUCT_CHAT_TERMINAL_STDOUT_SHOULD_NOT_LEAK"
    assert terminal_content["shell"] is False

    second_response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {
            "messages": _messages("PRODUCT_CHAT_TERMINAL_RESUME_MESSAGE_SHOULD_NOT_LEAK"),
            "llm_result": first,
            "tool_execution_result": first,
        },
    )

    assert _status_code(second_response) == 200
    body = _body(second_response)
    assert body["status"] == "completed"
    assert body["provider_status"] == "final_answer"
    assert body["turn_kind"] == "tool_result_followup"
    assert body["previous_provider_tool_call_id"] == "call_terminal_exec"
    assert body["tool_result_status"] == "completed"
    assert body["tool_result_artifact_ref"] == first["artifact_ref"]
    assert body["assistant_message"]["content"] == "Final answer after safe terminal result."
    assert provider.calls[1]["messages"][-2]["role"] == "assistant"
    assert provider.calls[1]["messages"][-2]["tool_calls"] == [
        {
            "id": "call_terminal_exec",
            "type": "function",
            "function": {"name": "terminal_exec", "arguments": "{}"},
        }
    ]
    tool_message = provider.calls[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_terminal_exec"
    assert tool_message["name"] == "terminal_exec"
    assert json.loads(tool_message["content"]) == {
        "artifact_ref": first["artifact_ref"],
        "execution_id": first["execution_id"],
        "status": "completed",
        "tool_name": "terminal_exec",
    }
    event_types = _event_types(app, run_id)
    assert "approval.requested" not in event_types
    assert event_types.count("action.started") == 2
    assert event_types.count("run.completed") == 1
    rendered = repr({"first": first, "second": body, "tool_message": tool_message})
    assert "PRODUCT_CHAT_TERMINAL_STDOUT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_TERMINAL_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_TERMINAL_RESUME_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_route_rejects_provider_selected_unoffered_tool_without_side_effects(tmp_path):
    provider = SequencedChatProvider(
        [
            _provider_response(
                "PRODUCT_CHAT_UNOFFERED_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_unoffered_codex",
                summary="unoffered codex task",
            )
        ]
    )
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _product_chat_app(tmp_path, provider, runner, tool_names=("terminal_exec",))
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(
        app,
        "POST",
        _chat_route(run_id),
        {"messages": _messages("PRODUCT_CHAT_UNOFFERED_MESSAGE_SHOULD_NOT_LEAK")},
    )

    assert _status_code(response) == 501
    body = _body(response)
    assert body["status"] == "not_enabled"
    assert body["error"]["code"] == "llm_provider_selected_unoffered_tool"
    assert body["error"]["details"] == {"tool_names": ["codex_task"]}
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["terminal_exec"]
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events
    rendered = repr(body)
    assert "PRODUCT_CHAT_UNOFFERED_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_UNOFFERED_MESSAGE_SHOULD_NOT_LEAK" not in rendered
