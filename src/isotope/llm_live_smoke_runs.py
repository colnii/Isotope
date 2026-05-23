"""Run and diagnose LLM live smoke flows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .platform.errors import IsotopeError
from .llm.provider import (
    ToolCallProvider,
    resolve_llm_tool_call_provider,
    submit_llm_tool_call,
)
from .llm_live_smoke_cases import (
    _messages,
    _run_llm_product_chat_live_smoke_cases,
    _terminal_tool_messages,
)
from .llm_live_smoke_config import (
    DeepSeekToolCallLiveSmokeConfig,
    LLMProductChatLiveSmokeConfig,
    LLMTerminalToolLiveSmokeConfig,
    LLMToolCallLiveSmokeConfig,
)
from .llm_live_smoke_diagnosis import (
    _diagnosis_for,
    _legacy_deepseek_result,
    _llm_diagnosis_for,
    _llm_product_chat_diagnosis_for,
    _llm_product_chat_preflight_for,
    _llm_terminal_tool_diagnosis_for,
    _llm_terminal_tool_preflight_for,
    _terminal_error_reason_summary,
)


def run_llm_tool_call_live_smoke(
    app: Any,
    run_id: str,
    *,
    config: LLMToolCallLiveSmokeConfig | None = None,
    provider: ToolCallProvider | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run a deliberate provider tool-call smoke and return low-sensitive status."""

    resolved_config = config or LLMToolCallLiveSmokeConfig()
    if not isinstance(resolved_config, LLMToolCallLiveSmokeConfig):
        raise TypeError("config must be a LLMToolCallLiveSmokeConfig")
    if not resolved_config.enabled:
        return {
            "status": "skipped",
            "reason_code": "llm_tool_call_live_smoke_not_enabled",
            "provider": "auto",
            "tool_name": resolved_config.tool_name,
        }

    effective_provider = provider
    if effective_provider is None:
        resolution = resolve_llm_tool_call_provider(environ)
        if resolution.provider is None:
            return {
                "status": "missing_configuration",
                "reason_code": resolution.reason_code,
                "provider": resolution.provider_name,
                "tool_name": resolved_config.tool_name,
            }
        effective_provider = resolution.provider

    try:
        llm_result = submit_llm_tool_call(
            app,
            run_id,
            effective_provider,
            _messages(resolved_config),
            max_tokens=resolved_config.max_tokens,
            tool_names=(resolved_config.tool_name,),
        )
    except IsotopeError as exc:
        return {
            "status": "failed",
            "reason_code": exc.code,
            "provider": _safe_provider_name(effective_provider),
            "tool_name": resolved_config.tool_name,
            "category": exc.category,
            "retryable": exc.retryable,
        }

    tool_result = llm_result.get("tool_result")
    if not isinstance(tool_result, dict):
        tool_result = {}
    return {
        "status": "completed",
        "reason_code": "llm_tool_call_live_smoke_completed",
        "provider": llm_result.get("provider"),
        "model": llm_result.get("model"),
        "finish_reason": llm_result.get("finish_reason"),
        "tool_name": llm_result.get("tool_name"),
        "provider_tool_call_id": llm_result.get("provider_tool_call_id"),
        "tool_result_status": tool_result.get("status"),
        "approval_id": tool_result.get("approval_id"),
        "proposal_id": tool_result.get("proposal_id"),
        "decision_id": tool_result.get("decision_id"),
        "usage": _safe_usage(llm_result.get("usage")),
    }


def run_llm_product_chat_live_smoke(
    app: Any,
    *,
    config: LLMProductChatLiveSmokeConfig | None = None,
    provider: ToolCallProvider | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the product-chat route through final answer, approval pause, and resume."""

    resolved_config = config or LLMProductChatLiveSmokeConfig()
    if not isinstance(resolved_config, LLMProductChatLiveSmokeConfig):
        raise TypeError("config must be a LLMProductChatLiveSmokeConfig")
    if not resolved_config.enabled:
        return {
            "status": "skipped",
            "reason_code": "llm_product_chat_live_smoke_not_enabled",
            "provider": "auto",
            "case_count": 0,
            "cases": [],
        }

    original_provider = getattr(app, "llm_tool_call_provider", None)
    effective_provider = provider or original_provider
    if effective_provider is None:
        resolution = resolve_llm_tool_call_provider(environ)
        if resolution.provider is None:
            return {
                "status": "missing_configuration",
                "reason_code": resolution.reason_code,
                "provider": resolution.provider_name,
                "case_count": 0,
                "cases": [],
            }
        effective_provider = resolution.provider

    changed_provider = provider is not None or original_provider is None
    if changed_provider:
        app.llm_tool_call_provider = effective_provider
    try:
        return _run_llm_product_chat_live_smoke_cases(
            app,
            resolved_config,
            provider_name=_safe_provider_name(effective_provider),
        )
    finally:
        if changed_provider:
            app.llm_tool_call_provider = original_provider


def run_llm_terminal_tool_live_smoke(
    app: Any,
    run_id: str,
    *,
    config: LLMTerminalToolLiveSmokeConfig | None = None,
    provider: ToolCallProvider | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Ask a configured provider to choose only terminal_exec, then execute it safely."""

    resolved_config = config or LLMTerminalToolLiveSmokeConfig()
    if not isinstance(resolved_config, LLMTerminalToolLiveSmokeConfig):
        raise TypeError("config must be a LLMTerminalToolLiveSmokeConfig")
    if not resolved_config.enabled:
        return {
            "status": "skipped",
            "reason_code": "llm_terminal_tool_live_smoke_not_enabled",
            "provider": "auto",
            "tool_name": "terminal_exec",
            "codex_call_count": 0,
        }

    effective_provider = provider
    if effective_provider is None:
        resolution = resolve_llm_tool_call_provider(environ)
        if resolution.provider is None:
            return {
                "status": "missing_configuration",
                "reason_code": resolution.reason_code,
                "provider": resolution.provider_name,
                "tool_name": "terminal_exec",
            }
        effective_provider = resolution.provider

    try:
        llm_result = submit_llm_tool_call(
            app,
            run_id,
            effective_provider,
            _terminal_tool_messages(resolved_config),
            max_tokens=resolved_config.max_tokens,
            tool_names=("terminal_exec",),
        )
    except IsotopeError as exc:
        return {
            "status": "failed",
            "reason_code": exc.code,
            "provider": _safe_provider_name(effective_provider),
            "tool_name": "terminal_exec",
            "category": exc.category,
            "retryable": exc.retryable,
            "codex_call_count": 0,
        }

    tool_result = llm_result.get("tool_result")
    if not isinstance(tool_result, dict):
        tool_result = {}
    return {
        "status": "completed",
        "reason_code": "llm_terminal_tool_live_smoke_completed",
        "provider": llm_result.get("provider"),
        "model": llm_result.get("model"),
        "finish_reason": llm_result.get("finish_reason"),
        "tool_name": llm_result.get("tool_name"),
        "provider_tool_call_id": llm_result.get("provider_tool_call_id"),
        "tool_result_status": tool_result.get("status"),
        "execution_id": tool_result.get("execution_id"),
        "proposal_id": tool_result.get("proposal_id"),
        "decision_id": tool_result.get("decision_id"),
        "artifact_ref_present": isinstance(tool_result.get("artifact_ref"), dict),
        **_terminal_error_reason_summary(app, run_id, tool_result),
        "usage": _safe_usage(llm_result.get("usage")),
        "codex_call_count": 0,
    }


def run_deepseek_tool_call_live_smoke(
    app: Any,
    run_id: str,
    *,
    config: DeepSeekToolCallLiveSmokeConfig | None = None,
    provider: ToolCallProvider | None = None,
) -> dict[str, Any]:
    """Backward-compatible DeepSeek-named wrapper for the generic LLM smoke."""

    result = run_llm_tool_call_live_smoke(
        app,
        run_id,
        config=config,
        provider=provider,
    )
    return _legacy_deepseek_result(result)


def diagnose_llm_tool_call_live_smoke(
    app: Any,
    run_id: str,
    *,
    config: LLMToolCallLiveSmokeConfig | None = None,
    provider: ToolCallProvider | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the provider smoke and add low-sensitive readiness diagnostics."""

    result = run_llm_tool_call_live_smoke(
        app,
        run_id,
        config=config,
        provider=provider,
        environ=environ,
    )
    diagnosed = dict(result)
    diagnosed["diagnosis"] = _llm_diagnosis_for(result)
    return diagnosed


def diagnose_llm_product_chat_live_smoke(
    app: Any,
    *,
    config: LLMProductChatLiveSmokeConfig | None = None,
    provider: ToolCallProvider | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the product-chat smoke and add low-sensitive readiness diagnostics."""

    result = run_llm_product_chat_live_smoke(
        app,
        config=config,
        provider=provider,
        environ=environ,
    )
    diagnosed = dict(result)
    diagnosed["diagnosis"] = _llm_product_chat_diagnosis_for(result)
    diagnosed["preflight"] = _llm_product_chat_preflight_for(diagnosed)
    return diagnosed


def diagnose_llm_terminal_tool_live_smoke(
    app: Any,
    run_id: str,
    *,
    config: LLMTerminalToolLiveSmokeConfig | None = None,
    provider: ToolCallProvider | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the terminal-tool smoke and add low-sensitive readiness diagnostics."""

    result = run_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=config,
        provider=provider,
        environ=environ,
    )
    diagnosed = dict(result)
    diagnosed["diagnosis"] = _llm_terminal_tool_diagnosis_for(result)
    diagnosed["preflight"] = _llm_terminal_tool_preflight_for(diagnosed)
    return diagnosed


def diagnose_deepseek_tool_call_live_smoke(
    app: Any,
    run_id: str,
    *,
    config: DeepSeekToolCallLiveSmokeConfig | None = None,
    provider: ToolCallProvider | None = None,
) -> dict[str, Any]:
    """Backward-compatible DeepSeek-named diagnosis wrapper."""

    result = run_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=config,
        provider=provider,
    )
    diagnosed = dict(result)
    diagnosed["diagnosis"] = _diagnosis_for(result)
    return diagnosed


def _safe_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and (isinstance(item, (str, int, float, bool)) or item is None)
    }


def _safe_provider_name(provider: ToolCallProvider | None) -> str:
    name = getattr(provider, "provider", None)
    if isinstance(name, str) and name:
        return name[:64]
    return "deepseek"
