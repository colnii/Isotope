"""Environment-based LLM provider resolution."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...integrations.codex.task import CodexTaskNotConfiguredError
from ..pool import resolve_pool_entries_from_env
from .clients import (
    DeepSeekChatProvider,
    DeepSeekToolCallProvider,
    OpenAICompatibleToolCallProvider,
)
from .codex import CodexCliLLMProvider
from .codex_api import CodexApiLLMProvider
from .factory import create_chat_provider_from_pool_entry
from .parsing import _env_string, _normalized_provider_name, _resolve_provider_timeout
from .types import LLMProviderResolution, Transport

DEFAULT_CHAT_POOL_PATH = (
    Path(__file__).resolve().parents[2]
    / "features"
    / "supervisor"
    / "supervisor_llm_pool.toml"
)


def resolve_llm_tool_call_provider(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
    codex_process_runner: Any = subprocess.run,
    codex_executable_resolver: Any = shutil.which,
) -> LLMProviderResolution:
    """Resolve the configured model tool-call provider without exposing secrets."""

    env = os.environ if environ is None else environ
    provider_name = _normalized_provider_name(_env_string(env, "ISOTOPE_LLM_PROVIDER"))
    if not provider_name:
        provider_name = "deepseek" if _env_string(env, "DEEPSEEK_API_KEY") else ""
    if not provider_name:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_not_configured",
            provider_name="auto",
        )
    if provider_name == "codex":
        timeout = _resolve_provider_timeout(env)
        if timeout is None:
            return LLMProviderResolution(
                status="missing_configuration",
                reason_code="llm_provider_invalid_configuration",
                provider_name=provider_name,
            )
        return _resolve_codex_provider(
            env,
            timeout=timeout,
            process_runner=codex_process_runner,
            executable_resolver=codex_executable_resolver,
        )

    timeout = _resolve_provider_timeout(env)
    if timeout is None:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
            provider_name=provider_name,
        )

    if provider_name == "mimo":
        return _resolve_mimo_tool_call_provider(
            env,
            timeout=timeout,
            transport=transport,
        )

    if provider_name == "codex-api":
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_unsupported",
            provider_name=provider_name,
        )

    if provider_name != "deepseek":
        return _resolve_pool_tool_call_provider(
            env,
            provider_name=provider_name,
            timeout=timeout,
            transport=transport,
        )

    api_key = _env_string(env, "ISOTOPE_LLM_API_KEY") or _env_string(env, "DEEPSEEK_API_KEY")
    if not api_key:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_api_key_missing",
            provider_name=provider_name,
        )

    provider = DeepSeekToolCallProvider(
        api_key=api_key,
        model=_env_string(env, "ISOTOPE_LLM_MODEL")
        or _env_string(env, "DEEPSEEK_MODEL")
        or "deepseek-v4-flash",
        base_url=_env_string(env, "ISOTOPE_LLM_BASE_URL")
        or _env_string(env, "DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com",
        timeout=timeout,
        transport=transport,
    )
    return LLMProviderResolution(
        status="configured",
        reason_code="llm_provider_configured",
        provider_name=provider.provider,
        provider=provider,
    )


def _resolve_mimo_tool_call_provider(
    env: Mapping[str, str],
    *,
    timeout: int,
    transport: Transport | None,
) -> LLMProviderResolution:
    api_key = _env_string(env, "ISOTOPE_LLM_API_KEY") or _env_string(env, "MIMO_API_KEY")
    if not api_key:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_api_key_missing",
            provider_name="mimo",
        )
    try:
        provider = OpenAICompatibleToolCallProvider(
            provider="mimo",
            api_key=api_key,
            model=_env_string(env, "ISOTOPE_LLM_MODEL")
            or _env_string(env, "MIMO_MODEL")
            or "mimo-v2.5",
            base_url=_env_string(env, "ISOTOPE_LLM_BASE_URL")
            or _env_string(env, "MIMO_BASE_URL")
            or "https://token-plan-cn.xiaomimimo.com/v1",
            timeout=timeout,
            transport=transport,
        )
    except ValueError:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
            provider_name="mimo",
        )
    return LLMProviderResolution(
        status="configured",
        reason_code="llm_provider_configured",
        provider_name=provider.provider,
        provider=provider,
    )


def _resolve_pool_tool_call_provider(
    env: Mapping[str, str],
    *,
    provider_name: str,
    timeout: int,
    transport: Transport | None,
) -> LLMProviderResolution:
    pool_env = dict(env)
    if "ISOTOPE_LLM_POOL_TOML_FILES" not in pool_env:
        supervisor_pool_files = _env_string(pool_env, "SUPERVISOR_LLM_POOL_TOML_FILES")
        if supervisor_pool_files:
            pool_env["ISOTOPE_LLM_POOL_TOML_FILES"] = supervisor_pool_files
    try:
        entries = resolve_pool_entries_from_env(
            pool_env,
            env_var="ISOTOPE_LLM_POOL_TOML_FILES",
            default_paths=(DEFAULT_CHAT_POOL_PATH,),
        )
    except ValueError:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
            provider_name=provider_name,
        )
    for entry in entries:
        if _normalized_provider_name(entry.provider) != provider_name:
            continue
        try:
            provider = OpenAICompatibleToolCallProvider(
                provider=entry.provider,
                api_key=entry.api_key,
                base_url=entry.base_url,
                model=entry.model,
                timeout=timeout,
                transport=transport,
            )
        except ValueError:
            return LLMProviderResolution(
                status="missing_configuration",
                reason_code="llm_provider_invalid_configuration",
                provider_name=provider_name,
            )
        return LLMProviderResolution(
            status="configured",
            reason_code="llm_provider_configured",
            provider_name=provider.provider,
            provider=provider,
        )
    return LLMProviderResolution(
        status="missing_configuration",
        reason_code="llm_provider_unsupported",
        provider_name=provider_name,
    )


def resolve_llm_chat_provider(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
    codex_process_runner: Any = subprocess.run,
    codex_executable_resolver: Any = shutil.which,
) -> LLMProviderResolution:
    """Resolve a direct chat provider from the same first-class provider config."""
    env = os.environ if environ is None else environ
    provider_name = _normalized_provider_name(_env_string(env, "ISOTOPE_LLM_PROVIDER"))
    if not provider_name:
        provider_name = "deepseek" if _env_string(env, "DEEPSEEK_API_KEY") else ""
    if not provider_name:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_not_configured",
            provider_name="auto",
        )
    timeout = _resolve_provider_timeout(env)
    if timeout is None:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
            provider_name=provider_name,
        )
    if provider_name == "codex":
        return _resolve_codex_provider(
            env,
            timeout=timeout,
            process_runner=codex_process_runner,
            executable_resolver=codex_executable_resolver,
        )
    if provider_name == "codex-api":
        return _resolve_codex_api_provider(
            env,
            timeout=timeout,
            executable_resolver=codex_executable_resolver,
        )
    if provider_name != "deepseek":
        return _resolve_pool_chat_provider(
            env,
            provider_name=provider_name,
            timeout=timeout,
            transport=transport,
            codex_process_runner=codex_process_runner,
            codex_executable_resolver=codex_executable_resolver,
        )

    api_key = _env_string(env, "ISOTOPE_LLM_API_KEY") or _env_string(env, "DEEPSEEK_API_KEY")
    if not api_key:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_api_key_missing",
            provider_name=provider_name,
        )
    provider = DeepSeekChatProvider(
        api_key=api_key,
        model=_env_string(env, "ISOTOPE_LLM_MODEL")
        or _env_string(env, "DEEPSEEK_MODEL")
        or "deepseek-v4-flash",
        base_url=_env_string(env, "ISOTOPE_LLM_BASE_URL")
        or _env_string(env, "DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com",
        timeout=timeout,
        transport=transport,
    )
    return LLMProviderResolution(
        status="configured",
        reason_code="llm_provider_configured",
        provider_name=provider.provider,
        provider=provider,
    )


def _resolve_pool_chat_provider(
    env: Mapping[str, str],
    *,
    provider_name: str,
    timeout: int,
    transport: Transport | None,
    codex_process_runner: Any,
    codex_executable_resolver: Any,
) -> LLMProviderResolution:
    pool_env = dict(env)
    if "ISOTOPE_LLM_POOL_TOML_FILES" not in pool_env:
        supervisor_pool_files = _env_string(pool_env, "SUPERVISOR_LLM_POOL_TOML_FILES")
        if supervisor_pool_files:
            pool_env["ISOTOPE_LLM_POOL_TOML_FILES"] = supervisor_pool_files
    try:
        entries = resolve_pool_entries_from_env(
            pool_env,
            env_var="ISOTOPE_LLM_POOL_TOML_FILES",
            default_paths=(DEFAULT_CHAT_POOL_PATH,),
        )
    except ValueError:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
            provider_name=provider_name,
        )
    for entry in entries:
        if _normalized_provider_name(entry.provider) != provider_name:
            continue
        try:
            provider = create_chat_provider_from_pool_entry(
                entry,
                timeout=timeout,
                transport=transport,
                codex_process_runner=codex_process_runner,
                codex_executable_resolver=codex_executable_resolver,
            )
        except ValueError:
            return LLMProviderResolution(
                status="missing_configuration",
                reason_code="llm_provider_invalid_configuration",
                provider_name=provider_name,
            )
        return LLMProviderResolution(
            status="configured",
            reason_code="llm_provider_configured",
            provider_name=provider.provider,
            provider=provider,
        )
    return LLMProviderResolution(
        status="missing_configuration",
        reason_code="llm_provider_unsupported",
        provider_name=provider_name,
    )


def _resolve_codex_provider(
    env: Mapping[str, str],
    *,
    timeout: int,
    process_runner: Any,
    executable_resolver: Any,
) -> LLMProviderResolution:
    try:
        provider = CodexCliLLMProvider(
            workspace_root=_env_string(env, "ISOTOPE_CODEX_WORKSPACE_ROOT") or os.getcwd(),
            executable=_env_string(env, "ISOTOPE_CODEX_EXECUTABLE") or "codex",
            codex_home=_optional_env_string(env, "ISOTOPE_CODEX_HOME"),
            model=_optional_env_string(env, "ISOTOPE_LLM_MODEL")
            or _optional_env_string(env, "CODEX_MODEL"),
            profile=_optional_env_string(env, "ISOTOPE_CODEX_PROFILE"),
            timeout=timeout,
            process_runner=process_runner,
            executable_resolver=executable_resolver,
            skip_git_repo_check=_env_bool(
                env,
                "ISOTOPE_CODEX_SKIP_GIT_REPO_CHECK",
                default=True,
            ),
            inherit_proxy_env=_env_bool(
                env,
                "ISOTOPE_CODEX_INHERIT_PROXY_ENV",
                default=False,
            ),
        )
    except CodexTaskNotConfiguredError:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_codex_cli_missing",
            provider_name="codex",
        )
    except ValueError:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
            provider_name="codex",
        )
    return LLMProviderResolution(
        status="configured",
        reason_code="llm_provider_configured",
        provider_name=provider.provider,
        provider=provider,
    )


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


def _env_bool(env: Mapping[str, str], name: str, *, default: bool) -> bool:
    value = _env_string(env, name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _optional_env_string(env: Mapping[str, str], name: str) -> str | None:
    value = _env_string(env, name)
    return value or None
