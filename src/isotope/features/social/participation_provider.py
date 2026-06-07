"""LLM-backed social participation decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .messages import _required_string_value


@dataclass(frozen=True)
class LLMParticipationDecision:
    action: str
    reason: str
    confidence: float
    text: str | None = None

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


def participation_decision_from_content(content: object) -> LLMParticipationDecision:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("participation provider output must be a JSON object")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("participation provider output must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("participation provider output must be a JSON object")
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
