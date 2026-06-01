"""Codex CLI backed LLM provider."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from ...integrations.codex.cli import CodexCliBackend, CodexCliBackendConfig
from ...integrations.codex.jsonl import extract_codex_agent_message_text
from ...integrations.codex.task import CodexTaskConfig, CodexTaskRequest
from .parsing import (
    _require_non_empty_string,
    _safe_usage,
    _validate_messages,
    _validate_model_tools,
)
from .types import (
    LLMChatTurnResponse,
    LLMFinalAnswerResponse,
    LLMResponse,
    LLMStreamChunk,
    LLMToolCall,
    LLMToolCallResponse,
)


CODEX_DEFAULT_MODEL_LABEL = "codex-default"
CODEX_PROVIDER_ID = "codex"


class CodexCliLLMProvider:
    """Use local Codex CLI as an Isotope LLM provider."""

    provider = CODEX_PROVIDER_ID

    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        executable: str = "codex",
        codex_home: str | None = None,
        model: str | None = None,
        profile: str | None = None,
        timeout: int = 60,
        max_output_bytes: int = 65536,
        process_runner: Callable[..., Any] = subprocess.run,
        executable_resolver: Callable[[str], str | None] = shutil.which,
        skip_git_repo_check: bool = True,
        inherit_proxy_env: bool = False,
    ) -> None:
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer")
        self.model = _require_non_empty_string(
            "model",
            model or CODEX_DEFAULT_MODEL_LABEL,
        )
        self.timeout = timeout
        self._backend = CodexCliBackend(
            CodexCliBackendConfig(
                workspace_root=str(Path(workspace_root or Path.cwd()).expanduser()),
                executable=executable,
                codex_home=codex_home,
                model=model,
                profile=profile,
                max_output_bytes=max_output_bytes,
                skip_git_repo_check=skip_git_repo_check,
                inherit_proxy_env=inherit_proxy_env,
            ),
            process_runner=process_runner,
            executable_resolver=executable_resolver,
        )

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        _validate_messages(messages)
        _validate_max_tokens(max_tokens)
        text, raw = self._run_prompt(
            _build_chat_prompt(messages, max_tokens=max_tokens),
            max_tokens=max_tokens,
        )
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=text,
            finish_reason="stop",
            usage=_usage(max_tokens=max_tokens, timeout=self.timeout, raw=raw),
            raw=raw,
        )

    def stream_generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> Iterator[LLMStreamChunk]:
        response = self.generate(messages, max_tokens=max_tokens)
        yield LLMStreamChunk(
            provider=response.provider,
            model=response.model,
            content=response.content,
            raw=response.raw,
        )

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        _validate_messages(messages)
        _validate_max_tokens(max_tokens)
        model_tools = _validate_model_tools(tools)
        text, raw = self._run_prompt(
            _build_tool_prompt(
                messages,
                tools=model_tools,
                max_tokens=max_tokens,
                allow_final_answer=False,
            ),
            max_tokens=max_tokens,
        )
        tool_call = _parse_tool_call_payload(_extract_json_object(text))
        return LLMToolCallResponse(
            provider=self.provider,
            model=self.model,
            finish_reason="tool_calls",
            usage=_usage(max_tokens=max_tokens, timeout=self.timeout, raw=raw),
            tool_call=tool_call,
        )

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMChatTurnResponse:
        _validate_messages(messages)
        _validate_max_tokens(max_tokens)
        model_tools = _validate_model_tools(tools)
        text, raw = self._run_prompt(
            _build_tool_prompt(
                messages,
                tools=model_tools,
                max_tokens=max_tokens,
                allow_final_answer=True,
            ),
            max_tokens=max_tokens,
        )
        payload = _extract_json_object(text)
        if payload.get("type") == "final_answer":
            content = _require_non_empty_string("content", payload.get("content"))
            return LLMFinalAnswerResponse(
                provider=self.provider,
                model=self.model,
                finish_reason="stop",
                usage=_usage(max_tokens=max_tokens, timeout=self.timeout, raw=raw),
                content=content,
            )
        tool_call = _parse_tool_call_payload(payload)
        return LLMToolCallResponse(
            provider=self.provider,
            model=self.model,
            finish_reason="tool_calls",
            usage=_usage(max_tokens=max_tokens, timeout=self.timeout, raw=raw),
            tool_call=tool_call,
        )

    def _run_prompt(self, prompt: str, *, max_tokens: int) -> tuple[str, dict[str, Any]]:
        result = self._backend.run(_build_codex_task_request(prompt, timeout=self.timeout))
        raw = _safe_codex_result_metadata(result)
        raw["max_tokens"] = max_tokens
        if result.status != "completed":
            reason = _require_non_empty_string("reason_code", result.reason_code)
            raise RuntimeError(f"codex cli provider failed: {reason}")
        for output in result.output_artifacts:
            content = output.content if hasattr(output, "content") else output["content"]
            text = _extract_output_text(content)
            if text:
                return text, raw
        raise RuntimeError("codex cli provider did not return an agent message")


def _build_chat_prompt(messages: list[dict[str, str]], *, max_tokens: int) -> str:
    payload = {
        "messages": copy.deepcopy(messages),
        "max_tokens": max_tokens,
        "rules": [
            "Act as an LLM provider inside Isotope, not as an autonomous coding agent.",
            "Do not execute shell commands, inspect files, modify files, or call tools.",
            "Answer only from the provided chat messages.",
            "Return only the assistant reply text.",
        ],
    }
    return (
        "Do not execute shell commands. Return only the assistant reply text.\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def _build_tool_prompt(
    messages: list[dict[str, str]],
    *,
    tools: list[dict[str, Any]],
    max_tokens: int,
    allow_final_answer: bool,
) -> str:
    payload = {
        "messages": copy.deepcopy(messages),
        "tools": copy.deepcopy(tools),
        "max_tokens": max_tokens,
        "rules": [
            "Act as an LLM provider inside Isotope, not as an autonomous coding agent.",
            "Do not execute shell commands, inspect files, modify files, or call tools.",
            "Choose only from the offered tools.",
            "Return exactly one JSON object and no prose outside JSON.",
        ],
    }
    if allow_final_answer:
        payload["rules"].append("Return either a final_answer or one tool_call.")
        payload["required_json_shape"] = {
            "type": "final_answer",
            "content": "assistant text",
            "or": {
                "type": "tool_call",
                "tool_call": {
                    "id": "stable call id",
                    "name": "offered tool name",
                    "arguments": "object",
                },
            },
        }
        prefix = "Return either a final_answer or one tool_call as JSON.\n"
    else:
        payload["rules"].append("Select exactly one offered tool.")
        payload["required_json_shape"] = {
            "tool_call": {
                "id": "stable call id",
                "name": "offered tool name",
                "arguments": "object",
            }
        }
        prefix = "Select exactly one offered tool. Return only JSON.\n"
    return prefix + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _build_codex_task_request(prompt: str, *, timeout: int) -> CodexTaskRequest:
    suffix = uuid.uuid4().hex
    return CodexTaskRequest(
        run_id=f"run_codex_llm_{suffix}",
        proposal_id=f"prop_codex_llm_{suffix}",
        decision_id=f"dec_codex_llm_{suffix}",
        execution_id=f"exec_codex_llm_{suffix}",
        policy_profile_id="default",
        policy_version="v0.2",
        registry_id="default",
        registry_version="v0.2",
        grants={
            "tools": ["codex_task"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": timeout},
            "codex_task": {"adapter_required": True},
        },
        workspace_binding={
            "workspace_id": f"workspace_codex_llm_{suffix}",
            "mode": "shared_ro",
            "lease_status": "active",
        },
        task_request={"kind": "codex_prompt", "prompt": prompt},
        budget={"seconds": timeout},
        artifact_policy={
            "capture": ["transcript"],
            "full_content_in_events": False,
            "full_content_in_read_model": False,
        },
        basis_event_ids=[f"evt_codex_llm_{suffix}"],
        adapter_config=CodexTaskConfig(
            adapter_id="codex_cli_llm_provider",
            adapter_version="v0.1",
        ).to_dict(),
    )


def _extract_output_text(content: str) -> str | None:
    try:
        transcript = json.loads(content)
    except json.JSONDecodeError:
        return extract_codex_agent_message_text(content) or _plain_text_or_none(content)
    if not isinstance(transcript, dict):
        return None
    stdout = transcript.get("stdout")
    if isinstance(stdout, str):
        return extract_codex_agent_message_text(stdout) or _plain_text_or_none(stdout)
    return None


def _plain_text_or_none(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    if _looks_like_codex_jsonl(stripped):
        return None
    return stripped


def _looks_like_codex_jsonl(text: str) -> bool:
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False
        return isinstance(event, dict) and isinstance(event.get("type"), str)
    return False


def _extract_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("codex provider returned empty response")
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        try:
            payload = _first_json_object(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError("codex provider response must contain a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("codex provider response must be a JSON object")
    return payload


def _first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise json.JSONDecodeError("no JSON object", text, 0)


def _parse_tool_call_payload(payload: Mapping[str, Any]) -> LLMToolCall:
    raw_call = payload.get("tool_call", payload)
    if not isinstance(raw_call, Mapping):
        raise ValueError("tool_call must be a JSON object")
    call_id = _optional_non_empty_string(raw_call.get("id")) or f"call_codex_{uuid.uuid4().hex[:8]}"
    tool_name = _optional_non_empty_string(raw_call.get("name")) or _optional_non_empty_string(
        raw_call.get("tool_name")
    )
    if tool_name is None:
        raise ValueError("tool_call.name must be a non-empty string")
    arguments = raw_call.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError("tool_call.arguments must be a JSON object") from exc
    if not isinstance(arguments, dict):
        raise ValueError("tool_call.arguments must be a JSON object")
    return LLMToolCall(
        call_id=call_id,
        tool_name=tool_name,
        arguments=copy.deepcopy(arguments),
    )


def _optional_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _validate_max_tokens(max_tokens: int) -> None:
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")


def _usage(*, max_tokens: int, timeout: int, raw: dict[str, Any]) -> dict[str, Any]:
    usage = {
        "max_tokens": max_tokens,
        "codex_timeout_seconds": timeout,
    }
    resource_usage = raw.get("resource_usage")
    if isinstance(resource_usage, dict):
        usage.update(_safe_usage(resource_usage))
    return usage


def _safe_codex_result_metadata(result: Any) -> dict[str, Any]:
    return {
        "status": str(getattr(result, "status", "")),
        "reason_code": str(getattr(result, "reason_code", "")),
        "resource_usage": _safe_usage(
            getattr(result, "resource_usage", {})
            if isinstance(getattr(result, "resource_usage", {}), dict)
            else {}
        ),
    }


def codex_provider_from_options(
    *,
    workspace_root: str | Path | None = None,
    executable: str = "codex",
    codex_home: str | None = None,
    model: str | None = None,
    profile: str | None = None,
    timeout: int = 60,
    process_runner: Callable[..., Any] = subprocess.run,
    executable_resolver: Callable[[str], str | None] = shutil.which,
    skip_git_repo_check: bool = True,
    inherit_proxy_env: bool = False,
) -> CodexCliLLMProvider:
    return CodexCliLLMProvider(
        workspace_root=workspace_root or os.getcwd(),
        executable=executable,
        codex_home=codex_home,
        model=model,
        profile=profile,
        timeout=timeout,
        process_runner=process_runner,
        executable_resolver=executable_resolver,
        skip_git_repo_check=skip_git_repo_check,
        inherit_proxy_env=inherit_proxy_env,
    )
