from __future__ import annotations

import json
from typing import Any

import pytest

from isotope import llm_provider
from isotope import codex_server
from isotope.errors import KernelError
from isotope.http_api import create_codex_cli_http_app
from isotope.llm_provider import (
    DeepSeekToolCallProvider,
    LLMToolCall,
    LLMToolCallResponse,
    build_llm_tool_result_message,
    select_llm_tool_result_followup,
    submit_llm_tool_call,
    submit_llm_tool_result_followup,
)


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


def _codex_http_app(tmp_path, runner: RecordingProcessRunner):
    return create_codex_cli_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=17,
            max_output_bytes=4096,
        ),
        process_runner=runner,
    )


def _create_run(app) -> str:
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="model chooses a controlled tool")
    return run["run_id"]


def _approve_route(run_id: str, approval_id: str) -> str:
    return f"/runs/{run_id}/approvals/{approval_id}/resolve"


def _approved_body() -> dict[str, str]:
    return {
        "resolution": "approved",
        "reason": "operator approved provider-selected Codex task",
        "resolver": "reviewer",
    }


def _body(response) -> dict[str, Any]:
    body = response.body
    assert isinstance(body, dict)
    return body


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Select exactly one available Isotope tool."},
        {"role": "user", "content": "Inspect the repository without leaking this prompt."},
    ]


def _provider_call(call_id: str, prompt_secret: str, summary: str) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="tool_calls",
        usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={
                "prompt": prompt_secret,
                "summary": summary,
            },
        ),
    )


def test_llm_tool_loop_sends_catalog_to_provider_and_waits_for_approval(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(
        LLMToolCallResponse(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="tool_calls",
            usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            tool_call=LLMToolCall(
                call_id="call_123",
                tool_name="codex_task",
                arguments={
                    "prompt": "LLM_PROVIDER_PROMPT_SHOULD_NOT_LEAK",
                    "summary": "model-selected Codex inspection",
                },
            ),
        )
    )

    result = submit_llm_tool_call(app, run_id, provider, _messages(), max_tokens=128)

    assert result["status"] == "pending_user_approval"
    assert result["provider"] == "deepseek"
    assert result["model"] == "deepseek-v4-flash"
    assert result["finish_reason"] == "tool_calls"
    assert result["usage"] == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    assert result["tool_name"] == "codex_task"
    assert result["provider_tool_call_id"] == "call_123"
    assert result["tool_result"]["status"] == "pending_user_approval"
    assert "LLM_PROVIDER_PROMPT_SHOULD_NOT_LEAK" not in repr(result)
    assert provider.calls[0]["max_tokens"] == 128
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == [
        "write_artifact_tool",
        "terminal_exec",
        "codex_task",
    ]
    assert runner.calls == []
    event_types = _event_types(app, run_id)
    assert "approval.requested" in event_types
    assert not ACTION_EXECUTION_EVENTS.intersection(event_types)


def test_llm_tool_result_message_returns_artifact_ref_without_transcript_or_prompt(tmp_path):
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"message":"TOOL_RESULT_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(
        LLMToolCallResponse(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="tool_calls",
            usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            tool_call=LLMToolCall(
                call_id="call_tool_result",
                tool_name="codex_task",
                arguments={
                    "prompt": "TOOL_RESULT_PROMPT_SHOULD_NOT_LEAK",
                    "summary": "model-selected Codex inspection",
                },
            ),
        )
    )

    pending = submit_llm_tool_call(app, run_id, provider, _messages(), max_tokens=128)
    approved = _body(
        app.request("POST", _approve_route(run_id, pending["tool_result"]["approval_id"]), _approved_body())
    )
    message = build_llm_tool_result_message(pending, approved)

    assert message["role"] == "tool"
    assert message["tool_call_id"] == "call_tool_result"
    assert message["name"] == "codex_task"
    content = json.loads(message["content"])
    assert content == {
        "artifact_ref": approved["artifact_ref"],
        "execution_id": approved["execution_id"],
        "status": "completed",
        "tool_name": "codex_task",
    }
    assert {"prompt", "messages", "stdout", "stderr", "stdin", "raw_content"}.isdisjoint(content)
    rendered = json.dumps(message, sort_keys=True)
    assert "TOOL_RESULT_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "TOOL_RESULT_STDOUT_SHOULD_NOT_LEAK" not in rendered


def test_llm_tool_result_followup_sends_safe_tool_message_for_next_model_choice_without_action_side_effect(
    tmp_path,
):
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"message":"FOLLOWUP_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = SequencedToolProvider(
        [
            _provider_call(
                "call_first_tool",
                "FOLLOWUP_FIRST_PROMPT_SHOULD_NOT_LEAK",
                "first provider-selected Codex inspection",
            ),
            _provider_call(
                "call_second_tool",
                "FOLLOWUP_SECOND_PROMPT_SHOULD_NOT_LEAK",
                "second provider-selected Codex inspection",
            ),
        ]
    )

    first = submit_llm_tool_call(app, run_id, provider, _messages(), max_tokens=128)
    approved = _body(
        app.request("POST", _approve_route(run_id, first["tool_result"]["approval_id"]), _approved_body())
    )
    followup = select_llm_tool_result_followup(
        app,
        run_id,
        provider,
        _messages(),
        first,
        approved,
        max_tokens=96,
    )

    assert followup["status"] == "tool_call_selected"
    assert followup["provider_status"] == "tool_result_followup_selected"
    assert followup["previous_provider_tool_call_id"] == "call_first_tool"
    assert followup["provider_tool_call_id"] == "call_second_tool"
    assert followup["tool_name"] == "codex_task"
    assert followup["tool_result_status"] == "completed"
    assert followup["tool_result_artifact_ref"] == approved["artifact_ref"]
    assert len(provider.calls) == 2
    second_messages = provider.calls[1]["messages"]
    assert second_messages[-2]["role"] == "assistant"
    assert second_messages[-2]["content"] == "Tool call selected by Isotope."
    assert second_messages[-2]["tool_calls"] == [
        {
            "id": "call_first_tool",
            "type": "function",
            "function": {"name": "codex_task", "arguments": "{}"},
        }
    ]
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_call_id"] == "call_first_tool"
    assert second_messages[-1]["name"] == "codex_task"
    tool_content = json.loads(second_messages[-1]["content"])
    assert tool_content == {
        "artifact_ref": approved["artifact_ref"],
        "execution_id": approved["execution_id"],
        "status": "completed",
        "tool_name": "codex_task",
    }
    assert provider.calls[1]["max_tokens"] == 96
    assert len(runner.calls) == 1
    event_types = _event_types(app, run_id)
    assert event_types.count("approval.requested") == 1
    assert event_types.count("action.started") == 1
    assert event_types[-1] == "run.completed"
    rendered = json.dumps({"followup": followup, "messages": second_messages}, sort_keys=True)
    assert "FOLLOWUP_FIRST_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "FOLLOWUP_SECOND_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "FOLLOWUP_STDOUT_SHOULD_NOT_LEAK" not in rendered
    assert {"prompt", "messages", "stdout", "stderr", "stdin", "raw_content"}.isdisjoint(followup)


def test_llm_tool_result_followup_can_submit_second_action_when_first_action_keeps_run_open(
    tmp_path,
):
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"message":"MULTI_STEP_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = SequencedToolProvider(
        [
            _provider_call(
                "call_first_open_tool",
                "MULTI_STEP_FIRST_PROMPT_SHOULD_NOT_LEAK",
                "first provider-selected Codex inspection",
            ),
            _provider_call(
                "call_second_open_tool",
                "MULTI_STEP_SECOND_PROMPT_SHOULD_NOT_LEAK",
                "second provider-selected Codex inspection",
            ),
        ]
    )

    first = submit_llm_tool_call(
        app,
        run_id,
        provider,
        _messages(),
        max_tokens=128,
        complete_run=False,
    )
    first_approved = _body(
        app.request("POST", _approve_route(run_id, first["tool_result"]["approval_id"]), _approved_body())
    )

    assert first_approved["status"] == "running"
    assert first_approved["run_state"]["status"] == "running"
    assert len(runner.calls) == 1
    assert "run.completed" not in _event_types(app, run_id)

    followup = submit_llm_tool_result_followup(
        app,
        run_id,
        provider,
        _messages(),
        first,
        first_approved,
        max_tokens=96,
    )

    assert followup["status"] == "pending_user_approval"
    assert followup["provider_status"] == "tool_result_followup_selected"
    assert followup["previous_provider_tool_call_id"] == "call_first_open_tool"
    assert followup["provider_tool_call_id"] == "call_second_open_tool"
    assert followup["tool_name"] == "codex_task"
    assert followup["tool_result_status"] == "completed"
    assert followup["tool_result_artifact_ref"] == first_approved["artifact_ref"]
    assert followup["requires_approval"] is True
    assert len(provider.calls) == 2
    assert len(runner.calls) == 1
    event_types_after_followup = _event_types(app, run_id)
    assert event_types_after_followup.count("approval.requested") == 2
    assert event_types_after_followup.count("action.started") == 1
    assert "run.completed" not in event_types_after_followup

    second_approved = _body(
        app.request("POST", _approve_route(run_id, followup["tool_result"]["approval_id"]), _approved_body())
    )

    assert second_approved["status"] == "completed"
    assert second_approved["run_state"]["status"] == "completed"
    assert len(runner.calls) == 2
    event_types = _event_types(app, run_id)
    assert event_types.count("approval.requested") == 2
    assert event_types.count("action.started") == 2
    assert event_types.count("run.completed") == 1
    assert event_types[-1] == "run.completed"
    rendered = json.dumps({"followup": followup, "second": second_approved}, sort_keys=True)
    assert "MULTI_STEP_FIRST_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "MULTI_STEP_SECOND_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "MULTI_STEP_STDOUT_SHOULD_NOT_LEAK" not in rendered
    assert {"prompt", "messages", "stdout", "stderr", "stdin", "raw_content"}.isdisjoint(followup)


def test_llm_tool_result_followup_submission_rejects_completed_run_before_provider_call(
    tmp_path,
):
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"message":"COMPLETED_RUN_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = SequencedToolProvider(
        [
            _provider_call(
                "call_first_completed_tool",
                "COMPLETED_RUN_FIRST_PROMPT_SHOULD_NOT_LEAK",
                "first provider-selected Codex inspection",
            ),
            _provider_call(
                "call_second_completed_tool",
                "COMPLETED_RUN_SECOND_PROMPT_SHOULD_NOT_LEAK",
                "second provider-selected Codex inspection",
            ),
        ]
    )

    first = submit_llm_tool_call(app, run_id, provider, _messages(), max_tokens=128)
    approved = _body(
        app.request("POST", _approve_route(run_id, first["tool_result"]["approval_id"]), _approved_body())
    )

    assert approved["status"] == "completed"
    assert len(provider.calls) == 1
    with pytest.raises(KernelError) as exc_info:
        submit_llm_tool_result_followup(
            app,
            run_id,
            provider,
            _messages(),
            first,
            approved,
            max_tokens=96,
        )

    assert exc_info.value.code == "run_not_open_for_followup_submission"
    assert exc_info.value.http_status == 409
    assert exc_info.value.details == {"run_id": run_id, "status": "completed"}
    assert len(provider.calls) == 1
    event_types = _event_types(app, run_id)
    assert event_types.count("approval.requested") == 1
    assert event_types.count("action.started") == 1
    assert event_types.count("run.completed") == 1
    rendered = repr(exc_info.value)
    assert "COMPLETED_RUN_FIRST_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "COMPLETED_RUN_SECOND_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "COMPLETED_RUN_STDOUT_SHOULD_NOT_LEAK" not in rendered


def test_llm_tool_result_followup_rejects_unknown_run_before_provider_call(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"message":"unused"}\n'))
    app = _codex_http_app(tmp_path, runner)
    provider = SequencedToolProvider(
        [
            _provider_call(
                "call_unused",
                "UNKNOWN_RUN_PROMPT_SHOULD_NOT_LEAK",
                "unused provider choice",
            )
        ]
    )

    with pytest.raises(KernelError) as exc_info:
        select_llm_tool_result_followup(
            app,
            "missing_run",
            provider,
            _messages(),
            {"provider_tool_call_id": "call_previous", "tool_name": "codex_task"},
            {
                "status": "completed",
                "execution_id": "execution_previous",
                "artifact_ref": {
                    "ref_type": "artifact",
                    "run_id": "missing_run",
                    "artifact_id": "artifact_previous",
                },
            },
        )

    assert exc_info.value.code == "unknown_run"
    assert provider.calls == []
    assert runner.calls == []


def test_llm_tool_result_message_requires_provider_call_id():
    with pytest.raises(KernelError) as exc_info:
        build_llm_tool_result_message(
            {"status": "completed", "tool_name": "codex_task"},
            {
                "status": "completed",
                "execution_id": "exec_001",
                "artifact_ref": {
                    "ref_type": "artifact",
                    "run_id": "run_001",
                    "artifact_id": "artifact_001",
                },
            },
        )

    assert exc_info.value.code == "llm_tool_result_invalid_source"


def test_llm_tool_result_message_requires_artifact_ref_for_completed_tool():
    with pytest.raises(KernelError) as exc_info:
        build_llm_tool_result_message(
            {
                "status": "pending_user_approval",
                "provider_tool_call_id": "call_missing_artifact",
                "tool_name": "codex_task",
            },
            {"status": "completed", "execution_id": "exec_001"},
        )

    assert exc_info.value.code == "llm_tool_result_missing_artifact_ref"


def test_deepseek_tool_provider_posts_openai_compatible_tool_call_request():
    captured: dict[str, Any] = {}

    def fake_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "id": "chatcmpl_test",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc",
                                "type": "function",
                                "function": {
                                    "name": "codex_task",
                                    "arguments": json.dumps(
                                        {
                                            "prompt": "Inspect current repo.",
                                            "summary": "model-selected Codex inspection",
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        }

    provider = DeepSeekToolCallProvider(api_key="test_secret", transport=fake_transport)

    response = provider.select_tool(
        _messages(),
        tools=[
            {
                "name": "codex_task",
                "action": "delegate_agent_task",
                "input_schema": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {"prompt": {"type": "string"}},
                },
            }
        ],
        max_tokens=64,
    )

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["temperature"] == 0
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["tool_choice"] == "required"
    assert captured["payload"]["max_tokens"] == 64
    assert captured["payload"]["tools"][0]["type"] == "function"
    assert captured["payload"]["tools"][0]["function"]["name"] == "codex_task"
    assert captured["payload"]["tools"][0]["function"]["parameters"]["required"] == ["prompt"]
    assert captured["headers"]["Authorization"] == "Bearer test_secret"
    assert captured["timeout"] == 60
    assert response.provider == "deepseek"
    assert response.model == "deepseek-v4-flash"
    assert response.finish_reason == "tool_calls"
    assert response.tool_call.tool_name == "codex_task"
    assert response.tool_call.arguments["summary"] == "model-selected Codex inspection"
    assert response.usage["total_tokens"] == 14
    assert "test_secret" not in repr(response)


def test_deepseek_tool_provider_chat_turn_can_return_final_answer():
    captured: dict[str, Any] = {}

    def fake_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "Safe final answer from the model.",
                    },
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
        }

    provider = DeepSeekToolCallProvider(api_key="test_secret", transport=fake_transport)

    response = provider.select_chat_turn(
        _messages(),
        tools=[{"name": "codex_task", "input_schema": {}}],
        max_tokens=96,
    )

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["tool_choice"] == "auto"
    assert captured["payload"]["max_tokens"] == 96
    assert isinstance(response, llm_provider.LLMFinalAnswerResponse)
    assert response.provider == "deepseek"
    assert response.model == "deepseek-v4-flash"
    assert response.finish_reason == "stop"
    assert response.content == "Safe final answer from the model."
    assert response.usage["total_tokens"] == 14


def test_llm_tool_loop_rejects_text_response_without_side_effects(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)
    provider = RecordingToolProvider(
        ValueError("model response did not include a tool call: SECRET_RAW_MODEL_TEXT")
    )

    with pytest.raises(KernelError) as exc_info:
        submit_llm_tool_call(app, run_id, provider, _messages())

    assert exc_info.value.code == "llm_tool_call_invalid_response"
    assert exc_info.value.details == {"provider": "deepseek"}
    assert "SECRET_RAW_MODEL_TEXT" not in str(exc_info.value)
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []


def test_deepseek_tool_provider_rejects_bad_tool_arguments_without_raw_leak():
    def fake_transport(url, payload, headers, timeout):
        return {
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_bad",
                                "type": "function",
                                "function": {
                                    "name": "codex_task",
                                    "arguments": "{not json SECRET_RAW_ARGS}",
                                },
                            }
                        ],
                    },
                }
            ],
        }

    provider = DeepSeekToolCallProvider(api_key="test_secret", transport=fake_transport)

    with pytest.raises(ValueError) as exc_info:
        provider.select_tool(_messages(), tools=[{"name": "codex_task", "input_schema": {}}])

    assert "tool call arguments must be a JSON object" in str(exc_info.value)
    assert "SECRET_RAW_ARGS" not in str(exc_info.value)


def test_deepseek_tool_provider_requires_api_key_without_echoing_key_value():
    with pytest.raises(ValueError) as exc_info:
        DeepSeekToolCallProvider(api_key="")

    assert "DEEPSEEK_API_KEY" in str(exc_info.value)
    assert "test_secret" not in str(exc_info.value)
