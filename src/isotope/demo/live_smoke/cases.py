"""Request builders and case summaries for LLM live-smoke flows."""

from __future__ import annotations

from typing import Any

from .cli_support import (
    _response_dict,
    _run_state_status,
    _safe_body_string,
)


def _run_llm_product_chat_live_smoke_cases(
    app: Any,
    config: LLMProductChatLiveSmokeConfig,
    *,
    provider_name: str,
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    provider = provider_name
    model = None

    direct_run_id = _create_smoke_run(app, "llm product chat live smoke: direct answer")
    direct_response = app.request(
        "POST",
        f"/runs/{direct_run_id}/llm/chat-turns",
        json=_product_chat_request_body(
            _product_chat_messages(config.direct_prompt, mode="direct"),
            config=config,
            complete_run=True,
        ),
    )
    direct_body = _response_dict(direct_response)
    provider = _safe_body_string(direct_body, "provider") or provider
    model = _safe_body_string(direct_body, "model") or model
    cases.append(_direct_final_answer_case(direct_response.status_code, direct_body))
    if direct_response.status_code != 200 or direct_body.get("status") != "completed":
        return _product_chat_failed(provider=provider, model=model, cases=cases)

    tool_run_id = _create_smoke_run(app, "llm product chat live smoke: tool approval resume")
    tool_response = app.request(
        "POST",
        f"/runs/{tool_run_id}/llm/chat-turns",
        json=_product_chat_request_body(
            _product_chat_messages(config.tool_prompt, mode="tool"),
            config=config,
            complete_run=False,
        ),
    )
    tool_body = _response_dict(tool_response)
    provider = _safe_body_string(tool_body, "provider") or provider
    model = _safe_body_string(tool_body, "model") or model
    cases.append(_tool_choice_case(tool_response.status_code, tool_body))
    if (
        tool_response.status_code != 202
        or tool_body.get("status") != "pending_user_approval"
        or not isinstance(tool_body.get("approval_id"), str)
    ):
        return _product_chat_failed(provider=provider, model=model, cases=cases)

    approval_response = app.request(
        "POST",
        f"/runs/{tool_run_id}/approvals/{tool_body['approval_id']}/resolve",
        json={
            "resolution": "approved",
            "reason": "approve LLM product chat live smoke tool call",
            "resolver": "isotope-live-smoke",
        },
    )
    approval_body = _response_dict(approval_response)
    cases.append(_approval_resolution_case(approval_response.status_code, approval_body))
    if approval_response.status_code != 200 or approval_body.get("status") != "running":
        return _product_chat_failed(provider=provider, model=model, cases=cases)

    resume_response = app.request(
        "POST",
        f"/runs/{tool_run_id}/llm/chat-turns",
        json={
            **_product_chat_request_body(
                _product_chat_messages(config.resume_prompt, mode="resume"),
                config=config,
                complete_run=True,
            ),
            "llm_result": tool_body,
            "tool_execution_result": approval_body,
        },
    )
    resume_body = _response_dict(resume_response)
    provider = _safe_body_string(resume_body, "provider") or provider
    model = _safe_body_string(resume_body, "model") or model
    cases.append(_resume_final_answer_case(resume_response.status_code, resume_body))
    if resume_response.status_code != 200 or resume_body.get("status") != "completed":
        return _product_chat_failed(provider=provider, model=model, cases=cases)

    return {
        "status": "completed",
        "reason_code": "llm_product_chat_live_smoke_completed",
        "provider": provider,
        "model": model,
        "case_count": len(cases),
        "cases": cases,
    }


def _messages(config: LLMToolCallLiveSmokeConfig) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are testing Isotope provider tool-call selection. "
                "You must choose the provided tool and must not answer in text."
            ),
        },
        {"role": "user", "content": config.prompt},
    ]


def _terminal_tool_messages(config: LLMTerminalToolLiveSmokeConfig) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are testing Isotope terminal tool selection. "
                "Only choose the provided terminal_exec tool. Do not answer directly."
            ),
        },
        {"role": "user", "content": config.prompt},
    ]


def _create_smoke_run(app: Any, goal: str) -> str:
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal=goal)
    return run["run_id"]


def _product_chat_request_body(
    messages: list[dict[str, str]],
    *,
    config: LLMProductChatLiveSmokeConfig,
    complete_run: bool,
) -> dict[str, Any]:
    return {
        "messages": messages,
        "max_tokens": config.max_tokens,
        "complete_run": complete_run,
        "max_tool_steps": 1,
    }


def _product_chat_messages(prompt: str, *, mode: str) -> list[dict[str, str]]:
    if mode == "direct":
        instruction = "Answer directly in text and do not call tools."
    elif mode == "tool":
        instruction = "Choose codex_task exactly once and do not answer directly."
    else:
        instruction = "Produce a final answer from the provided tool result and do not call tools."
    return [
        {
            "role": "system",
            "content": f"You are testing Isotope product chat. {instruction}",
        },
        {"role": "user", "content": prompt},
    ]


def _direct_final_answer_case(http_status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": "direct_final_answer",
        "http_status": http_status,
        "status": body.get("status"),
        "provider_status": body.get("provider_status"),
        "turn_kind": body.get("turn_kind"),
        "artifact_ref_present": isinstance(body.get("artifact_ref"), dict),
        "assistant_message_present": isinstance(body.get("assistant_message"), dict),
        "run_state_status": _run_state_status(body),
    }


def _tool_choice_case(http_status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": "tool_choice_pending_approval",
        "http_status": http_status,
        "status": body.get("status"),
        "provider_status": body.get("provider_status"),
        "turn_kind": body.get("turn_kind"),
        "tool_name": body.get("tool_name"),
        "requires_approval": body.get("requires_approval"),
        "approval_id_present": isinstance(body.get("approval_id"), str),
        "run_state_status": _run_state_status(body),
    }


def _approval_resolution_case(http_status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": "approval_resolution",
        "http_status": http_status,
        "status": body.get("status"),
        "artifact_ref_present": isinstance(body.get("artifact_ref"), dict),
        "run_state_status": _run_state_status(body),
    }


def _resume_final_answer_case(http_status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": "resume_final_answer",
        "http_status": http_status,
        "status": body.get("status"),
        "provider_status": body.get("provider_status"),
        "turn_kind": body.get("turn_kind"),
        "assistant_message_present": isinstance(body.get("assistant_message"), dict),
        "tool_result_artifact_ref_present": isinstance(body.get("tool_result_artifact_ref"), dict),
        "run_state_status": _run_state_status(body),
    }


def _product_chat_failed(
    *,
    provider: str,
    model: Any,
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "failed",
        "reason_code": "llm_product_chat_live_smoke_failed",
        "provider": provider,
        "case_count": len(cases),
        "cases": cases,
    }
    if isinstance(model, str) and model:
        result["model"] = model
    return result
