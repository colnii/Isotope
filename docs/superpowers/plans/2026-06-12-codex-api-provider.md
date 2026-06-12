# Codex API Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first `codex-api` Isotope LLM provider that uses local `codex app-server` OAuth-backed execution through the existing chat provider contract.

**Architecture:** Add a focused `src/isotope/llm/provider/codex_api.py` module that starts `codex app-server --stdio`, speaks the minimal JSON-RPC flow for one chat turn, and returns an `LLMResponse`. Wire the provider into existing pool parsing, provider factory, and env resolution without changing the existing CLI-backed `provider = "codex"` path.

**Tech Stack:** Python 3.13, stdlib `subprocess`/JSON, existing `isotope.llm.provider` contracts, pytest.

---

## File Map

- Create `src/isotope/llm/provider/codex_api.py`: app-server provider, JSON-RPC request/response helpers, prompt conversion, safe event projection.
- Create `tests/unit/llm/test_codex_api_llm_provider.py`: fake process tests for app-server `generate()` and failure handling.
- Modify `src/isotope/llm/provider/__init__.py`: export `CodexApiLLMProvider`.
- Modify `src/isotope/llm/provider/factory.py`: instantiate `CodexApiLLMProvider` for `PoolEntry(provider="codex-api")`.
- Modify `src/isotope/llm/provider/resolution.py`: resolve `ISOTOPE_LLM_PROVIDER=codex-api`.
- Modify `src/isotope/llm/pool.py`: parse `provider = "codex-api"` without `api_keys`, using `codex://app-server`.
- Modify `tests/unit/llm/test_llm_pool.py`: cover TOML and factory behavior.
- Modify `tests/unit/llm/test_codex_llm_provider.py`: add env resolution regression for `codex-api`.
- Modify `src/isotope/features/supervisor/supervisor_llm_pool.toml.example`: document the new provider option.

---

### Task 1: App-Server Provider Core

**Files:**
- Create: `src/isotope/llm/provider/codex_api.py`
- Create: `tests/unit/llm/test_codex_api_llm_provider.py`

- [ ] **Step 1: Write the failing provider success test**

Create `tests/unit/llm/test_codex_api_llm_provider.py` with:

```python
from __future__ import annotations

import io
import json
from typing import Any

from isotope.llm.provider.codex_api import CodexApiLLMProvider


class _FakeStdin:
    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] = []

    def write(self, text: str) -> int:
        self.lines.append(json.loads(text))
        return len(text)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeProcess:
    def __init__(self, lines: list[dict[str, Any]]) -> None:
        self.stdin = _FakeStdin()
        self.stdout = io.StringIO("".join(json.dumps(line) + "\n" for line in lines))
        self.stderr = io.StringIO("")
        self.returncode = None
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


class _FakeProcessFactory:
    def __init__(self, lines: list[dict[str, Any]]) -> None:
        self.lines = lines
        self.calls: list[dict[str, Any]] = []
        self.processes: list[_FakeProcess] = []

    def __call__(self, argv, **kwargs):
        process = _FakeProcess(self.lines)
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs), "process": process})
        self.processes.append(process)
        return process


def _resolve_codex(executable: str) -> str:
    assert executable == "codex"
    return "/opt/codex/bin/codex"


def test_codex_api_provider_generates_from_app_server_agent_message(tmp_path):
    factory = _FakeProcessFactory(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread_123"}}},
            {"id": 3, "result": {"turn": {"id": "turn_123"}}},
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agent_message",
                        "text": "Codex API answer",
                    }
                },
            },
            {"method": "turn/completed", "params": {"turn": {"id": "turn_123"}}},
        ]
    )
    provider = CodexApiLLMProvider(
        workspace_root=tmp_path,
        executable="codex",
        model="gpt-5-codex",
        timeout=7,
        process_factory=factory,
        executable_resolver=_resolve_codex,
    )

    response = provider.generate(
        [
            {"role": "system", "content": "Answer briefly."},
            {"role": "user", "content": "hello"},
        ],
        max_tokens=123,
    )

    assert response.provider == "codex-api"
    assert response.model == "gpt-5-codex"
    assert response.content == "Codex API answer"
    assert response.finish_reason == "stop"
    assert response.usage["max_tokens"] == 123
    assert response.usage["codex_timeout_seconds"] == 7
    assert response.raw == {
        "thread_id": "thread_123",
        "events_seen": 2,
        "app_server": "codex",
    }
    call = factory.calls[0]
    assert call["argv"] == ["/opt/codex/bin/codex", "app-server", "--stdio"]
    assert call["kwargs"]["cwd"] == str(tmp_path.resolve())
    sent = call["process"].stdin.lines
    assert sent[0]["method"] == "initialize"
    assert sent[1] == {"method": "initialized", "params": {}}
    assert sent[2]["method"] == "thread/start"
    assert sent[2]["params"] == {"model": "gpt-5-codex"}
    assert sent[3]["method"] == "turn/start"
    assert sent[3]["params"]["threadId"] == "thread_123"
    assert "Do not execute shell commands" in sent[3]["params"]["input"][0]["text"]
```

- [ ] **Step 2: Run the success test and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_codex_api_llm_provider.py::test_codex_api_provider_generates_from_app_server_agent_message -q
```

Expected: failure because `isotope.llm.provider.codex_api` does not exist.

- [ ] **Step 3: Implement minimal app-server provider**

Create `src/isotope/llm/provider/codex_api.py` with:

```python
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
from pathlib import Path
from typing import Any

from ...integrations.codex.task import CodexTaskNotConfiguredError
from .codex import CODEX_DEFAULT_MODEL_LABEL
from .parsing import _require_non_empty_string, _validate_messages
from .types import LLMResponse

CODEX_API_PROVIDER_ID = "codex-api"
CODEX_APP_SERVER_BASE_URL = "codex://app-server"


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
            raise CodexTaskNotConfiguredError("codex executable not found")
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


class _CodexAppServerResult:
    def __init__(self, *, thread_id: str, message: str, events_seen: int) -> None:
        self.thread_id = thread_id
        self.message = message
        self.events_seen = events_seen


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
            if isinstance(method, str) and isinstance(params, dict):
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
    for marker in ("secret", "token", "api_key", "apikey", "refresh"):
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
```

- [ ] **Step 4: Run provider test and verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_codex_api_llm_provider.py::test_codex_api_provider_generates_from_app_server_agent_message -q
```

Expected: `1 passed`.

- [ ] **Step 5: Add failing provider error tests**

Append these tests to `tests/unit/llm/test_codex_api_llm_provider.py`:

```python
import pytest


def test_codex_api_provider_raises_safe_rpc_error(tmp_path):
    factory = _FakeProcessFactory(
        [
            {"id": 1, "error": {"code": -32000, "message": "bad token secret-value"}},
        ]
    )
    provider = CodexApiLLMProvider(
        workspace_root=tmp_path,
        executable="codex",
        process_factory=factory,
        executable_resolver=_resolve_codex,
    )

    with pytest.raises(RuntimeError) as excinfo:
        provider.generate([{"role": "user", "content": "hello"}])

    message = str(excinfo.value)
    assert "bad token" in message
    assert "secret-value" not in message
    assert "[redacted]" in message
    assert len(message) <= 180


def test_codex_api_provider_requires_agent_message(tmp_path):
    factory = _FakeProcessFactory(
        [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "thread_123"}}},
            {"id": 3, "result": {"turn": {"id": "turn_123"}}},
            {"method": "turn/completed", "params": {"turn": {"id": "turn_123"}}},
        ]
    )
    provider = CodexApiLLMProvider(
        workspace_root=tmp_path,
        executable="codex",
        process_factory=factory,
        executable_resolver=_resolve_codex,
    )

    with pytest.raises(RuntimeError, match="did not return an agent message"):
        provider.generate([{"role": "user", "content": "hello"}])
```

- [ ] **Step 6: Run provider file and verify expected result**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_codex_api_llm_provider.py -q
```

Expected: all provider tests pass, including the `secret-value` non-leak
assertion.

- [ ] **Step 7: Commit provider core**

```bash
git add src/isotope/llm/provider/codex_api.py tests/unit/llm/test_codex_api_llm_provider.py
git commit -m "feat(codex): add app-server llm provider"
```

---

### Task 2: Pool Parser and Factory Wiring

**Files:**
- Modify: `src/isotope/llm/pool.py`
- Modify: `src/isotope/llm/provider/factory.py`
- Modify: `src/isotope/llm/provider/__init__.py`
- Modify: `tests/unit/llm/test_llm_pool.py`

- [ ] **Step 1: Write failing pool parser test**

Add to `tests/unit/llm/test_llm_pool.py`:

```python
def test_pool_entries_accept_codex_api_provider_without_api_key(tmp_path):
    codex_home = tmp_path / "codex-home"
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        f"""\
[[agents]]
name = "supervisor"

[[agents.providers]]
provider = "codex-api"
model = "gpt-5-codex"
codex_home = "{codex_home}"
profile = "chatgpt"
max_tokens = 2048
""",
        encoding="utf-8",
    )

    entries = resolve_pool_entries_from_env(
        {"SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path)},
        env_var="SUPERVISOR_LLM_POOL_TOML_FILES",
        agent_name="supervisor",
    )

    assert len(entries) == 1
    assert entries[0].provider == "codex-api"
    assert entries[0].api_key == ""
    assert entries[0].base_url == "codex://app-server"
    assert entries[0].model == "gpt-5-codex"
    assert entries[0].max_tokens == 2048
    assert entries[0].options == {
        "codex_home": str(codex_home),
        "profile": "chatgpt",
    }
```

- [ ] **Step 2: Run parser test and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_llm_pool.py::test_pool_entries_accept_codex_api_provider_without_api_key -q
```

Expected: failure because `codex-api` is treated as a generic provider requiring
`base_url` and `api_keys`.

- [ ] **Step 3: Implement pool constants and parser branch**

In `src/isotope/llm/pool.py`:

```python
CODEX_POOL_BASE_URL = "codex://cli"
CODEX_API_POOL_BASE_URL = "codex://app-server"
```

In `_append_entries_from_toml_item(...)`, after the existing `provider == "codex"`
branch, add:

```python
    if provider.strip().lower() == "codex-api":
        entries.append(
            PoolEntry(
                provider="codex-api",
                api_key="",
                base_url=CODEX_API_POOL_BASE_URL,
                model=_optional_toml_str(item, "model") or "codex-default",
                max_tokens=max_tokens_val,
                options=_codex_options_from_toml_item(item),
            )
        )
        return
```

- [ ] **Step 4: Run parser test and verify GREEN**

Run the same parser test. Expected: `1 passed`.

- [ ] **Step 5: Write failing factory/export test**

Add to `tests/unit/llm/test_llm_pool.py`:

```python
def test_codex_api_pool_entry_creates_app_server_provider(tmp_path):
    from isotope.llm.provider import CodexApiLLMProvider

    provider = create_chat_provider_from_pool_entry(
        PoolEntry(
            provider="codex-api",
            api_key="",
            base_url="codex://app-server",
            model="gpt-5-codex",
            options={"workspace_root": str(tmp_path), "codex_home": str(tmp_path / "codex")},
        ),
        timeout=9,
        codex_executable_resolver=lambda executable: "/opt/codex/bin/codex",
    )

    assert isinstance(provider, CodexApiLLMProvider)
    assert provider.provider == "codex-api"
    assert provider.model == "gpt-5-codex"
    assert provider.timeout == 9
```

- [ ] **Step 6: Run factory test and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_llm_pool.py::test_codex_api_pool_entry_creates_app_server_provider -q
```

Expected: import failure or generic provider API-key validation failure.

- [ ] **Step 7: Wire exports and factory**

Modify `src/isotope/llm/provider/__init__.py`:

```python
from .codex_api import CodexApiLLMProvider
```

Add `"CodexApiLLMProvider"` to `__all__`.

Modify `src/isotope/llm/provider/factory.py` imports:

```python
from .codex_api import CodexApiLLMProvider
```

Before `_is_deepseek_entry(entry)`:

```python
    if _normalized_provider_name(entry.provider) == "codex-api":
        return CodexApiLLMProvider(
            workspace_root=_option_string(entry, "workspace_root"),
            executable=_option_string(entry, "executable") or "codex",
            codex_home=_option_string(entry, "codex_home"),
            model=None if entry.model == CODEX_DEFAULT_MODEL_LABEL else entry.model,
            profile=_option_string(entry, "profile"),
            timeout=timeout,
            executable_resolver=codex_executable_resolver,
        )
```

- [ ] **Step 8: Run pool tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/llm/test_llm_pool.py -q
```

Expected: all pool tests pass.

- [ ] **Step 9: Commit pool/factory wiring**

```bash
git add src/isotope/llm/pool.py src/isotope/llm/provider/__init__.py \
  src/isotope/llm/provider/factory.py tests/unit/llm/test_llm_pool.py
git commit -m "feat(codex): wire app-server provider into pool"
```

---

### Task 3: Environment Resolution and Example TOML

**Files:**
- Modify: `src/isotope/llm/provider/resolution.py`
- Modify: `tests/unit/llm/test_codex_llm_provider.py`
- Modify: `src/isotope/features/supervisor/supervisor_llm_pool.toml.example`

- [ ] **Step 1: Write failing env resolver test**

Add to `tests/unit/llm/test_codex_llm_provider.py`:

```python
def test_llm_provider_resolution_configures_codex_api_without_api_key(tmp_path):
    resolution = resolve_llm_tool_call_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "codex-api",
            "ISOTOPE_LLM_MODEL": "gpt-5-codex",
            "ISOTOPE_LLM_TIMEOUT_SECONDS": "13",
            "ISOTOPE_CODEX_WORKSPACE_ROOT": str(tmp_path),
            "ISOTOPE_CODEX_HOME": str(tmp_path / "codex-home"),
        },
        codex_executable_resolver=_resolve_codex_executable,
    )

    assert resolution.status == "configured"
    assert resolution.provider_name == "codex-api"
    assert resolution.provider is not None
    assert resolution.provider.provider == "codex-api"
    assert resolution.provider.model == "gpt-5-codex"
```

- [ ] **Step 2: Run resolver test and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_codex_llm_provider.py::test_llm_provider_resolution_configures_codex_api_without_api_key -q
```

Expected: unsupported provider resolution.

- [ ] **Step 3: Implement resolver branch**

Modify `src/isotope/llm/provider/resolution.py`:

- import `CodexApiLLMProvider`.
- in both `resolve_llm_tool_call_provider(...)` and
  `resolve_llm_chat_provider(...)`, route `provider_name == "codex-api"` to a
  new `_resolve_codex_api_provider(...)`.
- implement:

```python
def _resolve_codex_api_provider(
    env: Mapping[str, str],
    *,
    timeout: int,
    executable_resolver: Any,
) -> LLMProviderResolution:
    try:
        provider = CodexApiLLMProvider(
            workspace_root=_env_string(env, "ISOTOPE_CODEX_WORKSPACE_ROOT") or os.getcwd(),
            executable=_env_string(env, "ISOTOPE_CODEX_EXECUTABLE") or "codex",
            codex_home=_optional_env_string(env, "ISOTOPE_CODEX_HOME"),
            model=_optional_env_string(env, "ISOTOPE_LLM_MODEL")
            or _optional_env_string(env, "CODEX_MODEL"),
            profile=_optional_env_string(env, "ISOTOPE_CODEX_PROFILE"),
            timeout=timeout,
            executable_resolver=executable_resolver,
        )
    except CodexTaskNotConfiguredError:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_codex_cli_missing",
            provider_name="codex-api",
        )
    except ValueError:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
            provider_name="codex-api",
        )
    return LLMProviderResolution(
        status="configured",
        reason_code="llm_provider_configured",
        provider_name=provider.provider,
        provider=provider,
    )
```

- [ ] **Step 4: Run resolver tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_codex_llm_provider.py -q
```

Expected: all Codex provider resolver tests pass.

- [ ] **Step 5: Update example TOML**

In `src/isotope/features/supervisor/supervisor_llm_pool.toml.example`, add a
commented `codex-api` provider block under the existing Codex provider example:

```toml
# [[agents.providers]]
# provider = "codex-api"
# model = "gpt-5-codex"
# max_tokens = 2048
# # Uses local Codex OAuth via `codex app-server`; no api_keys field.
```

- [ ] **Step 6: Commit resolver and docs wiring**

```bash
git add src/isotope/llm/provider/resolution.py tests/unit/llm/test_codex_llm_provider.py \
  src/isotope/features/supervisor/supervisor_llm_pool.toml.example
git commit -m "feat(codex): resolve app-server provider from env"
```

---

### Task 4: Verification and Surface Audit

**Files:**
- Read: all changed files

- [ ] **Step 1: Run targeted unit tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_codex_api_llm_provider.py \
  tests/unit/llm/test_codex_llm_provider.py \
  tests/unit/llm/test_llm_provider.py \
  tests/unit/llm/test_llm_pool.py \
  tests/unit/integrations/codex/runtime -q
```

Expected: all pass.

- [ ] **Step 2: Check file sizes and directory counts**

Run:

```bash
wc -l src/isotope/llm/provider/*.py tests/unit/llm/*.py
find src/isotope/llm/provider -maxdepth 1 -type f -name '*.py' | wc -l
find tests/unit/llm -maxdepth 1 -type f -name '*.py' | wc -l
```

Expected: no touched Python file exceeds the project comfort range in a way
introduced by this change; provider directory remains at or below 10 source
files.

- [ ] **Step 3: Run changed-surface dev eval check**

Run:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

If `eval_required=true`, run the returned `recommended_command`, read generated
`.dev-eval-runs/**/state/dev-evals/reviewer-prompts/*.md`, and apply any
required follow-up before final merge.

- [ ] **Step 4: Inspect git status and commit state**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected: branch contains the spec commit plus implementation commits, and no
unstaged changes remain unless a verification artifact is intentionally ignored.
