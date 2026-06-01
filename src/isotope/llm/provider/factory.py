"""Factories for provider configs shared by pool-backed chains."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from ..pool import PoolEntry
from .clients import DeepSeekChatProvider, OpenAICompatibleChatProvider
from .codex import CODEX_DEFAULT_MODEL_LABEL, CodexCliLLMProvider
from .parsing import _normalized_provider_name
from .types import StreamTransport, Transport


def create_chat_provider_from_pool_entry(
    entry: PoolEntry,
    *,
    timeout: int = 60,
    transport: Transport | None = None,
    stream_transport: StreamTransport | None = None,
    codex_process_runner: Callable[..., Any] = subprocess.run,
    codex_executable_resolver: Callable[[str], str | None] = shutil.which,
) -> Any:
    """Create the chat-style provider represented by one TOML pool entry."""
    if _normalized_provider_name(entry.provider) == "codex":
        return CodexCliLLMProvider(
            workspace_root=_option_string(entry, "workspace_root"),
            executable=_option_string(entry, "executable") or "codex",
            codex_home=_option_string(entry, "codex_home"),
            model=None if entry.model == CODEX_DEFAULT_MODEL_LABEL else entry.model,
            profile=_option_string(entry, "profile"),
            timeout=timeout,
            process_runner=codex_process_runner,
            executable_resolver=codex_executable_resolver,
            skip_git_repo_check=_option_bool(entry, "skip_git_repo_check", default=True),
            inherit_proxy_env=_option_bool(entry, "inherit_proxy_env", default=False),
        )
    if _is_deepseek_entry(entry):
        return DeepSeekChatProvider(
            api_key=entry.api_key,
            model=entry.model,
            base_url=entry.base_url,
            timeout=timeout,
            transport=transport,
            stream_transport=stream_transport,
        )
    return OpenAICompatibleChatProvider(
        provider=entry.provider,
        api_key=entry.api_key,
        base_url=entry.base_url,
        model=entry.model,
        timeout=timeout,
        transport=transport,
        stream_transport=stream_transport,
    )


def _is_deepseek_entry(entry: PoolEntry) -> bool:
    if _normalized_provider_name(entry.provider) == "deepseek":
        return True
    host = urlparse(entry.base_url).hostname or ""
    return host.lower() == "api.deepseek.com"


def _option_string(entry: PoolEntry, name: str) -> str | None:
    value = entry.options.get(name)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _option_bool(entry: PoolEntry, name: str, *, default: bool) -> bool:
    value = entry.options.get(name)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return default
