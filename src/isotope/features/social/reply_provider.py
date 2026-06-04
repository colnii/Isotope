"""Reply generation providers for social-agent turns."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from ...llm.prompts import load_system_prompt, render_json_prompt_template
from .decision import SocialDecisionRequest
from .messages import _required_string_value


@dataclass(frozen=True)
class SocialReplyDraft:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required_string_value(self.text, "reply draft text")
        if not isinstance(self.metadata, dict):
            raise ValueError("reply draft metadata must be a dict")


class SocialReplyProvider(Protocol):
    def generate_reply(
        self,
        request: SocialDecisionRequest,
        *,
        wake_reason: str,
    ) -> SocialReplyDraft:
        ...


@dataclass(frozen=True)
class DeterministicSocialReplyProvider:
    def generate_reply(
        self,
        request: SocialDecisionRequest,
        *,
        wake_reason: str,
    ) -> SocialReplyDraft:
        if not isinstance(request, SocialDecisionRequest):
            raise ValueError("request must be a SocialDecisionRequest")
        _required_string_value(wake_reason, "wake_reason")
        persona = _dict_field(request.context, "persona_instructions")
        chat_context = _dict_field(request.context, "chat_context")
        current_message = _dict_field(chat_context, "current_message")
        return SocialReplyDraft(
            text="我看到了，先按上下文处理。",
            metadata={
                "provider": "deterministic",
                "role_name": str(persona.get("role_name", "")),
                "wake_reason": wake_reason,
                "current_message_id": str(current_message.get("message_id", "")),
            },
        )


@dataclass(frozen=True)
class LLMSocialReplyProvider:
    chat_provider: Any
    max_tokens: int = 256

    def __post_init__(self) -> None:
        if not hasattr(self.chat_provider, "generate"):
            raise ValueError("chat_provider must provide generate")
        if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int):
            raise ValueError("max_tokens must be a positive integer")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")

    def generate_reply(
        self,
        request: SocialDecisionRequest,
        *,
        wake_reason: str,
    ) -> SocialReplyDraft:
        if not isinstance(request, SocialDecisionRequest):
            raise ValueError("request must be a SocialDecisionRequest")
        clean_reason = _required_string_value(wake_reason, "wake_reason")
        response = self.chat_provider.generate(
            [
                {"role": "system", "content": load_system_prompt("social_reply")},
                {
                    "role": "user",
                    "content": render_json_prompt_template(
                        "social_reply_user",
                        {
                            "wake_reason": clean_reason,
                            "persona_instructions": _dict_field(
                                request.context,
                                "persona_instructions",
                            ),
                            "chat_context": _dict_field(request.context, "chat_context"),
                            "required_json_shape": {"text": "non-empty string"},
                        },
                    ),
                },
            ],
            max_tokens=self.max_tokens,
        )
        text = _reply_text_from_content(response.content)
        return SocialReplyDraft(
            text=text,
            metadata={
                "provider": str(getattr(response, "provider", "")),
                "model": str(getattr(response, "model", "")),
                "usage": dict(getattr(response, "usage", {})),
                "wake_reason": clean_reason,
            },
        )


def _dict_field(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"{key} must be a dict")
    return item


def _reply_text_from_content(content: object) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("reply text must be a non-empty string")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("reply provider output must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("reply provider output must be a JSON object")
    return _required_string_value(payload.get("text"), "reply text")
