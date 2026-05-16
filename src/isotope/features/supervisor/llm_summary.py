"""LLM summary helpers for Codex Supervisor reports."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol

from .flow import CodexSupervisorReport


DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7-highspeed"
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
        api_key = _first_env("MINIMAX_API_KEY", "MINIMAX_TOKEN", "MINIMAX_API_TOKEN")
        if api_key is None:
            raise ValueError(
                "MINIMAX_API_KEY is required for --llm-summary "
                "(also accepts MINIMAX_TOKEN or MINIMAX_API_TOKEN)"
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


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
