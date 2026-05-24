"""Configuration objects for LLM live smoke helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_LLM_LIVE_SMOKE_PROMPT = (
    "Call the codex_task tool exactly once. "
    "Use prompt 'Reply exactly ISOTOPE_LLM_TOOL_CALL_SMOKE_OK.' "
    "Use summary 'LLM tool call live smoke'."
)
DEFAULT_DEEPSEEK_LIVE_SMOKE_PROMPT = DEFAULT_LLM_LIVE_SMOKE_PROMPT
DEFAULT_LLM_PRODUCT_CHAT_DIRECT_PROMPT = "Reply exactly ISOTOPE_LLM_PRODUCT_CHAT_DIRECT_OK."
DEFAULT_LLM_PRODUCT_CHAT_TOOL_PROMPT = (
    "Call the codex_task tool exactly once. "
    "Use prompt 'Reply exactly ISOTOPE_LLM_PRODUCT_CHAT_TOOL_OK.' "
    "Use summary 'LLM product chat live smoke'."
)
DEFAULT_LLM_PRODUCT_CHAT_RESUME_PROMPT = (
    "Use the tool result already provided in this conversation and reply with a short final answer."
)
DEFAULT_LLM_TERMINAL_TOOL_SMOKE_PROMPT = (
    "Call the terminal_exec tool exactly once. "
    "Use argv ['printf', 'ISOTOPE_LLM_TERMINAL_TOOL_SMOKE_OK']. "
    "Use summary 'LLM terminal tool live smoke'."
)


@dataclass(frozen=True)
class LLMToolCallLiveSmokeConfig:
    enabled: bool = False
    prompt: str = DEFAULT_LLM_LIVE_SMOKE_PROMPT
    max_tokens: int = 128
    tool_name: str = "codex_task"

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")
        _non_empty_string("prompt", self.prompt)
        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        _non_empty_string("tool_name", self.tool_name)


DeepSeekToolCallLiveSmokeConfig = LLMToolCallLiveSmokeConfig


@dataclass(frozen=True)
class LLMTerminalToolLiveSmokeConfig:
    enabled: bool = False
    prompt: str = DEFAULT_LLM_TERMINAL_TOOL_SMOKE_PROMPT
    max_tokens: int = 128

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")
        _non_empty_string("prompt", self.prompt)
        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")


@dataclass(frozen=True)
class LLMProductChatLiveSmokeConfig:
    enabled: bool = False
    direct_prompt: str = DEFAULT_LLM_PRODUCT_CHAT_DIRECT_PROMPT
    tool_prompt: str = DEFAULT_LLM_PRODUCT_CHAT_TOOL_PROMPT
    resume_prompt: str = DEFAULT_LLM_PRODUCT_CHAT_RESUME_PROMPT
    max_tokens: int = 128

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")
        _non_empty_string("direct_prompt", self.direct_prompt)
        _non_empty_string("tool_prompt", self.tool_prompt)
        _non_empty_string("resume_prompt", self.resume_prompt)
        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")


def _non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value
