from __future__ import annotations

import base64
import json
import os
import shutil
import struct
import zlib
from typing import Any

import pytest

import isotope.integrations.codex.server as codex_server
import isotope.demo.live_smoke.llm_live_smoke as llm_live_smoke
from isotope.interfaces.http import (
    create_codex_cli_http_app,
    create_http_app,
    create_llm_product_chat_http_app,
)
import isotope.llm.provider as llm_provider
from isotope.llm.provider import LLMToolCall, LLMToolCallResponse
from isotope.platform.errors import IsotopeError


ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


class DeterministicCompletedProcess:
    def __init__(self, *, stdout: str = "") -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


class RecordingProcessRunner:
    def __init__(self, result: DeterministicCompletedProcess) -> None:
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


def _product_chat_http_app(tmp_path, runner: RecordingProcessRunner, provider: Any):
    return create_llm_product_chat_http_app(
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
    run = app.server.create_run(session["session_id"], goal="live model chooses a tool")
    return run["run_id"]


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _provider_response(
    prompt: str = "LLM_LIVE_PROMPT_SHOULD_NOT_LEAK",
    *,
    call_id: str = "call_live_smoke",
    summary: str = "live smoke selected Codex task",
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="tool_calls",
        usage={"prompt_tokens": 9, "completion_tokens": 5, "total_tokens": 14},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={
                "prompt": prompt,
                "summary": summary,
            },
        ),
    )


def _final_answer_response(content: str) -> llm_provider.LLMFinalAnswerResponse:
    return llm_provider.LLMFinalAnswerResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="stop",
        usage={"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
        content=content,
    )


def _raw_tool_call_completion() -> dict[str, Any]:
    return {
        "model": "deepseek-unit",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_unified_env",
                            "type": "function",
                            "function": {
                                "name": "codex_task",
                                "arguments": '{"prompt":"ok","summary":"unit"}',
                            },
                        }
                    ]
                },
            }
        ],
        "usage": {"total_tokens": 12},
    }



def test_live_llm_tool_call_smoke_reaches_provider_without_starting_codex(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)

    result = llm_live_smoke.run_llm_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMToolCallLiveSmokeConfig(enabled=True, max_tokens=128),
    )

    assert result["status"] in {"completed", "failed", "missing_configuration"}
    assert "DEEPSEEK_API_KEY" not in repr(result)
    assert llm_live_smoke.DEFAULT_DEEPSEEK_LIVE_SMOKE_PROMPT not in repr(result)
    assert runner.calls == []
    if result["status"] == "completed":
        assert result["tool_name"] == "codex_task"
        assert result["tool_result_status"] == "pending_user_approval"
        assert "approval.requested" in _event_types(app, run_id)


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_LLM_TERMINAL_SMOKE") != "1"
    or llm_provider.resolve_llm_tool_call_provider().status != "configured",
    reason="live LLM terminal tool smoke is opt-in and requires unified provider configuration",
)

def test_live_llm_terminal_tool_smoke_reaches_provider_and_runs_terminal_only(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)

    result = llm_live_smoke.run_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMTerminalToolLiveSmokeConfig(enabled=True, max_tokens=128),
    )

    assert result["status"] in {"completed", "failed", "missing_configuration"}
    assert "DEEPSEEK_API_KEY" not in repr(result)
    assert llm_live_smoke.DEFAULT_LLM_TERMINAL_TOOL_SMOKE_PROMPT not in repr(result)
    assert "codex_task" not in repr(result)
    if result["status"] == "completed":
        assert result["tool_name"] == "terminal_exec"
        assert result["tool_result_status"] == "completed"
        assert "approval.requested" not in _event_types(app, run_id)
        assert "run.completed" in _event_types(app, run_id)


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_MIMO_SCREEN_CONTROL_SMOKE") != "1",
    reason="live Mimo multimodal screen-control smoke is opt-in",
)
def test_live_mimo_multimodal_screen_control_smoke_selects_approval_gated_tool(tmp_path):
    resolution = llm_provider.resolve_llm_tool_call_provider()
    if resolution.status != "configured":
        pytest.skip(f"Mimo provider is not configured: {resolution.reason_code}")
    assert resolution.provider_name == "mimo"
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    image_url = _blue_button_screen_image_url()

    try:
        result = llm_provider.submit_llm_tool_call(
            app,
            run_id,
            resolution.provider,
            _mimo_screen_control_messages(image_url),
            max_tokens=int(os.environ.get("ISOTOPE_LIVE_MIMO_MAX_TOKENS", "2048")),
            tool_names=("screen_control",),
            complete_run=False,
        )
    except IsotopeError as exc:
        pytest.fail(f"Mimo live request failed: {exc.code}", pytrace=False)

    _assert_mimo_screen_control_rules(app, run_id, result, image_url=image_url)


def _mimo_screen_control_messages(image_url: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "You are testing Isotope multimodal screen control. "
                "Choose the offered screen_control tool exactly once and do not answer in text. "
                "Use execution_mode=execute so Isotope asks the human operator for approval before input."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "The image is a small app window with one blue rectangular button. "
                        "Use target_selector {kind: window, selector: {app: notepad.exe}}, "
                        "target_allowlist {allowed_apps: [notepad.exe]}, and one left click near "
                        "the center of the blue button."
                    ),
                },
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]


def _assert_mimo_screen_control_rules(
    app: Any,
    run_id: str,
    result: dict[str, Any],
    *,
    image_url: str,
) -> None:
    assert result["status"] == "pending_user_approval"
    assert result["provider"] == "mimo"
    assert result["tool_name"] == "screen_control"
    assert result["requires_approval"] is True
    assert result["tool_result"]["status"] == "pending_user_approval"
    assert result["tool_result"]["requires_approval"] is True
    assert "approval.requested" in _event_types(app, run_id)
    assert not ACTION_EXECUTION_EVENTS.intersection(_event_types(app, run_id))

    state = app.server.get_run_state(run_id)
    pending_approvals = [
        approval
        for approval in state.approvals.values()
        if approval.get("status") == "pending"
    ]
    assert len(pending_approvals) == 1
    label = pending_approvals[0]["requested_action_label"]
    assert label["tool"] == "screen_control"
    assert label["target_kind"] == "window"
    assert label["selector_keys"] == ["app"]
    assert label["execution_mode"] == "execute"
    assert label["action_count"] == 1
    assert label["action_types"] == ["click"]

    rendered_result = repr(result)
    assert "data:image/" not in rendered_result
    assert image_url not in rendered_result


def _blue_button_screen_image_url() -> str:
    width = 120
    height = 80
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            if 70 <= x <= 110 and 42 <= y <= 66:
                rgb = (24, 36, 56)
            elif 74 <= x <= 106 and 46 <= y <= 62:
                rgb = (38, 118, 245)
            else:
                rgb = (245, 247, 250)
            row.extend(rgb)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
