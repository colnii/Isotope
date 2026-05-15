from __future__ import annotations

from typing import Any

import pytest

from isotope import codex_server
from isotope import http_api
from isotope import llm_provider
from isotope.platform.errors import IsotopeError
from isotope.features.chat.flow import (
    build_llm_product_chat_entry_resume_state,
    mark_llm_product_chat_entry_state_resumed,
    submit_llm_product_chat_entry_resume,
    submit_llm_product_chat_turn_with_preflight,
    submit_llm_product_chat_user_message_with_preflight,
)


class FakeCompletedProcess:
    returncode = 0
    stdout = '{"event":"task_complete","secret":"APP_ENTRY_STDOUT_SHOULD_NOT_LEAK"}\n'
    stderr = ""


class RecordingProcessRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return FakeCompletedProcess()


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
        self.calls.append(
            {"messages": list(messages), "tools": list(tools), "max_tokens": max_tokens}
        )
        assert self.responses
        return self.responses.pop(0)


def _product_chat_app(tmp_path, provider: Any, runner: RecordingProcessRunner):
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
    )


def _create_run(app) -> str:
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="product chat app entry")
    return run["run_id"]


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _messages(secret: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Use the product chat route."},
        {"role": "user", "content": secret},
    ]


def _final_answer_response(content: str = "Safe final answer.") -> Any:
    return llm_provider.LLMFinalAnswerResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="stop",
        usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        content=content,
    )


def _provider_response(
    prompt: str = "APP_ENTRY_TOOL_PROMPT_SHOULD_NOT_LEAK",
    *,
    call_id: str = "call_app_entry_pending",
    summary: str = "app entry pending task",
) -> Any:
    return llm_provider.LLMToolCallResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="tool_calls",
        usage={"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
        tool_call=llm_provider.LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={
                "prompt": prompt,
                "summary": summary,
            },
        ),
    )


def _ready_preflight() -> dict[str, Any]:
    return {
        "ready": True,
        "gate": "passed",
        "category": "ready",
        "status": "completed",
        "reason_code": "llm_product_chat_live_smoke_completed",
        "summary": "product-chat smoke completed direct answer, approval pause, and resume final answer",
        "next_step": "use this as a dev-only preflight before application-layer product chat wiring",
    }


def _blocked_preflight() -> dict[str, Any]:
    return {
        "ready": False,
        "gate": "blocked",
        "category": "missing_configuration",
        "status": "missing_configuration",
        "reason_code": "llm_provider_not_configured",
        "summary": "LLM provider is not configured",
        "next_step": "configure ISOTOPE_LLM_PROVIDER and provider credentials before running product-chat smoke",
    }


def test_product_chat_app_entry_blocks_unready_preflight_without_side_effects(tmp_path):
    provider = SequencedChatProvider([_final_answer_response()])
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = submit_llm_product_chat_turn_with_preflight(
        app,
        run_id,
        preflight=_blocked_preflight(),
        messages=_messages("APP_ENTRY_BLOCKED_MESSAGE_SHOULD_NOT_LEAK"),
        max_tokens=64,
    )

    assert response.status_code == 412
    body = response.json()
    assert body["status"] == "blocked_by_preflight"
    assert body["reason_code"] == "llm_product_chat_preflight_blocked"
    assert body["preflight"]["ready"] is False
    assert body["preflight"]["gate"] == "blocked"
    assert body["preflight"]["category"] == "missing_configuration"
    assert body["preflight"]["reason_code"] == "llm_provider_not_configured"
    assert body["preflight"]["next_step"] == (
        "configure ISOTOPE_LLM_PROVIDER and provider credentials before running product-chat smoke"
    )
    assert provider.calls == []
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events
    assert "APP_ENTRY_BLOCKED_MESSAGE_SHOULD_NOT_LEAK" not in repr(body)


def test_product_chat_app_entry_forwards_when_preflight_is_ready(tmp_path):
    provider = SequencedChatProvider([_final_answer_response("Final answer through gated entry.")])
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)

    response = submit_llm_product_chat_turn_with_preflight(
        app,
        run_id,
        preflight=_ready_preflight(),
        messages=_messages("APP_ENTRY_READY_MESSAGE_SHOULD_NOT_LEAK"),
        max_tokens=72,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["provider_status"] == "final_answer"
    assert body["turn_kind"] == "initial"
    assert body["assistant_message"] == {
        "role": "assistant",
        "content": "Final answer through gated entry.",
    }
    assert provider.calls[0]["max_tokens"] == 72
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["codex_task"]
    assert runner.calls == []
    assert "run.completed" in _event_types(app, run_id)
    assert "APP_ENTRY_READY_MESSAGE_SHOULD_NOT_LEAK" not in repr(body)


def test_product_chat_app_entry_builds_resume_state_without_leaks(tmp_path):
    provider = SequencedChatProvider(
        [
            _provider_response(
                prompt="APP_ENTRY_STATE_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_app_entry_state",
            )
        ]
    )
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)

    response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_ready_preflight(),
        user_message="APP_ENTRY_STATE_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=72,
        complete_run=False,
    )
    state = build_llm_product_chat_entry_resume_state(
        response,
        root=tmp_path,
        run_id=run_id,
        preflight=_ready_preflight(),
    )

    assert state is not None
    assert state["schema_version"] == "product_chat_entry_state_v1"
    assert state["root"] == str(tmp_path)
    assert state["run_id"] == run_id
    assert state["approval_id"].startswith("approval_")
    assert state["llm_result"]["approval_id"] == state["approval_id"]
    assert state["preflight"]["ready"] is True
    assert state["resume"] == {"status": "pending"}
    rendered = repr(state)
    assert "APP_ENTRY_STATE_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_STATE_PROMPT_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_app_entry_resume_helper_approves_and_returns_final_answer_without_leaks(
    tmp_path,
):
    provider = SequencedChatProvider(
        [
            _provider_response(
                prompt="APP_ENTRY_RESUME_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_app_entry_resume",
            ),
            _final_answer_response("APP_ENTRY_RESUME_FINAL_SHOULD_NOT_LEAK"),
        ]
    )
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    first_response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_ready_preflight(),
        user_message="APP_ENTRY_RESUME_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=72,
        complete_run=False,
    )
    state = build_llm_product_chat_entry_resume_state(
        first_response,
        root=tmp_path,
        run_id=run_id,
        preflight=_ready_preflight(),
    )
    assert state is not None

    result = submit_llm_product_chat_entry_resume(
        app,
        state,
        messages=_messages("APP_ENTRY_RESUME_FOLLOWUP_SHOULD_NOT_LEAK"),
        max_tokens=80,
    )

    assert result["approval"] == {
        "artifact_ref_present": True,
        "status": "running",
        "tool_execution_status": "completed",
    }
    assert result["entry"] == {
        "artifact_ref_present": True,
        "assistant_message_present": True,
        "http_status": 200,
        "previous_provider_tool_call_id": "call_app_entry_resume",
        "provider": "deepseek",
        "provider_status": "final_answer",
        "requires_approval": False,
        "run_state_status": "completed",
        "status": "completed",
        "tool_result_artifact_ref_present": True,
        "tool_result_status": "completed",
        "turn_kind": "tool_result_followup",
    }
    assert len(runner.calls) == 1
    rendered = repr(result)
    assert state["approval_id"] not in rendered
    assert "APP_ENTRY_RESUME_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_RESUME_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_RESUME_FOLLOWUP_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_RESUME_FINAL_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_app_entry_resume_rejects_mismatched_approval_state_before_side_effects(
    tmp_path,
):
    provider = SequencedChatProvider(
        [
            _provider_response(
                prompt="APP_ENTRY_MISMATCH_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_app_entry_mismatch",
            ),
            _final_answer_response("APP_ENTRY_MISMATCH_FINAL_SHOULD_NOT_LEAK"),
        ]
    )
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    first_response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_ready_preflight(),
        user_message="APP_ENTRY_MISMATCH_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=72,
        complete_run=False,
    )
    state = build_llm_product_chat_entry_resume_state(
        first_response,
        root=tmp_path,
        run_id=run_id,
        preflight=_ready_preflight(),
    )
    assert state is not None
    before_events = _event_types(app, run_id)
    bad_state = dict(state)
    bad_state["approval_id"] = "approval_mismatched"

    with pytest.raises(IsotopeError) as exc_info:
        submit_llm_product_chat_entry_resume(
            app,
            bad_state,
            messages=_messages("APP_ENTRY_MISMATCH_FOLLOWUP_SHOULD_NOT_LEAK"),
            max_tokens=80,
        )

    assert exc_info.value.code == "product_chat_entry_state_invalid"
    assert exc_info.value.details == {"field": "approval_id", "reason": "llm_result_mismatch"}
    assert len(provider.calls) == 1
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events
    rendered = repr(exc_info.value.details)
    assert "APP_ENTRY_MISMATCH_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_MISMATCH_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_MISMATCH_FOLLOWUP_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_MISMATCH_FINAL_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_app_entry_resume_rejects_already_resumed_state_before_side_effects(
    tmp_path,
):
    provider = SequencedChatProvider(
        [
            _provider_response(
                prompt="APP_ENTRY_ALREADY_RESUMED_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_app_entry_already_resumed",
            ),
            _final_answer_response("APP_ENTRY_ALREADY_RESUMED_FINAL_SHOULD_NOT_LEAK"),
        ]
    )
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    first_response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_ready_preflight(),
        user_message="APP_ENTRY_ALREADY_RESUMED_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=72,
        complete_run=False,
    )
    state = build_llm_product_chat_entry_resume_state(
        first_response,
        root=tmp_path,
        run_id=run_id,
        preflight=_ready_preflight(),
    )
    assert state is not None
    resumed_state = mark_llm_product_chat_entry_state_resumed(
        state,
        approval={"tool_execution_status": "completed"},
        entry={"status": "completed"},
    )
    before_events = _event_types(app, run_id)

    with pytest.raises(IsotopeError) as exc_info:
        submit_llm_product_chat_entry_resume(
            app,
            resumed_state,
            messages=_messages("APP_ENTRY_ALREADY_RESUMED_FOLLOWUP_SHOULD_NOT_LEAK"),
            max_tokens=80,
        )

    assert exc_info.value.code == "product_chat_entry_state_already_resumed"
    assert exc_info.value.details == {"resume_status": "completed"}
    assert len(provider.calls) == 1
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events
    rendered = repr(exc_info.value.details)
    assert "APP_ENTRY_ALREADY_RESUMED_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_ALREADY_RESUMED_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_ALREADY_RESUMED_FOLLOWUP_SHOULD_NOT_LEAK" not in rendered
    assert "APP_ENTRY_ALREADY_RESUMED_FINAL_SHOULD_NOT_LEAK" not in rendered


def test_product_chat_app_entry_resume_maps_missing_approval_context_without_leaks(
    tmp_path,
):
    provider = SequencedChatProvider(
        [
            _provider_response(
                prompt="APP_ENTRY_MISSING_APPROVAL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_app_entry_missing_approval",
            )
        ]
    )
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path / "source", provider, runner)
    run_id = _create_run(app)
    first_response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_ready_preflight(),
        user_message="APP_ENTRY_MISSING_APPROVAL_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=72,
        complete_run=False,
    )
    state = build_llm_product_chat_entry_resume_state(
        first_response,
        root=tmp_path / "source",
        run_id=run_id,
        preflight=_ready_preflight(),
    )
    assert state is not None
    empty_app = _product_chat_app(
        tmp_path / "empty",
        SequencedChatProvider([_final_answer_response("APP_ENTRY_MISSING_APPROVAL_FINAL_SHOULD_NOT_LEAK")]),
        RecordingProcessRunner(),
    )

    with pytest.raises(IsotopeError) as exc_info:
        submit_llm_product_chat_entry_resume(
            empty_app,
            state,
            messages=_messages("APP_ENTRY_MISSING_APPROVAL_FOLLOWUP_SHOULD_NOT_LEAK"),
            max_tokens=80,
        )

    assert exc_info.value.code == "product_chat_entry_approval_unavailable"
    assert exc_info.value.details == {"reason": "unknown_approval"}
    assert len(provider.calls) == 1
    assert empty_app.server.get_events(run_id) == []
    assert "APP_ENTRY_MISSING_APPROVAL_MESSAGE_SHOULD_NOT_LEAK" not in repr(exc_info.value.details)
    assert "APP_ENTRY_MISSING_APPROVAL_PROMPT_SHOULD_NOT_LEAK" not in repr(exc_info.value.details)
    assert "APP_ENTRY_MISSING_APPROVAL_FOLLOWUP_SHOULD_NOT_LEAK" not in repr(exc_info.value.details)


def test_product_chat_app_entry_blocks_malformed_preflight_without_side_effects(tmp_path):
    provider = SequencedChatProvider([_final_answer_response()])
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = submit_llm_product_chat_turn_with_preflight(
        app,
        run_id,
        preflight={"category": "ready"},
        messages=_messages("APP_ENTRY_MALFORMED_PREFLIGHT_MESSAGE_SHOULD_NOT_LEAK"),
    )

    assert response.status_code == 412
    body = response.json()
    assert body["status"] == "blocked_by_preflight"
    assert body["preflight"]["ready"] is False
    assert body["preflight"]["category"] == "invalid_preflight"
    assert provider.calls == []
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events
    assert "APP_ENTRY_MALFORMED_PREFLIGHT_MESSAGE_SHOULD_NOT_LEAK" not in repr(body)


def test_product_chat_user_message_entry_rejects_empty_message_without_side_effects(tmp_path):
    provider = SequencedChatProvider([_final_answer_response()])
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_ready_preflight(),
        user_message="   ",
    )

    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "bad_request"
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["details"]["field"] == "user_message"
    assert provider.calls == []
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events


def test_product_chat_user_message_entry_explains_blocked_preflight_without_leaking_message(
    tmp_path,
):
    provider = SequencedChatProvider([_final_answer_response()])
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_blocked_preflight(),
        user_message="APP_ENTRY_USER_BLOCKED_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=80,
    )

    assert response.status_code == 412
    body = response.json()
    assert body["status"] == "blocked_by_preflight"
    assert body["reason_code"] == "llm_product_chat_preflight_blocked"
    assert body["preflight"]["ready"] is False
    assert body["explanation"] == {
        "summary": "LLM provider is not configured",
        "next_step": "configure ISOTOPE_LLM_PROVIDER and provider credentials before running product-chat smoke",
    }
    assert provider.calls == []
    assert runner.calls == []
    assert _event_types(app, run_id) == before_events
    assert "APP_ENTRY_USER_BLOCKED_MESSAGE_SHOULD_NOT_LEAK" not in repr(body)


def test_product_chat_user_message_entry_builds_messages_after_preflight_passes(tmp_path):
    provider = SequencedChatProvider([_final_answer_response("Answer through user entry.")])
    runner = RecordingProcessRunner()
    app = _product_chat_app(tmp_path, provider, runner)
    run_id = _create_run(app)

    response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_ready_preflight(),
        user_message="APP_ENTRY_USER_READY_MESSAGE_SHOULD_NOT_LEAK",
        system_message="Use the safe app entry.",
        max_tokens=96,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["provider_status"] == "final_answer"
    assert provider.calls[0]["messages"] == [
        {"role": "system", "content": "Use the safe app entry."},
        {"role": "user", "content": "APP_ENTRY_USER_READY_MESSAGE_SHOULD_NOT_LEAK"},
    ]
    assert provider.calls[0]["max_tokens"] == 96
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["codex_task"]
    assert runner.calls == []
    assert "run.completed" in _event_types(app, run_id)
    assert "APP_ENTRY_USER_READY_MESSAGE_SHOULD_NOT_LEAK" not in repr(body)
