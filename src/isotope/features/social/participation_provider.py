"""LLM-backed social participation decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ...llm.provider.parsing import parse_model_json_object_content
from ...llm.prompts import load_system_prompt, render_json_prompt_template
from .decision import SocialDecisionRequest

from .messages import _required_string_value


class SocialParticipationProvider(Protocol):
    def decide(
        self,
        request: SocialDecisionRequest,
        *,
        wake_signals: tuple[str, ...],
    ) -> "LLMParticipationDecision":
        ...


@dataclass(frozen=True)
class LLMParticipationDecision:
    action: str
    reason: str
    confidence: float
    text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action not in {"respond", "silent"}:
            raise ValueError("participation action must be respond or silent")
        _required_string_value(self.reason, "participation reason")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("participation confidence must be between 0 and 1")
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("participation confidence must be between 0 and 1")
        if self.action == "respond":
            _required_string_value(self.text, "participation text")
        elif self.text is not None and not isinstance(self.text, str):
            raise ValueError("participation text must be a string")
        if not isinstance(self.metadata, dict):
            raise ValueError("participation metadata must be a dict")


@dataclass(frozen=True)
class LLMSocialParticipationProvider:
    chat_provider: Any
    max_tokens: int = 256

    def __post_init__(self) -> None:
        if not hasattr(self.chat_provider, "generate"):
            raise ValueError("chat_provider must provide generate")
        if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int):
            raise ValueError("max_tokens must be a positive integer")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")

    def decide(
        self,
        request: SocialDecisionRequest,
        *,
        wake_signals: tuple[str, ...],
    ) -> LLMParticipationDecision:
        if not isinstance(request, SocialDecisionRequest):
            raise ValueError("request must be a SocialDecisionRequest")
        response = self.chat_provider.generate(
            [
                {
                    "role": "system",
                    "content": load_system_prompt("social_participation"),
                },
                {
                    "role": "user",
                    "content": render_json_prompt_template(
                        "social_participation_user",
                        {
                            "persona_instructions": _dict_field(
                                request.context,
                                "persona_instructions",
                            ),
                            "chat_context": _dict_field(request.context, "chat_context"),
                            "wake_signals": list(wake_signals),
                            "dry_run": request.dry_run,
                            "required_json_shape": {
                                "action": "respond or silent",
                                "reason": "non-empty short string",
                                "confidence": "number from 0 to 1",
                                "text": "required only when action is respond",
                            },
                        },
                    ),
                },
            ],
            max_tokens=self.max_tokens,
        )
        decision = participation_decision_from_content(response.content)
        return LLMParticipationDecision(
            action=decision.action,
            reason=decision.reason,
            confidence=decision.confidence,
            text=decision.text,
            metadata={
                "provider": str(getattr(response, "provider", "")),
                "model": str(getattr(response, "model", "")),
                "usage": dict(getattr(response, "usage", {})),
            },
        )


def participation_decision_from_content(content: object) -> LLMParticipationDecision:
    payload = parse_model_json_object_content(
        content,
        error_message="participation provider output must be a JSON object",
    )
    action = _required_string_value(payload.get("action"), "participation action")
    reason = _required_string_value(payload.get("reason"), "participation reason")
    confidence = payload.get("confidence")
    text = payload.get("text")
    if action == "respond" and (not isinstance(text, str) or not text.strip()):
        raise ValueError("respond decisions require text")
    return LLMParticipationDecision(
        action=action,
        reason=reason,
        confidence=_confidence(confidence),
        text=text.strip() if isinstance(text, str) and text.strip() else None,
    )


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("participation confidence must be between 0 and 1")
    parsed = float(value)
    if parsed < 0 or parsed > 1:
        raise ValueError("participation confidence must be between 0 and 1")
    return parsed


def _dict_field(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"{key} must be a dict")
    return item
