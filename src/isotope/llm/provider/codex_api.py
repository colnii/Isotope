"""Codex app-server backed LLM provider."""

from __future__ import annotations

import copy
import json
import os
import select
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...integrations.codex.task import CodexTaskNotConfiguredError
from .codex import CODEX_DEFAULT_MODEL_LABEL
from .parsing import _require_non_empty_string, _validate_messages
from .types import LLMResponse


CODEX_API_PROVIDER_ID = "codex-api"
CODEX_APP_SERVER_BASE_URL = "codex://app-server"
_SENSITIVE_MARKERS = ("secret", "token", "api_key", "apikey", "refresh")


class CodexApiLLMProvider:
    """Use local Codex app-server as an Isotope chat provider."""

    provider = CODEX_API_PROVIDER_ID

    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        executable: str = "codex",
        codex_home: str | None = None,
        model: str | None = None,
        profile: str | None = None,
        timeout: int = 60,
        process_factory: Callable[..., Any] = subprocess.Popen,
        executable_resolver: Callable[[str], str | None] = shutil.which,
    ) -> None:
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer")
        resolved = executable_resolver(executable)
        if not resolved:
            raise CodexTaskNotConfiguredError(
                "codex app-server executable not found",
                details={"executable": executable},
            )
        self.executable = resolved
        self.codex_home = codex_home
        self.model = _require_non_empty_string("model", model or CODEX_DEFAULT_MODEL_LABEL)
        self.profile = profile
        self.timeout = timeout
        self.workspace_root = Path(workspace_root or Path.cwd()).expanduser().resolve()
        self._process_factory = process_factory

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        _validate_messages(messages)
        _validate_max_tokens(max_tokens)
        client = _CodexAppServerClient(
            executable=self.executable,
            workspace_root=self.workspace_root,
            codex_home=self.codex_home,
            profile=self.profile,
            timeout=self.timeout,
            process_factory=self._process_factory,
        )
        result = client.run_chat_turn(
            model=None if self.model == CODEX_DEFAULT_MODEL_LABEL else self.model,
            prompt=_build_provider_prompt(messages, max_tokens=max_tokens),
        )
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=result.message,
            finish_reason="stop",
            usage={"max_tokens": max_tokens, "codex_timeout_seconds": self.timeout},
            raw={
                "thread_id": result.thread_id,
                "events_seen": result.events_seen,
                "app_server": "codex",
            },
        )


@dataclass(frozen=True)
class _CodexAppServerResult:
    thread_id: str
    message: str
    events_seen: int


class _CodexAppServerClient:
    def __init__(
        self,
        *,
        executable: str,
        workspace_root: Path,
        codex_home: str | None,
        profile: str | None,
        timeout: int,
        process_factory: Callable[..., Any],
    ) -> None:
        self.executable = executable
        self.workspace_root = workspace_root
        self.codex_home = codex_home
        self.profile = profile
        self.timeout = timeout
        self.process_factory = process_factory
        self._next_id = 1

    def run_chat_turn(self, *, model: str | None, prompt: str) -> _CodexAppServerResult:
        process = self._start_process()
        deadline = time.monotonic() + self.timeout
        try:
            self._send_request(
                process,
                "initialize",
                {
                    "clientInfo": {
                        "name": "isotope",
                        "title": "Isotope",
                        "version": "0.1.0",
                    }
                },
            )
            self._read_response(process, 1, deadline)
            self._send_notification(process, "initialized", {})
            thread_params = {"model": model} if model else {}
            self._send_request(process, "thread/start", thread_params)
            thread_response = self._read_response(process, 2, deadline)
            thread_id = _extract_thread_id(thread_response)
            self._send_request(
                process,
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                },
            )
            return self._read_turn_result(process, thread_id, deadline)
        finally:
            _terminate_process(process)

    def _start_process(self) -> Any:
        argv = [self.executable]
        if self.profile:
            argv.extend(["--profile", self.profile])
        argv.extend(["app-server", "--stdio"])
        env = os.environ.copy()
        if self.codex_home:
            env["CODEX_HOME"] = self.codex_home
        return self.process_factory(
            argv,
            cwd=str(self.workspace_root),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _send_request(self, process: Any, method: str, params: dict[str, Any]) -> int:
        request_id = self._next_id
        self._next_id += 1
        _write_json(process, {"method": method, "id": request_id, "params": params})
        return request_id

    def _send_notification(self, process: Any, method: str, params: dict[str, Any]) -> None:
        _write_json(process, {"method": method, "params": params})

    def _read_response(self, process: Any, request_id: int, deadline: float) -> dict[str, Any]:
        while True:
            message = _read_json(process, deadline)
            if message.get("id") != request_id:
                continue
            if isinstance(message.get("error"), Mapping):
                raise RuntimeError(_safe_rpc_error(message["error"]))
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("codex app-server returned malformed response")
            return copy.deepcopy(result)

    def _read_turn_result(
        self,
        process: Any,
        thread_id: str,
        deadline: float,
    ) -> _CodexAppServerResult:
        message_text = ""
        events_seen = 0
        while True:
            message = _read_json(process, deadline)
            if isinstance(message.get("error"), Mapping):
                raise RuntimeError(_safe_rpc_error(message["error"]))
            method = message.get("method")
            params = message.get("params")
            if not isinstance(method, str) or not isinstance(params, dict):
                continue
            events_seen += 1
            message_text = _project_agent_message(method, params, message_text)
            if method == "turn/completed":
                if not message_text.strip():
                    raise RuntimeError("codex api provider did not return an agent message")
                return _CodexAppServerResult(
                    thread_id=thread_id,
                    message=message_text.strip(),
                    events_seen=events_seen,
                )
            if method == "turn/failed":
                raise RuntimeError("codex app-server turn failed")


def _build_provider_prompt(messages: list[dict[str, Any]], *, max_tokens: int) -> str:
    payload = {"messages": copy.deepcopy(messages), "max_tokens": max_tokens}
    return (
        "Act as an LLM provider inside Isotope.\n"
        "Do not execute shell commands, inspect files, modify files, or call tools.\n"
        "Answer only from the provided chat messages.\n"
        "Return only the assistant reply text.\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def _write_json(process: Any, payload: dict[str, Any]) -> None:
    stdin = process.stdin
    stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    stdin.flush()


def _read_json(process: Any, deadline: float) -> dict[str, Any]:
    stdout = process.stdout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("codex app-server timed out")
    if _wait_for_pipe(stdout, remaining) is False:
        raise TimeoutError("codex app-server timed out")
    line = stdout.readline()
    if not line:
        raise RuntimeError("codex app-server closed stdout")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError("codex app-server returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("codex app-server returned non-object JSON")
    return payload


def _wait_for_pipe(stdout: Any, timeout: float) -> bool | None:
    try:
        fileno = stdout.fileno()
    except Exception:
        return None
    readable, _, _ = select.select([fileno], [], [], timeout)
    return bool(readable)


def _extract_thread_id(result: dict[str, Any]) -> str:
    thread = result.get("thread")
    if isinstance(thread, dict):
        thread_id = thread.get("id")
        if isinstance(thread_id, str) and thread_id:
            return thread_id
    thread_id = result.get("threadId")
    if isinstance(thread_id, str) and thread_id:
        return thread_id
    raise RuntimeError("codex app-server did not return a thread id")


def _project_agent_message(method: str, params: dict[str, Any], current: str) -> str:
    if method == "item/agentMessage/delta":
        delta = params.get("delta") or params.get("text") or params.get("textDelta")
        return current + delta if isinstance(delta, str) else current
    if method != "item/completed":
        return current
    item = params.get("item")
    if not isinstance(item, dict):
        return current
    if item.get("type") not in {"agent_message", "message"}:
        return current
    text = item.get("text") or item.get("content")
    if isinstance(text, str) and text.strip():
        return text
    return current


def _safe_rpc_error(error: Mapping[str, Any]) -> str:
    message = error.get("message")
    text = message if isinstance(message, str) and message.strip() else "codex app-server error"
    text = " ".join(text.split())
    text = _redact_sensitive_text(text)
    return text[:180]


def _redact_sensitive_text(text: str) -> str:
    cleaned = text
    for marker in _SENSITIVE_MARKERS:
        cleaned = cleaned.replace(marker + "-value", "[redacted]")
        cleaned = cleaned.replace(marker + "_value", "[redacted]")
    return cleaned


def _terminate_process(process: Any) -> None:
    try:
        process.terminate()
        process.wait(timeout=2)
    except Exception:
        try:
            process.kill()
        except Exception:
            return


def _validate_max_tokens(max_tokens: int) -> None:
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
