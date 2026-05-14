"""Application-layer helpers for gated product-chat calls.

This module is intentionally a thin wrapper over the in-process product-chat
HTTP facade. It does not add a hosted route or a multi-turn product loop.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ...errors import KernelError
from ...http_api import HttpResponse


DEFAULT_PRODUCT_CHAT_SYSTEM_MESSAGE = "Use the product chat route."
PRODUCT_CHAT_ENTRY_STATE_SCHEMA = "product_chat_entry_state_v1"


def submit_llm_product_chat_turn_with_preflight(
    app: Any,
    run_id: str,
    *,
    preflight: Mapping[str, Any],
    messages: list[dict[str, str]],
    llm_result: Mapping[str, Any] | None = None,
    tool_execution_result: Mapping[str, Any] | None = None,
    max_tokens: int = 512,
    complete_run: bool = True,
    max_tool_steps: int = 1,
) -> HttpResponse:
    """Submit a product-chat turn only after a low-sensitive preflight gate passes."""

    gate = _product_chat_preflight_gate(preflight)
    if not gate["ready"]:
        return _blocked_preflight_response(gate)

    body: dict[str, Any] = {
        "messages": deepcopy(messages),
        "max_tokens": max_tokens,
        "complete_run": complete_run,
        "max_tool_steps": max_tool_steps,
    }
    if llm_result is not None:
        body["llm_result"] = deepcopy(dict(llm_result))
    if tool_execution_result is not None:
        body["tool_execution_result"] = deepcopy(dict(tool_execution_result))
    return app.request("POST", f"/runs/{run_id}/llm/chat-turns", json=body)


def submit_llm_product_chat_user_message_with_preflight(
    app: Any,
    run_id: str,
    *,
    preflight: Mapping[str, Any],
    user_message: str,
    system_message: str = DEFAULT_PRODUCT_CHAT_SYSTEM_MESSAGE,
    llm_result: Mapping[str, Any] | None = None,
    tool_execution_result: Mapping[str, Any] | None = None,
    max_tokens: int = 512,
    complete_run: bool = True,
    max_tool_steps: int = 1,
) -> HttpResponse:
    """Accept one user sentence, gate it by preflight, then call product chat."""

    safe_user_message = _required_user_message(user_message)
    if safe_user_message is None:
        return _invalid_user_message_response()

    messages = [
        {
            "role": "system",
            "content": _safe_text(
                system_message,
                default=DEFAULT_PRODUCT_CHAT_SYSTEM_MESSAGE,
            ),
        },
        {"role": "user", "content": safe_user_message},
    ]
    return submit_llm_product_chat_turn_with_preflight(
        app,
        run_id,
        preflight=preflight,
        messages=messages,
        llm_result=llm_result,
        tool_execution_result=tool_execution_result,
        max_tokens=max_tokens,
        complete_run=complete_run,
        max_tool_steps=max_tool_steps,
    )


def build_llm_product_chat_entry_resume_state(
    response: HttpResponse,
    *,
    root: Any,
    run_id: str,
    preflight: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build local resume state for a pending product-chat entry response."""

    body = response.json()
    if not isinstance(body, dict):
        return None
    approval_id = body.get("approval_id")
    if body.get("status") != "pending_user_approval" or not isinstance(approval_id, str):
        return None
    return {
        "schema_version": PRODUCT_CHAT_ENTRY_STATE_SCHEMA,
        "root": str(root),
        "run_id": run_id,
        "approval_id": approval_id,
        "preflight": _safe_json_object(dict(preflight)),
        "llm_result": _safe_json_object(body),
        "resume": {"status": "pending"},
    }


def submit_llm_product_chat_entry_resume(
    app: Any,
    state: Mapping[str, Any],
    *,
    messages: list[dict[str, str]],
    max_tokens: int = 512,
    complete_run: bool = True,
    resolver: str = "llm_product_chat_app",
    reason: str = "product-chat entry resume approved",
) -> dict[str, Any]:
    """Approve a saved product-chat entry state and submit one safe resume turn."""

    resume_state = validate_llm_product_chat_entry_resume_state(state)
    try:
        approval_result = app.server.resolve_approval(
            resume_state["approval_id"],
            {
                "resolution": "approved",
                "reason": _safe_text(reason, default="product-chat entry resume approved"),
                "resolver": _safe_text(resolver, default="llm_product_chat_app"),
            },
        )
    except ValueError as exc:
        _raise_product_chat_entry_approval_error(exc)
    approval_body = product_chat_entry_approval_result_body(approval_result)
    response = submit_llm_product_chat_turn_with_preflight(
        app,
        resume_state["run_id"],
        preflight=resume_state["preflight"],
        messages=messages,
        llm_result=resume_state["llm_result"],
        tool_execution_result=approval_body,
        max_tokens=max_tokens,
        complete_run=complete_run,
    )
    return {
        "approval": summarize_product_chat_entry_approval_result(approval_body),
        "entry": summarize_llm_product_chat_entry_response(response),
    }


def mark_llm_product_chat_entry_state_resumed(
    state: Mapping[str, Any],
    *,
    approval: Mapping[str, Any],
    entry: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a copied local resume state marked with a low-sensitive resume summary."""

    updated = dict(validate_llm_product_chat_entry_resume_state(state))
    updated["resume"] = {
        "status": entry.get("status"),
        "approval_resolved": approval.get("tool_execution_status") == "completed",
    }
    return _safe_json_object(updated)


def validate_llm_product_chat_entry_resume_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy a product-chat entry resume state object."""

    if not isinstance(state, Mapping) or state.get("schema_version") != PRODUCT_CHAT_ENTRY_STATE_SCHEMA:
        raise KernelError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "invalid"},
        )
    copied = _safe_json_object(dict(state))
    for key in ("root", "run_id", "approval_id"):
        if not isinstance(copied.get(key), str) or not copied[key]:
            raise KernelError(
                "product-chat entry state file is incomplete",
                code="product_chat_entry_state_invalid",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": key},
            )
    if not isinstance(copied.get("preflight"), dict) or not isinstance(copied.get("llm_result"), dict):
        raise KernelError(
            "product-chat entry state file is incomplete",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "resume_context"},
        )
    resume = copied.get("resume")
    if isinstance(resume, dict):
        resume_status = resume.get("status")
        if resume_status != "pending":
            raise KernelError(
                "product-chat entry state has already been resumed",
                code="product_chat_entry_state_already_resumed",
                category="conflict",
                retryable=False,
                http_status=409,
                details={"resume_status": resume_status},
            )
    llm_result = copied["llm_result"]
    if llm_result.get("status") != "pending_user_approval":
        raise KernelError(
            "product-chat entry state file is not pending approval",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "llm_result", "reason": "not_pending_user_approval"},
        )
    if llm_result.get("approval_id") != copied["approval_id"]:
        raise KernelError(
            "product-chat entry state approval id does not match llm result",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "approval_id", "reason": "llm_result_mismatch"},
        )
    return copied


def _raise_product_chat_entry_approval_error(exc: ValueError) -> None:
    message = str(exc)
    if "unknown approval" in message:
        raise KernelError(
            "product-chat entry approval is unavailable",
            code="product_chat_entry_approval_unavailable",
            category="not_found",
            retryable=False,
            http_status=404,
            details={"reason": "unknown_approval"},
        ) from exc
    if "approval already resolved" in message:
        raise KernelError(
            "product-chat entry approval has already been resolved",
            code="product_chat_entry_approval_already_resolved",
            category="conflict",
            retryable=False,
            http_status=409,
            details={"reason": "approval_already_resolved"},
        ) from exc
    raise KernelError(
        "product-chat entry approval could not be resumed",
        code="product_chat_entry_approval_unavailable",
        category="runtime",
        retryable=False,
        http_status=409,
        details={"reason": "approval_resume_failed"},
    ) from exc


def product_chat_entry_approval_result_body(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build the low-sensitive approved execution body used for model follow-up."""

    body: dict[str, Any] = {"status": result.get("status")}
    if isinstance(result.get("tool_execution_status"), str):
        body["tool_execution_status"] = result["tool_execution_status"]
    if isinstance(result.get("execution_id"), str):
        body["execution_id"] = result["execution_id"]
    artifact_ref = result.get("artifact_ref")
    if hasattr(artifact_ref, "to_dict"):
        body["artifact_ref"] = artifact_ref.to_dict()
    elif isinstance(artifact_ref, dict):
        body["artifact_ref"] = dict(artifact_ref)
    return body


def summarize_product_chat_entry_approval_result(body: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize approval execution without raw approval id or artifact content."""

    return {
        "status": body.get("status"),
        "tool_execution_status": body.get("tool_execution_status"),
        "artifact_ref_present": isinstance(body.get("artifact_ref"), dict),
    }


def summarize_llm_product_chat_entry_response(response: HttpResponse) -> dict[str, Any]:
    """Summarize a product-chat app-entry response for safe CLI/app output."""

    body = response.json()
    if not isinstance(body, dict):
        return {"http_status": response.status_code, "status": "invalid_response"}
    summary: dict[str, Any] = {
        "http_status": response.status_code,
        "status": body.get("status"),
    }
    error = body.get("error")
    if isinstance(error, dict):
        summary["error_code"] = error.get("code")
        details = error.get("details")
        if isinstance(details, dict):
            summary["reason_code"] = details.get("reason_code")
    if isinstance(body.get("reason_code"), str):
        summary["reason_code"] = body.get("reason_code")
    if isinstance(body.get("explanation"), dict):
        summary["explanation"] = dict(body["explanation"])
    for key in (
        "provider",
        "provider_status",
        "turn_kind",
        "tool_name",
        "previous_provider_tool_call_id",
        "tool_result_status",
    ):
        if isinstance(body.get(key), str) and body[key]:
            summary[key] = body[key]
    if isinstance(body.get("requires_approval"), bool):
        summary["requires_approval"] = body["requires_approval"]
    if isinstance(body.get("approval_id"), str) and body["approval_id"]:
        summary["approval_id_present"] = True
    if body.get("status") == "pending_user_approval":
        summary["next_step"] = "resolve the pending approval before expecting tool execution or a final answer"
    if isinstance(body.get("assistant_message"), dict):
        summary["assistant_message_present"] = True
    if isinstance(body.get("artifact_ref"), dict):
        summary["artifact_ref_present"] = True
    if isinstance(body.get("tool_result_artifact_ref"), dict):
        summary["tool_result_artifact_ref_present"] = True
    run_state = body.get("run_state")
    if isinstance(run_state, dict) and isinstance(run_state.get("status"), str):
        summary["run_state_status"] = run_state["status"]
    return summary


def _blocked_preflight_response(gate: dict[str, Any]) -> HttpResponse:
    return HttpResponse(
        status_code=412,
        body={
            "status": "blocked_by_preflight",
            "reason_code": "llm_product_chat_preflight_blocked",
            "preflight": gate,
            "explanation": _preflight_explanation(gate),
        },
    )


def _preflight_explanation(gate: Mapping[str, Any]) -> dict[str, str]:
    return {
        "summary": _safe_optional_text(gate.get("summary"))
        or "Product-chat preflight is not ready.",
        "next_step": _safe_optional_text(gate.get("next_step"))
        or "Run product-chat diagnosis before submitting a chat turn.",
    }


def _required_user_message(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _invalid_user_message_response() -> HttpResponse:
    return HttpResponse(
        status_code=400,
        body={
            "status": "bad_request",
            "error": {
                "code": "invalid_request",
                "message": "missing required request field: user_message",
                "category": "validation",
                "retryable": False,
                "details": {
                    "field": "user_message",
                    "reason_code": "llm_product_chat_user_message_required",
                },
            },
        },
    )


def _product_chat_preflight_gate(preflight: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(preflight, Mapping):
        return _blocked_preflight_gate(category="invalid_preflight")

    ready = preflight.get("ready") is True
    if ready:
        return {
            "ready": True,
            "gate": "passed",
            "category": _safe_text(preflight.get("category"), default="ready"),
            "status": _safe_text(preflight.get("status"), default="completed"),
            "reason_code": _safe_text(
                preflight.get("reason_code"),
                default="llm_product_chat_preflight_ready",
            ),
            "summary": _safe_optional_text(preflight.get("summary")),
            "next_step": _safe_optional_text(preflight.get("next_step")),
        }

    category = _safe_text(preflight.get("category"), default="invalid_preflight")
    if category == "ready":
        category = "invalid_preflight"
    return _blocked_preflight_gate(
        category=category,
        status=_safe_optional_text(preflight.get("status")),
        reason_code=_safe_optional_text(preflight.get("reason_code")),
        summary=_safe_optional_text(preflight.get("summary")),
        next_step=_safe_optional_text(preflight.get("next_step")),
    )


def _blocked_preflight_gate(
    *,
    category: str,
    status: str | None = None,
    reason_code: str | None = None,
    summary: str | None = None,
    next_step: str | None = None,
) -> dict[str, Any]:
    return {
        "ready": False,
        "gate": "blocked",
        "category": category,
        "status": status,
        "reason_code": reason_code,
        "summary": summary,
        "next_step": next_step,
    }


def _safe_text(value: Any, *, default: str) -> str:
    if not isinstance(value, str) or not value:
        return default
    return value[:256]


def _safe_optional_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:256]


def _safe_json_object(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_json_object(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_json_object(item) for item in value]
    if hasattr(value, "to_dict"):
        return _safe_json_object(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return _safe_json_object(asdict(value))
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value


__all__ = [
    "PRODUCT_CHAT_ENTRY_STATE_SCHEMA",
    "build_llm_product_chat_entry_resume_state",
    "mark_llm_product_chat_entry_state_resumed",
    "product_chat_entry_approval_result_body",
    "submit_llm_product_chat_entry_resume",
    "submit_llm_product_chat_turn_with_preflight",
    "submit_llm_product_chat_user_message_with_preflight",
    "summarize_llm_product_chat_entry_response",
    "summarize_product_chat_entry_approval_result",
    "validate_llm_product_chat_entry_resume_state",
]
