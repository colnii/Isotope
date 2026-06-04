"""Public diagnosis helpers for LLM live-smoke results."""

from __future__ import annotations

from typing import Any

from .terminal_diagnosis import (
    _llm_terminal_tool_diagnosis_for,
    _llm_terminal_tool_readiness_check_for,
    _maybe_diagnose_terminal_tool_missing_configuration,
    _terminal_error_reason_summary,
)


def _legacy_deepseek_result(result: dict[str, Any]) -> dict[str, Any]:
    legacy = dict(result)
    reason_code = legacy.get("reason_code")
    if reason_code == "llm_tool_call_live_smoke_unavailable":
        legacy["reason_code"] = "deepseek_tool_call_live_smoke_unavailable"
        legacy["provider"] = "deepseek"
    elif reason_code in {"llm_provider_not_configured", "llm_provider_api_key_missing"}:
        legacy["reason_code"] = "deepseek_api_key_missing"
        legacy["provider"] = "deepseek"
    elif reason_code == "llm_tool_call_live_smoke_completed":
        legacy["reason_code"] = "deepseek_tool_call_live_smoke_completed"
    return legacy


def _llm_diagnosis_for(result: dict[str, Any]) -> dict[str, Any]:
    reason_code = result.get("reason_code")
    status = result.get("status")
    if status == "skipped":
        return _diagnosis(
            category="unavailable",
            provider_request_started=False,
            approval_requested=False,
            codex_started=False,
            summary="live smoke is disabled",
            next_step="enable the smoke explicitly when a real LLM provider check is intended",
        )
    if status == "missing_configuration":
        if reason_code == "llm_provider_unsupported":
            return _diagnosis(
                category="unsupported_provider",
                provider_request_started=False,
                approval_requested=False,
                codex_started=False,
                summary="configured LLM provider is not supported by this boundary",
                next_step="configure a supported provider through the unified provider settings",
            )
        return _diagnosis(
            category="missing_configuration",
            provider_request_started=False,
            approval_requested=False,
            codex_started=False,
            summary="LLM provider is not configured",
            next_step="configure ISOTOPE_LLM_PROVIDER and provider credentials before running the smoke",
        )
    if (
        status == "completed"
        and result.get("tool_name") == "codex_task"
        and result.get("tool_result_status") == "pending_user_approval"
    ):
        return _diagnosis(
            category="ready",
            provider_request_started=True,
            approval_requested=True,
            codex_started=False,
            summary="provider selected codex_task and Isotope stopped at approval",
            next_step="keep this as a dev-only readiness check until product route tests exist",
        )
    if reason_code == "llm_tool_unavailable":
        return _diagnosis(
            category="tool_unavailable",
            provider_request_started=False,
            approval_requested=False,
            codex_started=False,
            summary="the requested tool is absent from the model-facing catalog",
            next_step="wire the intended tool explicitly or keep the smoke limited to codex_task",
        )
    if reason_code == "llm_provider_request_failed":
        return _diagnosis(
            category="provider_request_failed",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="provider request failed before a usable tool call was returned",
            next_step="check provider availability, credentials, network, or proxy settings",
        )
    if reason_code == "llm_tool_call_invalid_response":
        return _diagnosis(
            category="provider_response_invalid",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="provider response did not contain one valid tool call",
            next_step="inspect provider compatibility before widening the integration",
        )
    if reason_code == "llm_provider_selected_unoffered_tool":
        return _diagnosis(
            category="tool_unavailable",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the provider selected a tool that was not offered in this smoke",
            next_step="tighten the provider response or include the intended tool in the smoke config",
        )
    if reason_code == "model_tool_route_unavailable":
        return _diagnosis(
            category="tool_route_unavailable",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the model selected a tool that has no enabled bridge route",
            next_step="add route tests before exposing that tool to a real provider",
        )
    if reason_code in {"model_tool_unavailable", "unknown_model_tool"}:
        return _diagnosis(
            category="provider_selected_unavailable_tool",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the model selected a tool that Isotope will not execute",
            next_step="tighten the provider tool menu or add explicit bridge tests",
        )
    if reason_code == "invalid_model_tool_call":
        return _diagnosis(
            category="provider_tool_arguments_invalid",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the model selected a tool with invalid arguments",
            next_step="inspect the tool schema and prompt before product wiring",
        )
    return _diagnosis(
        category="provider_smoke_failed",
        provider_request_started=status != "missing_configuration",
        approval_requested=False,
        codex_started=False,
        summary="LLM provider tool-call smoke failed with an unclassified result",
        next_step="inspect public reason_code before widening the integration",
    )


def _llm_product_chat_diagnosis_for(result: dict[str, Any]) -> dict[str, Any]:
    reason_code = result.get("reason_code")
    status = result.get("status")
    cases = result.get("cases")
    if not isinstance(cases, list):
        cases = []

    if status == "skipped":
        return _product_chat_diagnosis(
            category="unavailable",
            provider_request_started=False,
            direct_answer_completed=False,
            approval_requested=False,
            approval_resolved=False,
            resume_completed=False,
            summary="product-chat smoke is disabled",
            next_step="enable the smoke explicitly when a product-chat provider check is intended",
        )
    if status == "missing_configuration":
        if reason_code == "llm_provider_unsupported":
            return _product_chat_diagnosis(
                category="unsupported_provider",
                provider_request_started=False,
                direct_answer_completed=False,
                approval_requested=False,
                approval_resolved=False,
                resume_completed=False,
                summary="configured LLM provider is not supported by this boundary",
                next_step="configure a supported provider through the unified provider settings",
            )
        return _product_chat_diagnosis(
            category="missing_configuration",
            provider_request_started=False,
            direct_answer_completed=False,
            approval_requested=False,
            approval_resolved=False,
            resume_completed=False,
            summary="LLM provider is not configured",
            next_step="configure ISOTOPE_LLM_PROVIDER and provider credentials before running product-chat smoke",
        )

    direct_answer_completed = _product_chat_case_completed(
        cases,
        case_name="direct_final_answer",
        http_status=200,
        status="completed",
        required_flags=("artifact_ref_present", "assistant_message_present"),
    )
    approval_requested = _product_chat_case_completed(
        cases,
        case_name="tool_choice_pending_approval",
        http_status=202,
        status="pending_user_approval",
        required_flags=("approval_id_present", "requires_approval"),
    )
    approval_resolved = _product_chat_case_completed(
        cases,
        case_name="approval_resolution",
        http_status=200,
        status="running",
        required_flags=("artifact_ref_present",),
    )
    resume_completed = _product_chat_case_completed(
        cases,
        case_name="resume_final_answer",
        http_status=200,
        status="completed",
        required_flags=("assistant_message_present", "tool_result_artifact_ref_present"),
    )
    if (
        status == "completed"
        and direct_answer_completed
        and approval_requested
        and approval_resolved
        and resume_completed
    ):
        return _product_chat_diagnosis(
            category="ready",
            provider_request_started=True,
            direct_answer_completed=True,
            approval_requested=True,
            approval_resolved=True,
            resume_completed=True,
            summary="product-chat smoke completed direct answer, approval pause, and resume final answer",
            next_step="use this as a dev-only readiness_check before application-layer product chat wiring",
        )

    return _product_chat_diagnosis(
        category="product_chat_smoke_failed",
        provider_request_started=bool(cases),
        direct_answer_completed=direct_answer_completed,
        approval_requested=approval_requested,
        approval_resolved=approval_resolved,
        resume_completed=resume_completed,
        summary="product-chat smoke stopped before all readiness checkpoints completed",
        next_step="inspect the failed case summary before widening application wiring",
    )


def _llm_product_chat_readiness_check_for(result: dict[str, Any]) -> dict[str, Any]:
    diagnosis = result.get("diagnosis")
    if not isinstance(diagnosis, dict):
        diagnosis = {}
    category = diagnosis.get("category")
    ready = category == "ready"
    return {
        "ready": ready,
        "gate": "passed" if ready else "blocked",
        "category": category if isinstance(category, str) and category else "unknown",
        "status": result.get("status"),
        "reason_code": result.get("reason_code"),
        "summary": diagnosis.get("summary"),
        "next_step": diagnosis.get("next_step"),
    }


def _product_chat_case_completed(
    cases: list[Any],
    *,
    case_name: str,
    http_status: int,
    status: str,
    required_flags: tuple[str, ...] = (),
) -> bool:
    for case in cases:
        if not isinstance(case, dict):
            continue
        if case.get("case") != case_name:
            continue
        return (
            case.get("http_status") == http_status
            and case.get("status") == status
            and all(case.get(flag) is True for flag in required_flags)
        )
    return False


def _product_chat_diagnosis(
    *,
    category: str,
    provider_request_started: bool,
    direct_answer_completed: bool,
    approval_requested: bool,
    approval_resolved: bool,
    resume_completed: bool,
    summary: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "provider_request_started": provider_request_started,
        "direct_answer_completed": direct_answer_completed,
        "approval_requested": approval_requested,
        "approval_resolved": approval_resolved,
        "resume_completed": resume_completed,
        "summary": summary,
        "next_step": next_step,
    }


def _diagnosis_for(result: dict[str, Any]) -> dict[str, Any]:
    reason_code = result.get("reason_code")
    status = result.get("status")
    if status == "skipped":
        return _diagnosis(
            category="unavailable",
            provider_request_started=False,
            approval_requested=False,
            codex_started=False,
            summary="live smoke is disabled",
            next_step="enable the smoke explicitly when a real DeepSeek check is intended",
        )
    if status == "missing_configuration":
        return _diagnosis(
            category="missing_configuration",
            provider_request_started=False,
            approval_requested=False,
            codex_started=False,
            summary="DEEPSEEK_API_KEY is not configured",
            next_step="configure DeepSeek credentials before running the live provider smoke",
        )
    if (
        status == "completed"
        and result.get("tool_name") == "codex_task"
        and result.get("tool_result_status") == "pending_user_approval"
    ):
        return _diagnosis(
            category="ready",
            provider_request_started=True,
            approval_requested=True,
            codex_started=False,
            summary="DeepSeek selected codex_task and Isotope stopped at approval",
            next_step="keep this as a dev-only readiness check until product route tests exist",
        )
    if reason_code == "llm_tool_unavailable":
        return _diagnosis(
            category="tool_unavailable",
            provider_request_started=False,
            approval_requested=False,
            codex_started=False,
            summary="the requested tool is absent from the model-facing catalog",
            next_step="wire the intended tool explicitly or keep the smoke limited to codex_task",
        )
    if reason_code == "llm_provider_request_failed":
        return _diagnosis(
            category="provider_request_failed",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="DeepSeek request failed before a usable tool call was returned",
            next_step="check provider availability, credentials, network, or proxy settings",
        )
    if reason_code == "llm_tool_call_invalid_response":
        return _diagnosis(
            category="provider_response_invalid",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="DeepSeek response did not contain one valid tool call",
            next_step="inspect provider compatibility before widening the integration",
        )
    if reason_code == "llm_provider_selected_unoffered_tool":
        return _diagnosis(
            category="tool_unavailable",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the provider selected a tool that was not offered in this smoke",
            next_step="tighten the provider response or include the intended tool in the smoke config",
        )
    if reason_code == "model_tool_route_unavailable":
        return _diagnosis(
            category="tool_route_unavailable",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the model selected a tool that has no enabled bridge route",
            next_step="add route tests before exposing that tool to a real provider",
        )
    if reason_code in {"model_tool_unavailable", "unknown_model_tool"}:
        return _diagnosis(
            category="provider_selected_unavailable_tool",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the model selected a tool that Isotope will not execute",
            next_step="tighten the provider tool menu or add explicit bridge tests",
        )
    if reason_code == "invalid_model_tool_call":
        return _diagnosis(
            category="provider_tool_arguments_invalid",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the model selected a tool with invalid arguments",
            next_step="inspect the tool schema and prompt before product wiring",
        )
    return _diagnosis(
        category="provider_smoke_failed",
        provider_request_started=status != "missing_configuration",
        approval_requested=False,
        codex_started=False,
        summary="DeepSeek tool-call smoke failed with an unclassified result",
        next_step="inspect public reason_code before widening the integration",
    )


def _diagnosis(
    *,
    category: str,
    provider_request_started: bool,
    approval_requested: bool,
    codex_started: bool,
    summary: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "provider_request_started": provider_request_started,
        "approval_requested": approval_requested,
        "codex_started": codex_started,
        "summary": summary,
        "next_step": next_step,
    }
