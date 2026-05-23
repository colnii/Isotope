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
    submit_llm_product_chat_entry_resume,
    submit_llm_product_chat_user_message_with_preflight,
    summarize_llm_product_chat_entry_response,
)
from .llm.provider import (
    ToolCallProvider,
    resolve_llm_tool_call_provider,
    submit_llm_tool_call,
)
from .llm_live_smoke_cli_support import (
    _blocked_product_chat_entry_summary,
    _entry_initial_complete_run,
    _invalid_product_chat_entry_mode_payload,
    _invalid_product_chat_entry_payload,
    _invalid_product_chat_entry_resume_mode_payload,
    _load_product_chat_entry_state,
    _mark_product_chat_entry_state_resumed,
    _maybe_write_product_chat_entry_state,
    _optional_path,
    _preflight_from_result,
    _prepare_product_chat_entry_root,
    _print_product_chat_entry_plain,
    _print_product_chat_entry_resume_plain,
    _print_product_chat_smoke_plain,
    _print_terminal_tool_smoke_plain,
    _product_chat_entry_error_payload,
    _product_chat_entry_exit_code,
    _product_chat_smoke_exit_code,
    _terminal_tool_smoke_exit_code,
    _validate_product_chat_entry_resume_root,
)
from .llm_live_smoke_cases import (
    _create_smoke_run,
    _messages,
    _product_chat_messages,
    _run_llm_product_chat_live_smoke_cases,
    _terminal_tool_messages,
)
from .llm_live_smoke_diagnosis import (
    _diagnosis_for,
    _legacy_deepseek_result,
    _llm_diagnosis_for,
    _llm_product_chat_diagnosis_for,
    _llm_product_chat_preflight_for,
    _llm_terminal_tool_diagnosis_for,
    _llm_terminal_tool_preflight_for,
    _maybe_diagnose_terminal_tool_missing_configuration,
    _terminal_error_reason_summary,
)
from .llm_live_smoke_fakes import (
    _RecordingFakeCodexRunner,
    _fake_codex_executable_resolver,
    _fake_product_chat_entry_provider,
    _fake_product_chat_provider,
    _fake_terminal_tool_provider,
    _provider_call_count,
)
from .llm_live_smoke_parser import _build_arg_parser


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
