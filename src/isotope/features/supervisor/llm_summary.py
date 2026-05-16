"""LLM summary helpers for Codex Supervisor reports."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Callable, Protocol

from ...llm.provider import DeepSeekChatProvider
from .flow import CodexSupervisorReport


DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_TOKENS = 512
Transport = Callable[[str, dict[str, object], dict[str, str], int], dict[str, object]]


class SummaryProvider(Protocol):
    def summarize(self, messages: list[dict[str, str]]) -> str:
        ...


class OpenAICompatibleSummaryProvider:
    """Small OpenAI-compatible chat client for supervisor summaries."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_MINIMAX_BASE_URL,
        model: str = DEFAULT_MINIMAX_MODEL,
        timeout: int = 60,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = _non_empty("api_key", api_key)
        self.base_url = _non_empty("base_url", base_url).rstrip("/")
        self.model = _non_empty("model", model)
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.transport = transport or _urllib_transport

    @classmethod
    def from_minimax_env(cls) -> "OpenAICompatibleSummaryProvider":
        api_key = _first_env(
            os.environ,
            "YIFU_MINIMAX_CODER_API_KEY",
            "YIFU_MINIMAX_API_KEY",
            "MINIMAX_API_KEY",
            "MINIMAX_TOKEN",
            "MINIMAX_API_TOKEN",
        )
        if api_key is None:
            raise ValueError(
                "MINIMAX_API_KEY is required for MiniMax summary "
                "(also accepts YIFU_MINIMAX_CODER_API_KEY, YIFU_MINIMAX_API_KEY, "
                "MINIMAX_TOKEN, or MINIMAX_API_TOKEN)"
            )
        return cls(
            api_key=api_key,
            base_url=os.environ.get("MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL),
            model=os.environ.get("MINIMAX_MODEL", DEFAULT_MINIMAX_MODEL),
            timeout=int(os.environ.get("MINIMAX_TIMEOUT", "60")),
            max_tokens=int(os.environ.get("MINIMAX_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))),
        )

    def summarize(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        raw = self.transport(
            f"{self.base_url}/chat/completions",
            payload,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            self.timeout,
        )
        return _strip_thinking(_extract_chat_content(raw))


class DeepSeekSummaryProvider:
    """Supervisor summary provider backed by the shared Isotope DeepSeek provider."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        timeout: int = 60,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        transport: Transport | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.provider = DeepSeekChatProvider(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            transport=transport,
        )

    def summarize(self, messages: list[dict[str, str]]) -> str:
        response = self.provider.generate(messages, max_tokens=self.max_tokens)
        return _strip_thinking(response.content)


def resolve_summary_provider_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
) -> SummaryProvider:
    env = os.environ if environ is None else environ
    deepseek_key = (
        _first_env(env, "ISOTOPE_LLM_API_KEY", "DEEPSEEK_API_KEY", "YIFU_DEEPSEEK_API_KEY")
    )
    if deepseek_key:
        return DeepSeekSummaryProvider(
            api_key=deepseek_key,
            model=_env_string(env, "ISOTOPE_LLM_MODEL")
            or _env_string(env, "DEEPSEEK_MODEL")
            or _env_string(env, "YIFU_DEEPSEEK_MODEL")
            or DEFAULT_DEEPSEEK_MODEL,
            base_url=_env_string(env, "ISOTOPE_LLM_BASE_URL")
            or _env_string(env, "DEEPSEEK_BASE_URL")
            or DEFAULT_DEEPSEEK_BASE_URL,
            timeout=_env_int(env, "DEEPSEEK_TIMEOUT_SECONDS", default=60),
            max_tokens=_env_int(env, "SUPERVISOR_LLM_MAX_TOKENS", default=DEFAULT_MAX_TOKENS),
            transport=transport,
        )

    minimax_key = _first_env(
        env,
        "YIFU_MINIMAX_CODER_API_KEY",
        "YIFU_MINIMAX_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_TOKEN",
        "MINIMAX_API_TOKEN",
    )
    if minimax_key:
        return OpenAICompatibleSummaryProvider(
            api_key=minimax_key,
            base_url=_env_string(env, "MINIMAX_BASE_URL") or DEFAULT_MINIMAX_BASE_URL,
            model=_env_string(env, "MINIMAX_MODEL") or DEFAULT_MINIMAX_MODEL,
            timeout=_env_int(env, "MINIMAX_TIMEOUT", default=60),
            max_tokens=_env_int(env, "MINIMAX_MAX_TOKENS", default=DEFAULT_MAX_TOKENS),
            transport=transport,
        )

    raise ValueError(
        "No summary LLM key found. Set DEEPSEEK_API_KEY, YIFU_DEEPSEEK_API_KEY, "
        "ISOTOPE_LLM_API_KEY, YIFU_MINIMAX_CODER_API_KEY, YIFU_MINIMAX_API_KEY, "
        "or MINIMAX_API_KEY."
    )


def build_llm_summary_messages(report: CodexSupervisorReport) -> list[dict[str, str]]:
    compact_sessions = [
        {
            "session_id": session.session_id,
            "cwd": session.cwd,
            "git_branch": session.git_branch,
            "status": session.status_label,
            "reason": session.reason,
            "age_seconds": session.age_seconds,
            "last_user": _clip(session.last_user_message),
            "last_reply": _clip(session.last_assistant_message),
        }
        for session in report.sessions
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是 Codex Supervisor 的中文摘要层。"
                "根据压缩后的会话状态，判断每个窗口在干什么、是否需要介入、"
                "优先处理哪个窗口。不要编造日志里没有的信息。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "generated_at": report.generated_at,
                    "sessions": compact_sessions,
                    "output_requirements": [
                        "用中文输出 3-6 行",
                        "每行都要短",
                        "说明优先处理建议",
                        "不要输出 JSON",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def generate_llm_summary(
    report: CodexSupervisorReport,
    provider: SummaryProvider,
) -> str:
    return provider.summarize(build_llm_summary_messages(report))


def _urllib_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout: int,
) -> dict[str, object]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"LLM summary request failed: HTTP {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"LLM summary request failed: {exc.reason}") from exc
    decoded = json.loads(body)
    if not isinstance(decoded, dict):
        raise ValueError("LLM summary response must be a JSON object")
    return decoded


def _extract_chat_content(raw: dict[str, object]) -> str:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM summary response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("LLM summary response choice must be an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM summary response missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM summary response missing content")
    return content.strip()


def _strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def _clip(text: str | None, *, limit: int = 160) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _first_env(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return None


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


def _non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
