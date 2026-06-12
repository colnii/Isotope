"""Environment-based LLM provider resolution."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from typing import Any

from ...integrations.codex.task import CodexTaskNotConfiguredError
from .clients import DeepSeekChatProvider, DeepSeekToolCallProvider
from .codex import CodexCliLLMProvider
from .codex_api import CodexApiLLMProvider
from .parsing import _env_string, _normalized_provider_name, _resolve_provider_timeout
from .types import LLMProviderResolution, Transport


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

    if provider_name != "deepseek":
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_unsupported",
            provider_name=provider_name,
        )

    api_key = _env_string(env, "ISOTOPE_LLM_API_KEY") or _env_string(env, "DEEPSEEK_API_KEY")
    if not api_key:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_api_key_missing",
            provider_name=provider_name,
        )

    timeout = _resolve_provider_timeout(env)
    if timeout is None:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
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
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_unsupported",
            provider_name=provider_name,
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
