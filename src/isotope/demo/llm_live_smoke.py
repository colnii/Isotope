"""Opt-in live smoke helper for LLM provider tool-call selection."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..platform.errors import IsotopeError
from ..features.chat.flow import (
    submit_llm_product_chat_entry_resume,
    submit_llm_product_chat_user_message_with_preflight,
    summarize_llm_product_chat_entry_response,
)
from ..llm.provider import resolve_llm_tool_call_provider
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
    _product_chat_messages,
)
from .llm_live_smoke_config import (
    DEFAULT_DEEPSEEK_LIVE_SMOKE_PROMPT,
    DEFAULT_LLM_LIVE_SMOKE_PROMPT,
    DEFAULT_LLM_PRODUCT_CHAT_DIRECT_PROMPT,
    DEFAULT_LLM_PRODUCT_CHAT_RESUME_PROMPT,
    DEFAULT_LLM_PRODUCT_CHAT_TOOL_PROMPT,
    DEFAULT_LLM_TERMINAL_TOOL_SMOKE_PROMPT,
    DeepSeekToolCallLiveSmokeConfig,
    LLMProductChatLiveSmokeConfig,
    LLMTerminalToolLiveSmokeConfig,
    LLMToolCallLiveSmokeConfig,
)
from .llm_live_smoke_diagnosis import (
    _maybe_diagnose_terminal_tool_missing_configuration,
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
from .llm_live_smoke_runs import (
    diagnose_deepseek_tool_call_live_smoke,
    diagnose_llm_product_chat_live_smoke,
    diagnose_llm_terminal_tool_live_smoke,
    diagnose_llm_tool_call_live_smoke,
    run_deepseek_tool_call_live_smoke,
    run_llm_product_chat_live_smoke,
    run_llm_terminal_tool_live_smoke,
    run_llm_tool_call_live_smoke,
)


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
    from ..interfaces.http import create_http_app

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
    from ..integrations.codex.server import CodexCliServerConfig
    from ..interfaces.http import create_llm_product_chat_http_app

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
    from ..integrations.codex.server import CodexCliServerConfig
    from ..interfaces.http import create_llm_product_chat_http_app

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
    from ..integrations.codex.server import CodexCliServerConfig
    from ..interfaces.http import create_llm_product_chat_http_app

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
