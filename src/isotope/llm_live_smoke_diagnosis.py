"""Low-sensitive diagnosis helpers for LLM live-smoke results."""

from __future__ import annotations

from typing import Any


def _legacy_deepseek_result(result: dict[str, Any]) -> dict[str, Any]:
    legacy = dict(result)
    reason_code = legacy.get("reason_code")
    if reason_code == "llm_tool_call_live_smoke_not_enabled":
        legacy["reason_code"] = "deepseek_tool_call_live_smoke_not_enabled"
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
            category="not_enabled",
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
    if reason_code == "llm_tool_not_enabled":
        return _diagnosis(
            category="tool_not_enabled",
            provider_request_started=False,
            approval_requested=False,
            codex_started=False,
            summary="the requested tool is not enabled in the model-facing catalog",
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
            category="tool_not_enabled",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the provider selected a tool that was not offered in this smoke",
            next_step="tighten the provider response or include the intended tool in the smoke config",
        )
    if reason_code == "model_tool_route_not_enabled":
        return _diagnosis(
            category="tool_route_not_enabled",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the model selected a tool that has no enabled bridge route",
            next_step="add route tests before exposing that tool to a real provider",
        )
    if reason_code in {"model_tool_not_enabled", "unknown_model_tool"}:
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
        next_step="inspect low-sensitive reason_code before widening the integration",
    )


def _llm_product_chat_diagnosis_for(result: dict[str, Any]) -> dict[str, Any]:
    reason_code = result.get("reason_code")
    status = result.get("status")
    cases = result.get("cases")
    if not isinstance(cases, list):
        cases = []

    if status == "skipped":
        return _product_chat_diagnosis(
            category="not_enabled",
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
            next_step="use this as a dev-only preflight before application-layer product chat wiring",
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


def _llm_product_chat_preflight_for(result: dict[str, Any]) -> dict[str, Any]:
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


def _maybe_diagnose_terminal_tool_missing_configuration(
    result: dict[str, Any],
    *,
    diagnose: bool,
) -> dict[str, Any]:
    if not diagnose:
        return result
    diagnosed = dict(result)
    diagnosed["diagnosis"] = _llm_terminal_tool_diagnosis_for(result)
    diagnosed["preflight"] = _llm_terminal_tool_preflight_for(diagnosed)
    return diagnosed


def _terminal_error_reason_summary(
    app: Any,
    run_id: str,
    tool_result: dict[str, Any],
) -> dict[str, str]:
    if tool_result.get("status") != "failed":
        return {}
    reason_code = _latest_action_failed_reason_code(app, run_id, tool_result.get("execution_id"))
    if reason_code is None:
        return {}
    return {"terminal_error_reason_code": reason_code}


def _latest_action_failed_reason_code(
    app: Any,
    run_id: str,
    execution_id: Any,
) -> str | None:
    try:
        events = app.server.get_events(run_id)
    except Exception:
        return None
    for event in reversed(events):
        if getattr(event, "event_type", None) != "action.failed":
            continue
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict):
            continue
        if isinstance(execution_id, str) and payload.get("execution_id") != execution_id:
            continue
        reason_code = payload.get("error_reason_code")
        if isinstance(reason_code, str) and reason_code:
            return reason_code
    return None


def _llm_terminal_tool_diagnosis_for(result: dict[str, Any]) -> dict[str, Any]:
    reason_code = result.get("reason_code")
    status = result.get("status")
    tool_name = result.get("tool_name")
    tool_result_status = result.get("tool_result_status")
    terminal_selected = tool_name == "terminal_exec" and reason_code != "llm_provider_selected_unoffered_tool"
    terminal_executed = isinstance(result.get("execution_id"), str)
    terminal_completed = tool_result_status == "completed" and result.get("artifact_ref_present") is True

    if status == "skipped":
        return _terminal_tool_diagnosis(
            category="not_enabled",
            provider_request_started=False,
            terminal_tool_selected=False,
            terminal_executed=False,
            terminal_completed=False,
            codex_started=False,
            summary="terminal-tool smoke is disabled",
            next_step="enable the smoke explicitly when a terminal provider check is intended",
        )
    if status == "missing_configuration":
        if reason_code == "llm_provider_unsupported":
            return _terminal_tool_diagnosis(
                category="unsupported_provider",
                provider_request_started=False,
                terminal_tool_selected=False,
                terminal_executed=False,
                terminal_completed=False,
                codex_started=False,
                summary="configured LLM provider is not supported by this boundary",
                next_step="configure a supported provider through the unified provider settings",
            )
        return _terminal_tool_diagnosis(
            category="missing_configuration",
            provider_request_started=False,
            terminal_tool_selected=False,
            terminal_executed=False,
            terminal_completed=False,
            codex_started=False,
            summary="LLM provider is not configured",
            next_step="configure ISOTOPE_LLM_PROVIDER and provider credentials before running terminal-tool smoke",
        )
    if status == "completed" and terminal_selected and terminal_completed:
        return _terminal_tool_diagnosis(
            category="ready",
            provider_request_started=True,
            terminal_tool_selected=True,
            terminal_executed=True,
            terminal_completed=True,
            codex_started=False,
            summary="provider selected terminal_exec and Isotope completed the terminal action",
            next_step="use this as a dev-only preflight before application-layer terminal wiring",
        )
    if reason_code == "llm_provider_request_failed":
        return _terminal_tool_diagnosis(
            category="provider_request_failed",
            provider_request_started=True,
            terminal_tool_selected=False,
            terminal_executed=False,
            terminal_completed=False,
            codex_started=False,
            summary="provider request failed before a usable terminal tool call was returned",
            next_step="check provider availability, credentials, network, or proxy settings",
        )
    if reason_code == "llm_tool_call_invalid_response":
        return _terminal_tool_diagnosis(
            category="provider_response_invalid",
            provider_request_started=True,
            terminal_tool_selected=False,
            terminal_executed=False,
            terminal_completed=False,
            codex_started=False,
            summary="provider response did not contain one valid terminal tool call",
            next_step="adjust the provider prompt or compatibility layer before app wiring",
        )
    if reason_code == "llm_provider_selected_unoffered_tool":
        return _terminal_tool_diagnosis(
            category="provider_selected_unoffered_tool",
            provider_request_started=True,
            terminal_tool_selected=False,
            terminal_executed=False,
            terminal_completed=False,
            codex_started=False,
            summary="provider selected a tool that was not offered by terminal-tool smoke",
            next_step="keep the provider tool menu limited to terminal_exec and inspect the model response",
        )
    if reason_code in {"invalid_model_tool_call", "llm_tool_not_enabled"}:
        return _terminal_tool_diagnosis(
            category="provider_tool_arguments_invalid",
            provider_request_started=True,
            terminal_tool_selected=terminal_selected,
            terminal_executed=False,
            terminal_completed=False,
            codex_started=False,
            summary="provider selected terminal_exec with invalid arguments",
            next_step="inspect the terminal_exec schema and prompt before app wiring",
        )
    if (
        reason_code in {"model_tool_policy_denied", "terminal_command_not_allowed"}
        or tool_result_status == "denied"
    ):
        return _terminal_tool_diagnosis(
            category="terminal_policy_denied",
            provider_request_started=True,
            terminal_tool_selected=terminal_selected,
            terminal_executed=terminal_executed,
            terminal_completed=False,
            codex_started=False,
            summary="Isotope policy rejected the selected terminal command",
            next_step="change the command request or add a deliberate policy profile test",
        )
    if tool_result_status == "failed":
        return _terminal_tool_diagnosis(
            category="terminal_execution_failed",
            provider_request_started=True,
            terminal_tool_selected=terminal_selected,
            terminal_executed=terminal_executed,
            terminal_completed=False,
            codex_started=False,
            summary="terminal_exec was selected but the terminal action failed",
            next_step="inspect the low-sensitive terminal_error_reason_code and action.failed event",
        )
    return _terminal_tool_diagnosis(
        category="terminal_tool_smoke_failed",
        provider_request_started=status != "missing_configuration",
        terminal_tool_selected=terminal_selected,
        terminal_executed=terminal_executed,
        terminal_completed=False,
        codex_started=False,
        summary="terminal-tool smoke stopped before all readiness checkpoints completed",
        next_step="inspect low-sensitive reason_code before widening application wiring",
    )


def _llm_terminal_tool_preflight_for(result: dict[str, Any]) -> dict[str, Any]:
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


def _terminal_tool_diagnosis(
    *,
    category: str,
    provider_request_started: bool,
    terminal_tool_selected: bool,
    terminal_executed: bool,
    terminal_completed: bool,
    codex_started: bool,
    summary: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "provider_request_started": provider_request_started,
        "terminal_tool_selected": terminal_tool_selected,
        "terminal_executed": terminal_executed,
        "terminal_completed": terminal_completed,
        "codex_started": codex_started,
        "summary": summary,
        "next_step": next_step,
    }


def _diagnosis_for(result: dict[str, Any]) -> dict[str, Any]:
    reason_code = result.get("reason_code")
    status = result.get("status")
    if status == "skipped":
        return _diagnosis(
            category="not_enabled",
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
    if reason_code == "llm_tool_not_enabled":
        return _diagnosis(
            category="tool_not_enabled",
            provider_request_started=False,
            approval_requested=False,
            codex_started=False,
            summary="the requested tool is not enabled in the model-facing catalog",
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
            category="tool_not_enabled",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the provider selected a tool that was not offered in this smoke",
            next_step="tighten the provider response or include the intended tool in the smoke config",
        )
    if reason_code == "model_tool_route_not_enabled":
        return _diagnosis(
            category="tool_route_not_enabled",
            provider_request_started=True,
            approval_requested=False,
            codex_started=False,
            summary="the model selected a tool that has no enabled bridge route",
            next_step="add route tests before exposing that tool to a real provider",
        )
    if reason_code in {"model_tool_not_enabled", "unknown_model_tool"}:
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
        next_step="inspect low-sensitive reason_code before widening the integration",
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
