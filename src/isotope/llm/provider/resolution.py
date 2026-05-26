"""Environment-based LLM provider resolution."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .clients import DeepSeekToolCallProvider
from .parsing import _env_string, _normalized_provider_name, _resolve_provider_timeout
from .types import LLMProviderResolution, Transport


def resolve_llm_tool_call_provider(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
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
