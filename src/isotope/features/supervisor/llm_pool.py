"""Supervisor TOML 号池到 summary provider 的适配。"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from ...llm.pool import PoolEntry, resolve_pool_entries_from_env
from ...llm.provider import OpenAICompatibleChatProvider, Transport

DEFAULT_MAX_TOKENS = 2048
DEFAULT_SUPERVISOR_LLM_POOL_PATH = (
    Path(__file__).resolve().parent / "supervisor_llm_pool.toml"
)


class SummaryProvider(Protocol):
    def summarize(self, messages: list[dict[str, str]]) -> str:
        ...


class PooledSummaryProvider:
    """按顺序尝试 OpenAI-compatible（兼容 OpenAI 形状）模型配置。"""

    def __init__(
        self,
        *,
        entries: tuple[PoolEntry, ...],
        timeout: int = 60,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        transport: Transport | None = None,
    ) -> None:
        if not entries:
            raise ValueError("entries must not be empty")
        self._entries = entries
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._transport = transport

    def summarize(self, messages: list[dict[str, str]]) -> str:
        failures: list[str] = []
        for entry in self._entries:
            try:
                provider = OpenAICompatibleChatProvider(
                    provider=entry.provider,
                    api_key=entry.api_key,
                    base_url=entry.base_url,
                    model=entry.model,
                    timeout=self._timeout,
                    transport=self._transport,
                )
                response = provider.generate(
                    messages,
                    max_tokens=entry.max_tokens or self._max_tokens,
                )
                return _strip_thinking(response.content)
            except Exception as exc:
                failures.append(
                    f"{entry.provider}:{type(exc).__name__}"
                    f"({_safe_failure_message(exc, entry.api_key)})"
                )
        raise ValueError("All LLM pool entries failed: " + ", ".join(failures))


def resolve_summary_provider_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    agent_name: str | None = None,
    transport: Transport | None = None,
) -> SummaryProvider:
    """从 TOML 号池创建摘要 provider（模型适配器）。

    ``agent_name`` 为 None 时使用全部 agent 的号池；
    指定 agent_name 时只加载对应 ``[[agents]]`` 下的 providers。
    """
    env = os.environ if environ is None else environ
    timeout = _env_int(env, "SUPERVISOR_LLM_TIMEOUT_SECONDS", default=60)
    max_tokens = _env_int(
        env,
        "SUPERVISOR_LLM_MAX_TOKENS",
        default=DEFAULT_MAX_TOKENS,
    )
    entries = resolve_pool_entries_from_env(
        env,
        agent_name=agent_name,
        env_var="SUPERVISOR_LLM_POOL_TOML_FILES",
        default_paths=(DEFAULT_SUPERVISOR_LLM_POOL_PATH,),
        default_provider="pool",
    )
    if not entries:
        agent_hint = f" for agent '{agent_name}'" if agent_name else ""
        raise ValueError(
            f"No LLM pool entries found{agent_hint}. "
            "Check SUPERVISOR_LLM_POOL_TOML_FILES or the default "
            "supervisor_llm_pool.toml configuration."
        )

    return PooledSummaryProvider(
        entries=entries,
        timeout=timeout,
        max_tokens=max_tokens,
        transport=transport,
    )


def _safe_failure_message(exc: Exception, api_key: str) -> str:
    message = " ".join(str(exc).split())
    if api_key:
        message = message.replace(api_key, _redacted_secret(api_key))
    return _clip_text(message or type(exc).__name__, limit=180)


def _redacted_secret(value: str) -> str:
    if len(value) <= 3:
        return "..."
    return value[:3] + "..."


def _clip_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


def _strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def _env_string(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if not value:
        return None
    return value.strip() or None


def _env_int(env: Mapping[str, str], name: str, *, default: int) -> int:
    value = _env_string(env, name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed
