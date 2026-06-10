"""Provider generation helpers for Supervisor conversation loops."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Protocol

from isotope.llm.provider import LLMResponse


class ConversationGenerationProvider(Protocol):
    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        raise NotImplementedError


def generate_with_timeout(
    provider: ConversationGenerationProvider,
    *,
    messages: list[dict[str, Any]],
    max_tokens: int,
    timeout_seconds: float | None,
) -> LLMResponse:
    if timeout_seconds is None:
        return provider.generate(messages, max_tokens=max_tokens)
    if timeout_seconds <= 0:
        raise TimeoutError("desktop chat response timed out")
    executor = ThreadPoolExecutor(max_workers=1)
    pending_call = executor.submit(provider.generate, messages, max_tokens=max_tokens)
    try:
        return pending_call.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        pending_call.cancel()
        raise TimeoutError("desktop chat response timed out") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
