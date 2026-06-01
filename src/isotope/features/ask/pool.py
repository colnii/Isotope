"""TOML 号池到 Workbench Ask 的 provider 适配。"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from ...llm.pool import (
    DEFAULT_LLM_MAX_TOKENS,
    PoolEntry,
    resolve_pool_entries_from_env,
)
from ...llm.provider import (
    LLMResponse,
    LLMStreamChunk,
    StreamTransport,
    Transport,
    create_chat_provider_from_pool_entry,
)

DEFAULT_WORKBENCH_ASK_POOL_PATH = (
    Path(__file__).resolve().parents[1] / "supervisor" / "supervisor_llm_pool.toml"
)


class PooledWorkbenchAskProvider:
    """按顺序尝试 OpenAI-compatible（兼容 OpenAI 形状）模型配置。"""

    def __init__(
        self,
        *,
        entries: tuple[PoolEntry, ...],
        timeout: int = 60,
        transport: Transport | None = None,
        stream_transport: StreamTransport | None = None,
        codex_process_runner: Callable[..., Any] = subprocess.run,
        codex_executable_resolver: Callable[[str], str | None] = shutil.which,
    ) -> None:
        if not entries:
            raise ValueError("entries must not be empty")
        self._entries = entries
        self._timeout = timeout
        self._transport = transport
        self._stream_transport = stream_transport
        self._codex_process_runner = codex_process_runner
        self._codex_executable_resolver = codex_executable_resolver
        self.provider = "llm_pool"
        self.model = "configured"

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> LLMResponse:
        failures: list[str] = []
        for entry in self._entries:
            try:
                provider = create_chat_provider_from_pool_entry(
                    entry,
                    timeout=self._timeout,
                    transport=self._transport,
                    stream_transport=self._stream_transport,
                    codex_process_runner=self._codex_process_runner,
                    codex_executable_resolver=self._codex_executable_resolver,
                )
                return provider.generate(
                    messages,
                    max_tokens=entry.max_tokens or max_tokens,
                )
            except Exception as exc:
                failures.append(f"{entry.provider}:{type(exc).__name__}")
        raise ValueError(
            "All Workbench Ask LLM pool entries failed: " + ", ".join(failures)
        )

    def stream_generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> Iterator[LLMStreamChunk]:
        failures: list[str] = []
        for entry in self._entries:
            yielded = False
            try:
                provider = create_chat_provider_from_pool_entry(
                    entry,
                    timeout=self._timeout,
                    transport=self._transport,
                    stream_transport=self._stream_transport,
                    codex_process_runner=self._codex_process_runner,
                    codex_executable_resolver=self._codex_executable_resolver,
                )
                stream_generate = getattr(provider, "stream_generate", None)
                if not callable(stream_generate):
                    response = provider.generate(
                        messages,
                        max_tokens=entry.max_tokens or max_tokens,
                    )
                    yield LLMStreamChunk(
                        provider=response.provider,
                        model=response.model,
                        content=response.content,
                        raw=response.raw,
                    )
                    return
                for chunk in stream_generate(
                    messages,
                    max_tokens=entry.max_tokens or max_tokens,
                ):
                    yielded = True
                    yield chunk
                return
            except Exception as exc:
                if yielded:
                    raise
                failures.append(f"{entry.provider}:{type(exc).__name__}")
        raise ValueError(
            "All Workbench Ask LLM pool entries failed: " + ", ".join(failures)
        )


def resolve_workbench_ask_provider_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    agent_name: str | None = None,
    transport: Transport | None = None,
    codex_process_runner: Callable[..., Any] = subprocess.run,
    codex_executable_resolver: Callable[[str], str | None] = shutil.which,
) -> PooledWorkbenchAskProvider:
    env = dict(os.environ if environ is None else environ)
    if (
        "ISOTOPE_LLM_POOL_TOML_FILES" in env
        and "SUPERVISOR_LLM_POOL_TOML_FILES" not in env
    ):
        env["SUPERVISOR_LLM_POOL_TOML_FILES"] = env["ISOTOPE_LLM_POOL_TOML_FILES"]
    entries = resolve_pool_entries_from_env(
        env,
        agent_name=agent_name,
        env_var="SUPERVISOR_LLM_POOL_TOML_FILES",
        default_paths=(DEFAULT_WORKBENCH_ASK_POOL_PATH,),
    )
    if not entries:
        agent_hint = f" for agent '{agent_name}'" if agent_name else ""
        raise ValueError(
            f"No Workbench Ask LLM pool entries found{agent_hint}. "
            "Check ISOTOPE_LLM_POOL_TOML_FILES, SUPERVISOR_LLM_POOL_TOML_FILES, "
            "or the default supervisor_llm_pool.toml configuration."
        )
    timeout = _env_int(
        env,
        "ISOTOPE_LLM_TIMEOUT_SECONDS",
        default=_env_int(env, "SUPERVISOR_LLM_TIMEOUT_SECONDS", default=60),
    )
    return PooledWorkbenchAskProvider(
        entries=entries,
        timeout=timeout,
        transport=transport,
        codex_process_runner=codex_process_runner,
        codex_executable_resolver=codex_executable_resolver,
    )


def _env_int(env: Mapping[str, str], name: str, *, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value
