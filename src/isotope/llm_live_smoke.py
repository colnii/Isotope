"""Opt-in live smoke helper for LLM provider tool-call selection."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .platform.errors import IsotopeError
from .features.chat.flow import (
    build_llm_product_chat_entry_resume_state,
    mark_llm_product_chat_entry_state_resumed,
    submit_llm_product_chat_entry_resume,
    submit_llm_product_chat_user_message_with_preflight,
    summarize_llm_product_chat_entry_response,
    validate_llm_product_chat_entry_resume_state,
)
from .llm.provider import (
    LLMFinalAnswerResponse,
    LLMToolCall,
    LLMToolCallResponse,
    ToolCallProvider,
    resolve_llm_tool_call_provider,
    submit_llm_tool_call,
)


DEFAULT_LLM_LIVE_SMOKE_PROMPT = (
    "Call the codex_task tool exactly once. "
    "Use prompt 'Reply exactly ISOTOPE_LLM_TOOL_CALL_SMOKE_OK.' "
    "Use summary 'LLM tool call live smoke'."
)
DEFAULT_DEEPSEEK_LIVE_SMOKE_PROMPT = DEFAULT_LLM_LIVE_SMOKE_PROMPT
DEFAULT_LLM_PRODUCT_CHAT_DIRECT_PROMPT = "Reply exactly ISOTOPE_LLM_PRODUCT_CHAT_DIRECT_OK."
DEFAULT_LLM_PRODUCT_CHAT_TOOL_PROMPT = (
    "Call the codex_task tool exactly once. "
    "Use prompt 'Reply exactly ISOTOPE_LLM_PRODUCT_CHAT_TOOL_OK.' "
    "Use summary 'LLM product chat live smoke'."
)
DEFAULT_LLM_PRODUCT_CHAT_RESUME_PROMPT = (
    "Use the tool result already provided in this conversation and reply with a short final answer."
)
DEFAULT_LLM_TERMINAL_TOOL_SMOKE_PROMPT = (
    "Call the terminal_exec tool exactly once. "
    "Use argv ['printf', 'ISOTOPE_LLM_TERMINAL_TOOL_SMOKE_OK']. "
    "Use summary 'LLM terminal tool live smoke'."
)


@dataclass(frozen=True)
class LLMToolCallLiveSmokeConfig:
    enabled: bool = False
    prompt: str = DEFAULT_LLM_LIVE_SMOKE_PROMPT
    max_tokens: int = 128
    tool_name: str = "codex_task"

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")
        _non_empty_string("prompt", self.prompt)
        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        _non_empty_string("tool_name", self.tool_name)


DeepSeekToolCallLiveSmokeConfig = LLMToolCallLiveSmokeConfig


@dataclass(frozen=True)
class LLMTerminalToolLiveSmokeConfig:
    enabled: bool = False
    prompt: str = DEFAULT_LLM_TERMINAL_TOOL_SMOKE_PROMPT
    max_tokens: int = 128

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")
        _non_empty_string("prompt", self.prompt)
        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")


@dataclass(frozen=True)
class LLMProductChatLiveSmokeConfig:
    enabled: bool = False
    direct_prompt: str = DEFAULT_LLM_PRODUCT_CHAT_DIRECT_PROMPT
    tool_prompt: str = DEFAULT_LLM_PRODUCT_CHAT_TOOL_PROMPT
    resume_prompt: str = DEFAULT_LLM_PRODUCT_CHAT_RESUME_PROMPT
    max_tokens: int = 128

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")
        _non_empty_string("direct_prompt", self.direct_prompt)
        _non_empty_string("tool_prompt", self.tool_prompt)
        _non_empty_string("resume_prompt", self.resume_prompt)
        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")


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


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run low-sensitive developer smoke commands."""

    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.command == "terminal-tool":
        return _run_terminal_tool_smoke_command(args, environ=environ)
    if args.command == "product-chat":
        return _run_product_chat_smoke_command(args, environ=environ)
    if args.command == "product-chat-entry":
        return _run_product_chat_entry_command(args, environ=environ)
    parser.print_help()
    return 2


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


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Isotope LLM developer smoke checks.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    terminal_tool = subparsers.add_parser(
        "terminal-tool",
        help="Run a provider smoke that exposes only terminal_exec.",
    )
    terminal_tool.add_argument("--json", action="store_true", help="Print JSON output.")
    terminal_tool.add_argument(
        "--fake-provider",
        action="store_true",
        help="Use a deterministic fake provider instead of configured ISOTOPE_LLM_* provider settings.",
    )
    terminal_tool.add_argument(
        "--diagnose",
        action="store_true",
        help="Include a low-sensitive readiness diagnosis in the smoke result.",
    )
    terminal_tool.add_argument(
        "--root",
        help="Optional smoke root. Defaults to a temporary directory.",
    )
    terminal_tool.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Max tokens passed to the provider.",
    )
    product_chat = subparsers.add_parser(
        "product-chat",
        help="Run the product-chat provider smoke with a fake Codex runner.",
    )
    product_chat.add_argument("--json", action="store_true", help="Print JSON output.")
    product_chat.add_argument(
        "--fake-provider",
        action="store_true",
        help="Use a deterministic fake provider instead of configured ISOTOPE_LLM_* provider settings.",
    )
    product_chat.add_argument(
        "--diagnose",
        action="store_true",
        help="Include a low-sensitive readiness diagnosis in the smoke result.",
    )
    product_chat.add_argument(
        "--root",
        help="Optional smoke root. Defaults to a temporary directory.",
    )
    product_chat.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Max tokens passed to the provider.",
    )
    product_chat.add_argument(
        "--codex-executable",
        default="codex",
        help="Codex executable name recorded in the fake-runner app config.",
    )
    product_chat.add_argument(
        "--timeout-seconds",
        type=int,
        default=17,
        help="Codex task timeout recorded in the fake-runner app config.",
    )
    product_chat.add_argument(
        "--max-output-bytes",
        type=int,
        default=4096,
        help="Codex task output cap recorded in the fake-runner app config.",
    )
    product_chat_entry = subparsers.add_parser(
        "product-chat-entry",
        help="Run product-chat preflight, then submit one user message if ready.",
    )
    product_chat_entry.add_argument("--json", action="store_true", help="Print JSON output.")
    product_chat_entry.add_argument(
        "--fake-provider",
        action="store_true",
        help="Use a deterministic fake provider instead of configured ISOTOPE_LLM_* provider settings.",
    )
    product_chat_entry.add_argument(
        "--fake-entry-pending",
        action="store_true",
        help="With --fake-provider, make the entry turn select codex_task and save a resumable pending state.",
    )
    product_chat_entry.add_argument(
        "--message",
        required=False,
        help="One user message to submit after product-chat preflight passes.",
    )
    product_chat_entry.add_argument(
        "--state-file",
        help="Optional local JSON file for resuming a pending product-chat entry approval.",
    )
    product_chat_entry.add_argument(
        "--resume-state",
        help="Resume a pending product-chat entry from a local JSON state file.",
    )
    product_chat_entry.add_argument(
        "--root",
        help="Optional command root. Defaults to a temporary directory.",
    )
    product_chat_entry.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Max tokens passed to the provider.",
    )
    product_chat_entry.add_argument(
        "--codex-executable",
        default="codex",
        help="Codex executable name recorded in the fake-runner app config.",
    )
    product_chat_entry.add_argument(
        "--timeout-seconds",
        type=int,
        default=17,
        help="Codex task timeout recorded in the fake-runner app config.",
    )
    product_chat_entry.add_argument(
        "--max-output-bytes",
        type=int,
        default=4096,
        help="Codex task output cap recorded in the fake-runner app config.",
    )
    return parser


def _run_terminal_tool_smoke_command(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None,
) -> int:
    root_arg = getattr(args, "root", None)
    if root_arg:
        root = Path(root_arg)
        root.mkdir(parents=True, exist_ok=True)
        return _run_terminal_tool_smoke_command_at_root(args, root, environ=environ)
    with tempfile.TemporaryDirectory(prefix="isotope-llm-terminal-tool-smoke-") as tmp:
        return _run_terminal_tool_smoke_command_at_root(args, Path(tmp), environ=environ)


def _run_terminal_tool_smoke_command_at_root(
    args: argparse.Namespace,
    root: Path,
    *,
    environ: Mapping[str, str] | None,
) -> int:
    from .interfaces.http import create_http_app

    provider = _fake_terminal_tool_provider() if args.fake_provider else None
    if provider is None:
        resolution = resolve_llm_tool_call_provider(environ)
        if resolution.provider is None:
            payload = {
                "command": "llm_terminal_tool_live_smoke",
                "result": _maybe_diagnose_terminal_tool_missing_configuration(
                    {
                        "status": "missing_configuration",
                        "reason_code": resolution.reason_code,
                        "provider": resolution.provider_name,
                        "tool_name": "terminal_exec",
                    },
                    diagnose=args.diagnose,
                ),
                "provider_call_count": 0,
                "codex_call_count": 0,
            }
            if args.json:
                print(json.dumps(payload, sort_keys=True))
            else:
                _print_terminal_tool_smoke_plain(payload)
            return 2
        provider = resolution.provider

    app = create_http_app(root)
    run_id = _create_smoke_run(app, "llm terminal tool live smoke")
    config = LLMTerminalToolLiveSmokeConfig(enabled=True, max_tokens=args.max_tokens)
    if args.diagnose:
        result = diagnose_llm_terminal_tool_live_smoke(
            app,
            run_id,
            config=config,
            provider=provider,
            environ=environ,
        )
    else:
        result = run_llm_terminal_tool_live_smoke(
            app,
            run_id,
            config=config,
            provider=provider,
            environ=environ,
        )
    payload = {
        "command": "llm_terminal_tool_live_smoke",
        "result": result,
        "provider_call_count": _provider_call_count(provider),
        "codex_call_count": 0,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        _print_terminal_tool_smoke_plain(payload)
    return _terminal_tool_smoke_exit_code(result)


def _run_product_chat_smoke_command(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None,
) -> int:
    root_arg = getattr(args, "root", None)
    if root_arg:
        root = Path(root_arg)
        root.mkdir(parents=True, exist_ok=True)
        return _run_product_chat_smoke_command_at_root(args, root, environ=environ)
    with tempfile.TemporaryDirectory(prefix="isotope-llm-product-chat-smoke-") as tmp:
        return _run_product_chat_smoke_command_at_root(args, Path(tmp), environ=environ)


def _run_product_chat_smoke_command_at_root(
    args: argparse.Namespace,
    root: Path,
    *,
    environ: Mapping[str, str] | None,
) -> int:
    from .integrations.codex.server import CodexCliServerConfig
    from .interfaces.http import create_llm_product_chat_http_app

    provider = _fake_product_chat_provider() if args.fake_provider else None
    runner = _RecordingFakeCodexRunner()
    app = create_llm_product_chat_http_app(
        root,
        config=CodexCliServerConfig(
            workspace_root=str(root / "workspace"),
            executable=args.codex_executable,
            timeout_seconds=args.timeout_seconds,
            max_output_bytes=args.max_output_bytes,
        ),
        provider=provider,
        process_runner=runner,
        executable_resolver=_fake_codex_executable_resolver,
    )
    config = LLMProductChatLiveSmokeConfig(
        enabled=True,
        max_tokens=args.max_tokens,
    )
    if args.diagnose:
        result = diagnose_llm_product_chat_live_smoke(
            app,
            config=config,
            environ=environ,
        )
    else:
        result = run_llm_product_chat_live_smoke(
            app,
            config=config,
            environ=environ,
        )
    payload = {
        "command": "llm_product_chat_live_smoke",
        "codex_runner": "fake",
        "result": result,
        "runner_call_count": len(runner.calls),
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        _print_product_chat_smoke_plain(payload)
    return _product_chat_smoke_exit_code(result)


def _run_product_chat_entry_command(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None,
) -> int:
    if getattr(args, "resume_state", None):
        invalid_resume_mode_payload = _invalid_product_chat_entry_resume_mode_payload(args)
        if invalid_resume_mode_payload is not None:
            if args.json:
                print(json.dumps(invalid_resume_mode_payload, sort_keys=True))
            else:
                _print_product_chat_entry_plain(invalid_resume_mode_payload)
            return 2
        return _run_product_chat_entry_resume_command(args, environ=environ)

    invalid_mode_payload = _invalid_product_chat_entry_mode_payload(args)
    if invalid_mode_payload is not None:
        if args.json:
            print(json.dumps(invalid_mode_payload, sort_keys=True))
        else:
            _print_product_chat_entry_plain(invalid_mode_payload)
        return 2

    invalid_payload = _invalid_product_chat_entry_payload(args.message)
    if invalid_payload is not None:
        if args.json:
            print(json.dumps(invalid_payload, sort_keys=True))
        else:
            _print_product_chat_entry_plain(invalid_payload)
        return 2

    root_arg = getattr(args, "root", None)
    state_file = _optional_path(getattr(args, "state_file", None))
    if root_arg:
        root = Path(root_arg)
        try:
            _prepare_product_chat_entry_root(root)
        except IsotopeError as exc:
            payload = _product_chat_entry_error_payload(exc, command="llm_product_chat_app_entry")
            if args.json:
                print(json.dumps(payload, sort_keys=True))
            else:
                _print_product_chat_entry_resume_plain(payload)
            return _product_chat_entry_exit_code(payload)
        return _run_product_chat_entry_command_at_root(args, root, environ=environ)
    if state_file is not None:
        root = state_file.parent / f"{state_file.stem}.root"
        try:
            _prepare_product_chat_entry_root(root)
        except IsotopeError as exc:
            payload = _product_chat_entry_error_payload(exc, command="llm_product_chat_app_entry")
            if args.json:
                print(json.dumps(payload, sort_keys=True))
            else:
                _print_product_chat_entry_resume_plain(payload)
            return _product_chat_entry_exit_code(payload)
        return _run_product_chat_entry_command_at_root(args, root, environ=environ)
    with tempfile.TemporaryDirectory(prefix="isotope-llm-product-chat-entry-") as tmp:
        return _run_product_chat_entry_command_at_root(args, Path(tmp), environ=environ)


def _run_product_chat_entry_command_at_root(
    args: argparse.Namespace,
    root: Path,
    *,
    environ: Mapping[str, str] | None,
) -> int:
    from .integrations.codex.server import CodexCliServerConfig
    from .interfaces.http import create_llm_product_chat_http_app

    if args.fake_provider:
        provider = (
            _fake_product_chat_entry_provider(entry_pending=True)
            if args.fake_entry_pending
            else _fake_product_chat_entry_provider()
        )
    else:
        provider = None
    if provider is None:
        resolution = resolve_llm_tool_call_provider(environ)
        provider = resolution.provider
    runner = _RecordingFakeCodexRunner()
    app = create_llm_product_chat_http_app(
        root,
        config=CodexCliServerConfig(
            workspace_root=str(root / "workspace"),
            executable=args.codex_executable,
            timeout_seconds=args.timeout_seconds,
            max_output_bytes=args.max_output_bytes,
        ),
        provider=provider,
        process_runner=runner,
        executable_resolver=_fake_codex_executable_resolver,
    )
    config = LLMProductChatLiveSmokeConfig(
        enabled=True,
        max_tokens=args.max_tokens,
    )
    preflight_result = diagnose_llm_product_chat_live_smoke(
        app,
        config=config,
        provider=provider,
        environ=environ,
    )
    preflight = preflight_result.get("preflight")
    if not isinstance(preflight, dict):
        preflight = _preflight_from_result(preflight_result)

    if preflight.get("ready") is True:
        run_id = _create_smoke_run(app, "llm product chat app entry command")
        response = submit_llm_product_chat_user_message_with_preflight(
            app,
            run_id,
            preflight=preflight,
            user_message=args.message,
            max_tokens=args.max_tokens,
            complete_run=_entry_initial_complete_run(args),
        )
        entry = summarize_llm_product_chat_entry_response(response)
        try:
            pending_state = _maybe_write_product_chat_entry_state(
                response,
                root=root,
                run_id=run_id,
                preflight=preflight,
                state_file=_optional_path(getattr(args, "state_file", None)),
            )
        except IsotopeError as exc:
            payload = _product_chat_entry_error_payload(exc, command="llm_product_chat_app_entry")
            if args.json:
                print(json.dumps(payload, sort_keys=True))
            else:
                _print_product_chat_entry_resume_plain(payload)
            return _product_chat_entry_exit_code(payload)
    else:
        entry = _blocked_product_chat_entry_summary(preflight)
        pending_state = {}

    payload = {
        "command": "llm_product_chat_app_entry",
        "codex_runner": "fake",
        "preflight": preflight,
        "entry": entry,
        "runner_call_count": len(runner.calls),
    }
    if pending_state:
        payload["pending_state"] = pending_state
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        _print_product_chat_entry_plain(payload)
    return _product_chat_entry_exit_code(payload)


def _run_product_chat_entry_resume_command(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None,
) -> int:
    from .integrations.codex.server import CodexCliServerConfig
    from .interfaces.http import create_llm_product_chat_http_app

    state_file = Path(args.resume_state)
    try:
        state = _load_product_chat_entry_state(state_file)
    except IsotopeError as exc:
        payload = _product_chat_entry_error_payload(exc, command="llm_product_chat_app_entry_resume")
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            _print_product_chat_entry_resume_plain(payload)
        return _product_chat_entry_exit_code(payload)
    try:
        _validate_product_chat_entry_resume_root(args, state)
    except IsotopeError as exc:
        payload = _product_chat_entry_error_payload(exc, command="llm_product_chat_app_entry_resume")
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            _print_product_chat_entry_resume_plain(payload)
        return _product_chat_entry_exit_code(payload)
    root = Path(getattr(args, "root", None) or state["root"])
    try:
        _prepare_product_chat_entry_root(root)
    except IsotopeError as exc:
        payload = _product_chat_entry_error_payload(
            exc,
            command="llm_product_chat_app_entry_resume",
        )
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            _print_product_chat_entry_resume_plain(payload)
        return _product_chat_entry_exit_code(payload)

    provider = _fake_product_chat_entry_provider() if args.fake_provider else None
    if provider is None:
        resolution = resolve_llm_tool_call_provider(environ)
        provider = resolution.provider
    runner = _RecordingFakeCodexRunner()
    app = create_llm_product_chat_http_app(
        root,
        config=CodexCliServerConfig(
            workspace_root=str(root / "workspace"),
            executable=args.codex_executable,
            timeout_seconds=args.timeout_seconds,
            max_output_bytes=args.max_output_bytes,
        ),
        provider=provider,
        process_runner=runner,
        executable_resolver=_fake_codex_executable_resolver,
    )

    try:
        result = submit_llm_product_chat_entry_resume(
            app,
            state,
            messages=_product_chat_messages(DEFAULT_LLM_PRODUCT_CHAT_RESUME_PROMPT, mode="resume"),
            max_tokens=args.max_tokens,
            resolver="llm_live_smoke_cli",
        )
    except IsotopeError as exc:
        payload = _product_chat_entry_error_payload(
            exc,
            command="llm_product_chat_app_entry_resume",
        )
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            _print_product_chat_entry_resume_plain(payload)
        return _product_chat_entry_exit_code(payload)
    approval = result["approval"]
    entry = result["entry"]
    try:
        _mark_product_chat_entry_state_resumed(
            state_file,
            state,
            approval=approval,
            entry=entry,
        )
    except IsotopeError as exc:
        payload = _product_chat_entry_error_payload(
            exc,
            command="llm_product_chat_app_entry_resume",
            runner_call_count=len(runner.calls),
        )
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            _print_product_chat_entry_resume_plain(payload)
        return _product_chat_entry_exit_code(payload)

    payload = {
        "command": "llm_product_chat_app_entry_resume",
        "codex_runner": "fake",
        "approval": approval,
        "entry": entry,
        "runner_call_count": len(runner.calls),
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        _print_product_chat_entry_resume_plain(payload)
    return _product_chat_entry_exit_code({"entry": entry})


class _RecordingFakeCodexRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: Any, **kwargs: Any) -> "_FakeCompletedProcess":
        self.calls.append({"argv_count": len(list(argv)), "timeout": kwargs.get("timeout")})
        return _FakeCompletedProcess()


class _FakeCompletedProcess:
    returncode = 0
    stdout = '{"event":"task_complete","secret":"PRODUCT_CHAT_CLI_FAKE_STDOUT_SHOULD_NOT_LEAK"}\n'
    stderr = ""


def _fake_codex_executable_resolver(executable: str) -> str | None:
    if not isinstance(executable, str) or not executable:
        return None
    if "/" in executable or "\\" in executable:
        return None
    return str(Path("/tmp/isotope-fake-codex-bin") / executable)


class _SequencedProductChatSmokeProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(
        self,
        *,
        include_entry_response: bool = False,
        entry_pending: bool = False,
    ) -> None:
        self._responses: list[LLMFinalAnswerResponse | LLMToolCallResponse] = [
            LLMFinalAnswerResponse(
                provider=self.provider,
                model=self.model,
                finish_reason="stop",
                usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
                content="Direct product-chat smoke answer.",
            ),
            LLMToolCallResponse(
                provider=self.provider,
                model=self.model,
                finish_reason="tool_calls",
                usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
                tool_call=LLMToolCall(
                    call_id="call_product_chat_cli_fake",
                    tool_name="codex_task",
                    arguments={
                        "prompt": "PRODUCT_CHAT_CLI_FAKE_PROMPT_SHOULD_NOT_LEAK",
                        "summary": "product chat CLI fake provider task",
                    },
                ),
            ),
            LLMFinalAnswerResponse(
                provider=self.provider,
                model=self.model,
                finish_reason="stop",
                usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
                content="Final product-chat smoke answer.",
            ),
        ]
        if include_entry_response and entry_pending:
            self._responses.append(
                LLMToolCallResponse(
                    provider=self.provider,
                    model=self.model,
                    finish_reason="tool_calls",
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    tool_call=LLMToolCall(
                        call_id="call_product_chat_entry_cli_fake",
                        tool_name="codex_task",
                        arguments={
                            "prompt": "PRODUCT_CHAT_ENTRY_CLI_PENDING_PROMPT_SHOULD_NOT_LEAK",
                            "summary": "product chat entry CLI fake pending task",
                        },
                    ),
                )
            )
        elif include_entry_response:
            self._responses.append(
                LLMFinalAnswerResponse(
                    provider=self.provider,
                    model=self.model,
                    finish_reason="stop",
                    usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
                    content="PRODUCT_CHAT_ENTRY_CLI_FINAL_ANSWER_SHOULD_NOT_LEAK",
                )
            )

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMFinalAnswerResponse | LLMToolCallResponse:
        del messages, tools, max_tokens
        if not self._responses:
            raise ValueError("fake product-chat smoke provider exhausted")
        return self._responses.pop(0)


def _fake_product_chat_provider() -> _SequencedProductChatSmokeProvider:
    return _SequencedProductChatSmokeProvider()


def _fake_product_chat_entry_provider(
    *,
    entry_pending: bool = False,
) -> _SequencedProductChatSmokeProvider:
    return _SequencedProductChatSmokeProvider(
        include_entry_response=True,
        entry_pending=entry_pending,
    )


class _FakeTerminalToolProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self) -> None:
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
        return LLMToolCallResponse(
            provider=self.provider,
            model=self.model,
            finish_reason="tool_calls",
            usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            tool_call=LLMToolCall(
                call_id="call_terminal_tool_cli_fake",
                tool_name="terminal_exec",
                arguments={
                    "argv": ["printf", "TERMINAL_TOOL_CLI_FAKE_STDOUT_SHOULD_NOT_LEAK"],
                    "summary": "terminal tool CLI fake provider command",
                },
            ),
        )


def _fake_terminal_tool_provider() -> _FakeTerminalToolProvider:
    return _FakeTerminalToolProvider()


def _provider_call_count(provider: ToolCallProvider | None) -> int:
    calls = getattr(provider, "calls", None)
    if isinstance(calls, list):
        return len(calls)
    return 0


def _print_terminal_tool_smoke_plain(payload: dict[str, Any]) -> None:
    result = payload.get("result")
    if not isinstance(result, dict):
        result = {}
    print(f"command: {payload.get('command')}")
    print(f"status: {result.get('status')}")
    print(f"reason_code: {result.get('reason_code')}")
    print(f"provider: {result.get('provider')}")
    if result.get("model"):
        print(f"model: {result.get('model')}")
    print(f"tool_name: {result.get('tool_name')}")
    print(f"tool_result_status: {result.get('tool_result_status')}")
    print(f"artifact_ref_present: {str(result.get('artifact_ref_present')).lower()}")
    print(f"provider_call_count: {payload.get('provider_call_count')}")
    print(f"codex_call_count: {payload.get('codex_call_count')}")
    diagnosis = result.get("diagnosis")
    if isinstance(diagnosis, dict):
        print(f"diagnosis: {diagnosis.get('category')}")
        print(f"diagnosis_summary: {diagnosis.get('summary')}")
        print(f"diagnosis_next_step: {diagnosis.get('next_step')}")
    preflight = result.get("preflight")
    if isinstance(preflight, dict):
        print(f"preflight_ready: {str(preflight.get('ready')).lower()}")
        print(f"preflight_gate: {preflight.get('gate')}")


def _print_product_chat_smoke_plain(payload: dict[str, Any]) -> None:
    result = payload.get("result")
    if not isinstance(result, dict):
        result = {}
    print(f"command: {payload.get('command')}")
    print(f"status: {result.get('status')}")
    print(f"reason_code: {result.get('reason_code')}")
    print(f"provider: {result.get('provider')}")
    if result.get("model"):
        print(f"model: {result.get('model')}")
    print(f"codex_runner: {payload.get('codex_runner')}")
    print(f"runner_call_count: {payload.get('runner_call_count')}")
    print(f"case_count: {result.get('case_count')}")
    cases = result.get("cases")
    if isinstance(cases, list) and cases:
        print("cases:")
        for case in cases:
            if not isinstance(case, dict):
                continue
            print(
                "- "
                f"{case.get('case')}: "
                f"{case.get('status')} "
                f"(http_status={case.get('http_status')}, run_state={case.get('run_state_status')})"
            )
    diagnosis = result.get("diagnosis")
    if isinstance(diagnosis, dict):
        print(f"diagnosis: {diagnosis.get('category')}")
        print(f"diagnosis_summary: {diagnosis.get('summary')}")
        print(f"diagnosis_next_step: {diagnosis.get('next_step')}")
    preflight = result.get("preflight")
    if isinstance(preflight, dict):
        print(f"preflight_ready: {str(preflight.get('ready')).lower()}")
        print(f"preflight_gate: {preflight.get('gate')}")


def _print_product_chat_entry_plain(payload: dict[str, Any]) -> None:
    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        preflight = {}
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        entry = {}
    print(f"command: {payload.get('command')}")
    print(f"preflight_ready: {str(preflight.get('ready')).lower()}")
    print(f"preflight_gate: {preflight.get('gate')}")
    print(f"preflight_category: {preflight.get('category')}")
    print(f"entry_status: {entry.get('status')}")
    print(f"entry_http_status: {entry.get('http_status')}")
    if entry.get("provider_status"):
        print(f"entry_provider_status: {entry.get('provider_status')}")
    if "requires_approval" in entry:
        print(f"entry_requires_approval: {str(entry.get('requires_approval')).lower()}")
    if "approval_id_present" in entry:
        print(f"approval_id_present: {str(entry.get('approval_id_present')).lower()}")
    if "assistant_message_present" in entry:
        print(f"assistant_message_present: {str(entry.get('assistant_message_present')).lower()}")
    if "artifact_ref_present" in entry:
        print(f"artifact_ref_present: {str(entry.get('artifact_ref_present')).lower()}")
    if isinstance(entry.get("next_step"), str):
        print(f"entry_next_step: {entry.get('next_step')}")
    explanation = entry.get("explanation")
    if isinstance(explanation, dict):
        print(f"entry_summary: {explanation.get('summary')}")
        print(f"entry_next_step: {explanation.get('next_step')}")
    pending_state = payload.get("pending_state")
    if isinstance(pending_state, dict):
        print(f"pending_state_saved: {str(pending_state.get('saved')).lower()}")
        print(f"pending_state_resume_ready: {str(pending_state.get('resume_ready')).lower()}")
        if isinstance(pending_state.get("next_step"), str):
            print(f"pending_state_next_step: {pending_state.get('next_step')}")
    print(f"codex_runner: {payload.get('codex_runner')}")
    print(f"runner_call_count: {payload.get('runner_call_count')}")


def _print_product_chat_entry_resume_plain(payload: dict[str, Any]) -> None:
    error = payload.get("error")
    if isinstance(error, dict):
        print(f"command: {payload.get('command')}")
        print(f"status: {payload.get('status')}")
        print(f"error_code: {error.get('code')}")
        print(f"error_reason: {error.get('reason')}")
        print(f"error_summary: {error.get('summary')}")
        print(f"error_next_step: {error.get('next_step')}")
        print(f"codex_runner: {payload.get('codex_runner')}")
        print(f"runner_call_count: {payload.get('runner_call_count')}")
        return
    approval = payload.get("approval")
    if not isinstance(approval, dict):
        approval = {}
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        entry = {}
    print(f"command: {payload.get('command')}")
    print(f"approval_status: {approval.get('status')}")
    print(f"approval_tool_execution_status: {approval.get('tool_execution_status')}")
    print(f"approval_artifact_ref_present: {str(approval.get('artifact_ref_present')).lower()}")
    print(f"entry_status: {entry.get('status')}")
    print(f"entry_http_status: {entry.get('http_status')}")
    if entry.get("provider_status"):
        print(f"entry_provider_status: {entry.get('provider_status')}")
    if "assistant_message_present" in entry:
        print(f"assistant_message_present: {str(entry.get('assistant_message_present')).lower()}")
    if "artifact_ref_present" in entry:
        print(f"artifact_ref_present: {str(entry.get('artifact_ref_present')).lower()}")
    if "tool_result_artifact_ref_present" in entry:
        print(
            "tool_result_artifact_ref_present: "
            f"{str(entry.get('tool_result_artifact_ref_present')).lower()}"
        )
    print(f"codex_runner: {payload.get('codex_runner')}")
    print(f"runner_call_count: {payload.get('runner_call_count')}")


def _product_chat_smoke_exit_code(result: dict[str, Any]) -> int:
    if result.get("status") in {"completed", "skipped"}:
        return 0
    if result.get("status") == "missing_configuration":
        return 2
    return 1


def _terminal_tool_smoke_exit_code(result: dict[str, Any]) -> int:
    if result.get("status") == "completed" and result.get("tool_result_status") == "completed":
        return 0
    if result.get("status") == "skipped":
        return 0
    if result.get("status") == "missing_configuration":
        return 2
    if result.get("reason_code") in {
        "llm_provider_selected_unoffered_tool",
        "invalid_model_tool_call",
    }:
        return 2
    return 1


def _product_chat_entry_exit_code(payload: dict[str, Any]) -> int:
    if payload.get("status") == "failed" and isinstance(payload.get("error"), dict):
        return 2
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        return 1
    if entry.get("status") in {"completed", "pending_user_approval"}:
        return 0
    if entry.get("status") == "bad_request":
        return 2
    preflight = payload.get("preflight")
    if isinstance(preflight, dict) and preflight.get("category") == "missing_configuration":
        return 2
    return 1


def _product_chat_entry_error_payload(
    exc: IsotopeError,
    *,
    command: str,
    runner_call_count: int = 0,
) -> dict[str, Any]:
    return {
        "command": command,
        "codex_runner": "fake",
        "status": "failed",
        "error": {
            "code": exc.code,
            "category": exc.category,
            "retryable": exc.retryable,
            "http_status": exc.http_status,
            "reason": _product_chat_entry_error_reason(exc),
            "summary": _product_chat_entry_error_summary(exc),
            "next_step": _product_chat_entry_error_next_step(exc),
        },
        "runner_call_count": runner_call_count,
    }


def _product_chat_entry_error_reason(exc: IsotopeError) -> str:
    details = exc.details if isinstance(exc.details, dict) else {}
    if isinstance(details.get("reason"), str):
        return details["reason"]
    if isinstance(details.get("resume_status"), str):
        return details["resume_status"]
    if isinstance(details.get("state"), str):
        return details["state"]
    if isinstance(details.get("field"), str):
        return details["field"]
    return exc.code


def _product_chat_entry_error_summary(exc: IsotopeError) -> str:
    if exc.code == "product_chat_entry_root_mismatch":
        return "The provided root does not match the local resume state."
    if exc.code == "product_chat_entry_state_already_resumed":
        return "The local resume state has already been used."
    if exc.code == "product_chat_entry_approval_unavailable":
        return "The saved approval is not available in this command root."
    if exc.code == "product_chat_entry_approval_already_resolved":
        return "The saved approval has already been resolved."
    if exc.code == "product_chat_entry_root_invalid":
        return "The command root is not a usable directory."
    if exc.code == "product_chat_entry_state_missing":
        return "The local resume state file was not found."
    if exc.code in {"product_chat_entry_state_invalid", "product_chat_entry_state_missing"}:
        return "The local resume state file is invalid."
    if exc.code == "product_chat_entry_state_save_failed":
        return "The local resume state could not be saved."
    if exc.code == "product_chat_entry_state_mark_failed":
        return "The resume completed, but the local state file could not be marked as used."
    return "The product-chat entry resume command could not continue."


def _product_chat_entry_error_next_step(exc: IsotopeError) -> str:
    if exc.code == "product_chat_entry_root_mismatch":
        return "omit --root or use the root recorded in the resume state"
    if exc.code == "product_chat_entry_state_already_resumed":
        return "start a new product-chat-entry request instead of reusing this state file"
    if exc.code == "product_chat_entry_approval_already_resolved":
        return "inspect the completed run, or create a fresh pending state"
    if exc.code == "product_chat_entry_approval_unavailable":
        return "use the original root/state file, or create a fresh pending state"
    if exc.code == "product_chat_entry_root_invalid":
        return "choose a command root that is a writable directory, then rerun product-chat-entry"
    if exc.code == "product_chat_entry_state_missing":
        return "check the --resume-state path, or create a fresh pending state with product-chat-entry --state-file"
    if exc.code == "product_chat_entry_state_save_failed":
        if _product_chat_entry_error_reason(exc) == "parent_not_directory":
            return "choose a --state-file path whose parent is a directory, then rerun product-chat-entry"
        return "choose a writable --state-file path and rerun product-chat-entry"
    if exc.code == "product_chat_entry_state_mark_failed":
        return "do not reuse this state file; inspect the completed run or create a fresh pending state"
    return "create a fresh pending state with product-chat-entry --state-file before resuming"


def _invalid_product_chat_entry_payload(message: Any) -> dict[str, Any] | None:
    if isinstance(message, str) and message.strip():
        return None
    preflight = {
        "ready": False,
        "gate": "blocked",
        "category": "invalid_request",
        "status": "bad_request",
        "reason_code": "llm_product_chat_user_message_required",
        "summary": "user message is required",
        "next_step": "pass a non-empty --message value",
    }
    return {
        "command": "llm_product_chat_app_entry",
        "codex_runner": "fake",
        "preflight": preflight,
        "entry": {
            "http_status": 400,
            "status": "bad_request",
            "error_code": "invalid_request",
            "reason_code": "llm_product_chat_user_message_required",
        },
        "runner_call_count": 0,
    }


def _invalid_product_chat_entry_mode_payload(args: argparse.Namespace) -> dict[str, Any] | None:
    if not getattr(args, "fake_entry_pending", False) or getattr(args, "fake_provider", False):
        return None
    reason_code = "llm_product_chat_fake_entry_pending_requires_fake_provider"
    preflight = {
        "ready": False,
        "gate": "blocked",
        "category": "invalid_request",
        "status": "bad_request",
        "reason_code": reason_code,
        "summary": "--fake-entry-pending only applies to the fake provider",
        "next_step": "pass --fake-provider with --fake-entry-pending, or remove --fake-entry-pending",
    }
    return {
        "command": "llm_product_chat_app_entry",
        "codex_runner": "fake",
        "preflight": preflight,
        "entry": {
            "http_status": 400,
            "status": "bad_request",
            "error_code": "invalid_request",
            "reason_code": reason_code,
        },
        "runner_call_count": 0,
    }


def _invalid_product_chat_entry_resume_mode_payload(args: argparse.Namespace) -> dict[str, Any] | None:
    if not (
        getattr(args, "message", None)
        or getattr(args, "state_file", None)
        or getattr(args, "fake_entry_pending", False)
    ):
        return None
    reason_code = "llm_product_chat_resume_state_conflicting_flags"
    preflight = {
        "ready": False,
        "gate": "blocked",
        "category": "invalid_request",
        "status": "bad_request",
        "reason_code": reason_code,
        "summary": "--resume-state cannot be combined with new-entry flags",
        "next_step": "use --resume-state by itself, or start a new product-chat-entry request",
    }
    return {
        "command": "llm_product_chat_app_entry_resume",
        "codex_runner": "fake",
        "preflight": preflight,
        "entry": {
            "http_status": 400,
            "status": "bad_request",
            "error_code": "invalid_request",
            "reason_code": reason_code,
        },
        "runner_call_count": 0,
    }


def _optional_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def _prepare_product_chat_entry_root(root: Path) -> None:
    try:
        root.mkdir(parents=True, exist_ok=True)
    except FileExistsError as exc:
        raise _product_chat_entry_root_error("not_directory") from exc
    except PermissionError as exc:
        raise _product_chat_entry_root_error("unwritable") from exc
    if not root.is_dir():
        raise _product_chat_entry_root_error("not_directory")


def _product_chat_entry_root_error(reason: str) -> IsotopeError:
    return IsotopeError(
        "product-chat entry command root is invalid",
        code="product_chat_entry_root_invalid",
        category="validation",
        retryable=False,
        http_status=400,
        details={"reason": reason},
    )


def _entry_initial_complete_run(args: argparse.Namespace) -> bool:
    return _optional_path(getattr(args, "state_file", None)) is None


def _maybe_write_product_chat_entry_state(
    response: Any,
    *,
    root: Path,
    run_id: str,
    preflight: Mapping[str, Any],
    state_file: Path | None,
) -> dict[str, Any]:
    body = _response_dict(response)
    approval_id = body.get("approval_id")
    if state_file is None:
        if body.get("status") == "pending_user_approval" and isinstance(approval_id, str):
            return {
                "saved": False,
                "resume_ready": False,
                "next_step": "rerun product-chat-entry with --state-file to save a resumable pending state",
            }
        return {}
    if body.get("status") != "pending_user_approval" or not isinstance(approval_id, str):
        return {"saved": False, "resume_ready": False}
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
    except FileExistsError as exc:
        raise _product_chat_entry_state_save_error("parent_not_directory") from exc
    except PermissionError as exc:
        raise _product_chat_entry_state_save_error("unwritable") from exc
    state = build_llm_product_chat_entry_resume_state(
        response,
        root=root,
        run_id=run_id,
        preflight=preflight,
    )
    if state is None:
        return {"saved": False, "resume_ready": False}
    try:
        state_file.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")
    except IsADirectoryError as exc:
        raise _product_chat_entry_state_save_error("not_file") from exc
    except PermissionError as exc:
        raise _product_chat_entry_state_save_error("unwritable") from exc
    return {
        "saved": True,
        "resume_ready": True,
        "next_step": "resume with product-chat-entry --resume-state using this saved state file",
    }


def _product_chat_entry_state_save_error(reason: str) -> IsotopeError:
    return IsotopeError(
        "product-chat entry state file could not be saved",
        code="product_chat_entry_state_save_failed",
        category="validation",
        retryable=False,
        http_status=400,
        details={"state": reason},
    )


def _product_chat_entry_state_mark_error(reason: str) -> IsotopeError:
    return IsotopeError(
        "product-chat entry state file could not be marked as resumed",
        code="product_chat_entry_state_mark_failed",
        category="validation",
        retryable=False,
        http_status=400,
        details={"state": reason},
    )


def _load_product_chat_entry_state(state_file: Path) -> dict[str, Any]:
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IsotopeError(
            "product-chat entry state file not found",
            code="product_chat_entry_state_missing",
            category="not_found",
            retryable=False,
            http_status=404,
            details={"state": "missing"},
        ) from exc
    except json.JSONDecodeError as exc:
        raise IsotopeError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "invalid"},
        ) from exc
    except IsADirectoryError as exc:
        raise IsotopeError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "not_file"},
        ) from exc
    except PermissionError as exc:
        raise IsotopeError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "unreadable"},
        ) from exc
    if not isinstance(state, dict):
        raise IsotopeError(
            "product-chat entry state file is invalid",
            code="product_chat_entry_state_invalid",
            category="validation",
            retryable=False,
            http_status=400,
            details={"state": "invalid"},
        )
    return validate_llm_product_chat_entry_resume_state(state)


def _validate_product_chat_entry_resume_root(args: argparse.Namespace, state: Mapping[str, Any]) -> None:
    root_arg = getattr(args, "root", None)
    if not root_arg:
        return
    state_root = state.get("root")
    if not isinstance(state_root, str) or not state_root:
        return
    requested_root = Path(root_arg).expanduser().resolve(strict=False)
    saved_root = Path(state_root).expanduser().resolve(strict=False)
    if requested_root == saved_root:
        return
    raise IsotopeError(
        "product-chat entry resume root mismatch",
        code="product_chat_entry_root_mismatch",
        category="validation",
        retryable=False,
        http_status=400,
        details={"reason": "root_mismatch", "field": "root"},
    )


def _mark_product_chat_entry_state_resumed(
    state_file: Path,
    state: dict[str, Any],
    *,
    approval: Mapping[str, Any],
    entry: Mapping[str, Any],
) -> None:
    updated = mark_llm_product_chat_entry_state_resumed(state, approval=approval, entry=entry)
    try:
        state_file.write_text(json.dumps(updated, sort_keys=True, indent=2), encoding="utf-8")
    except PermissionError as exc:
        raise _product_chat_entry_state_mark_error("unwritable") from exc


def _preflight_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    diagnosis = result.get("diagnosis")
    if not isinstance(diagnosis, dict):
        diagnosis = {}
    return {
        "ready": False,
        "gate": "blocked",
        "category": _safe_body_string(diagnosis, "category") or "product_chat_smoke_failed",
        "status": _safe_body_string(result, "status"),
        "reason_code": _safe_body_string(result, "reason_code"),
        "summary": _safe_body_string(diagnosis, "summary"),
        "next_step": _safe_body_string(diagnosis, "next_step"),
    }


def _blocked_product_chat_entry_summary(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "http_status": 412,
        "status": "blocked_by_preflight",
        "reason_code": "llm_product_chat_preflight_blocked",
        "preflight_category": _safe_body_string(dict(preflight), "category"),
        "explanation": {
            "summary": _safe_body_string(dict(preflight), "summary")
            or "Product-chat preflight is not ready.",
            "next_step": _safe_body_string(dict(preflight), "next_step")
            or "Run product-chat diagnosis before submitting a chat turn.",
        },
    }


def _response_dict(response: Any) -> dict[str, Any]:
    body = response.json() if callable(getattr(response, "json", None)) else getattr(response, "body", None)
    return body if isinstance(body, dict) else {}


def _run_state_status(body: dict[str, Any]) -> Any:
    run_state = body.get("run_state")
    if isinstance(run_state, dict) and isinstance(run_state.get("status"), str):
        return run_state["status"]
    return body.get("status")


def _safe_body_string(body: dict[str, Any], key: str) -> str | None:
    value = body.get(key)
    if isinstance(value, str) and value:
        return value[:128]
    return None


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


def _non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


__all__ = [
    "DEFAULT_DEEPSEEK_LIVE_SMOKE_PROMPT",
    "DEFAULT_LLM_LIVE_SMOKE_PROMPT",
    "DEFAULT_LLM_PRODUCT_CHAT_DIRECT_PROMPT",
    "DEFAULT_LLM_PRODUCT_CHAT_RESUME_PROMPT",
    "DEFAULT_LLM_PRODUCT_CHAT_TOOL_PROMPT",
    "DEFAULT_LLM_TERMINAL_TOOL_SMOKE_PROMPT",
    "DeepSeekToolCallLiveSmokeConfig",
    "LLMProductChatLiveSmokeConfig",
    "LLMTerminalToolLiveSmokeConfig",
    "LLMToolCallLiveSmokeConfig",
    "diagnose_deepseek_tool_call_live_smoke",
    "diagnose_llm_product_chat_live_smoke",
    "diagnose_llm_terminal_tool_live_smoke",
    "diagnose_llm_tool_call_live_smoke",
    "main",
    "run_deepseek_tool_call_live_smoke",
    "run_llm_product_chat_live_smoke",
    "run_llm_terminal_tool_live_smoke",
    "run_llm_tool_call_live_smoke",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
