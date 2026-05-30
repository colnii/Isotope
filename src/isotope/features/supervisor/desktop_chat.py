"""Desktop chat answer flow over the low-sensitive Supervisor snapshot."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from isotope.llm.provider import LLMResponse, LLMStreamChunk

from .desktop_snapshot import build_desktop_snapshot


class DesktopChatProvider(Protocol):
    provider: str
    model: str

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        ...


@dataclass(frozen=True)
class DesktopChatAnswer:
    question: str
    answer: str
    provider: str
    model: str

    def done_payload(self) -> dict[str, str]:
        return {
            "status": "ok",
            "provider": self.provider,
            "model": self.model,
        }


def answer_desktop_chat(
    *,
    codex_home: Path | str,
    question: str,
    provider: DesktopChatProvider,
    max_tokens: int = 512,
) -> DesktopChatAnswer:
    clean_question = _require_question(question)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    snapshot = build_desktop_snapshot(codex_home=codex_home)
    response = provider.generate(
        _desktop_chat_messages(clean_question, snapshot),
        max_tokens=max_tokens,
    )
    answer = response.content.strip()
    if not answer:
        raise ValueError("provider returned empty answer")
    return DesktopChatAnswer(
        question=clean_question,
        answer=answer,
        provider=response.provider,
        model=response.model,
    )


def stream_desktop_chat(
    *,
    codex_home: Path | str,
    question: str,
    provider: DesktopChatProvider,
    max_tokens: int = 512,
) -> Iterator[LLMStreamChunk]:
    clean_question = _require_question(question)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    stream_generate = getattr(provider, "stream_generate", None)
    if callable(stream_generate):
        snapshot = build_desktop_snapshot(codex_home=codex_home)
        yielded = False
        for chunk in stream_generate(
            _desktop_chat_messages(clean_question, snapshot),
            max_tokens=max_tokens,
        ):
            if not isinstance(chunk, LLMStreamChunk):
                raise ValueError("provider returned malformed stream chunk")
            if not chunk.content:
                continue
            yielded = True
            yield chunk
        if not yielded:
            raise ValueError("provider returned empty answer")
        return

    answer = answer_desktop_chat(
        codex_home=codex_home,
        question=clean_question,
        provider=provider,
        max_tokens=max_tokens,
    )
    for chunk in desktop_chat_answer_chunks(answer.answer):
        yield LLMStreamChunk(
            provider=answer.provider,
            model=answer.model,
            content=chunk,
            raw={},
        )


def desktop_chat_answer_chunks(answer: str, *, chunk_size: int = 12) -> list[str]:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    return [answer[index : index + chunk_size] for index in range(0, len(answer), chunk_size)]


def _desktop_chat_messages(question: str, snapshot: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是 Isotope 桌面端助手。只根据提供的低敏 Supervisor 状态回答，"
                "不要编造不存在的 worker、goal、approval 或 artifact。回答要短，"
                "用中文，说人话，优先说明当前 loop 能不能继续推进。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "desktop_snapshot": snapshot,
                    "output_requirements": [
                        "不要输出 JSON",
                        "一到三句话",
                        "只描述低敏状态",
                        "能给下一步就给下一步",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _require_question(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("question must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError("question must not be empty")
    return stripped
