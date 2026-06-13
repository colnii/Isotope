"""Provider resolver for long-task planner ticks."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from isotope.llm.pool import PoolEntry, resolve_pool_entries_from_env
from isotope.llm.provider import (
    LLMResponse,
    Transport,
    create_chat_provider_from_pool_entry,
)
from isotope.llm.provider.parsing import _normalized_provider_name


class PooledLongTaskPlannerProvider:
    provider = "pooled"
    model = "pooled"

    def __init__(
        self,
        *,
        entries: tuple[PoolEntry, ...],
        timeout: int = 60,
        transport: Transport | None = None,
        codex_process_runner: Callable[..., Any] = subprocess.run,
        codex_executable_resolver: Callable[[str], str | None] = shutil.which,
    ) -> None:
        if not entries:
            raise ValueError("entries must not be empty")
        self._entries = entries
        self._timeout = timeout
        self._transport = transport
        self._codex_process_runner = codex_process_runner
        self._codex_executable_resolver = codex_executable_resolver

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        failures: list[str] = []
        for entry in self._entries:
            try:
                provider = create_chat_provider_from_pool_entry(
                    entry,
                    timeout=self._timeout,
                    transport=self._transport,
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
            "All long-task planner pool entries failed: " + ", ".join(failures)
        )


def resolve_long_task_planner_provider_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    timeout: int | None = None,
    transport: Transport | None = None,
    codex_process_runner: Callable[..., Any] = subprocess.run,
    codex_executable_resolver: Callable[[str], str | None] = shutil.which,
) -> PooledLongTaskPlannerProvider:
    env = os.environ if environ is None else environ
    entries = resolve_pool_entries_from_env(
        env,
        env_var="SUPERVISOR_LLM_POOL_TOML_FILES",
        default_paths=(
            Path(__file__).resolve().parents[1] / "supervisor_llm_pool.toml",
        ),
    )
    provider_filter = _normalized_provider_name(
        _env_string(env, "ISOTOPE_LONG_TASK_LLM_PROVIDER")
    )
    if provider_filter:
        entries = tuple(
            entry
            for entry in entries
            if _normalized_provider_name(entry.provider) == provider_filter
        )
        if not entries:
            raise ValueError(
                "No long-task planner LLM pool entries found for provider "
                f"{provider_filter}. Check SUPERVISOR_LLM_POOL_TOML_FILES."
            )
    if not entries:
        raise ValueError(
            "No long-task planner LLM pool entries found. "
            "Check SUPERVISOR_LLM_POOL_TOML_FILES or supervisor_llm_pool.toml."
        )
    return PooledLongTaskPlannerProvider(
        entries=entries,
        timeout=timeout or 60,
        transport=transport,
        codex_process_runner=codex_process_runner,
        codex_executable_resolver=codex_executable_resolver,
    )


def _env_string(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
