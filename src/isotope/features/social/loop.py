"""Deterministic social decision loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .arbiter import SocialArbiter
from .candidates import SocialActionCandidate
from .character_card import CharacterCard
from .decision import SocialDecisionRequest, SocialDecisionTurn
from .messages import SocialMessagePart
from .reply_provider import DeterministicSocialReplyProvider, SocialReplyProvider
from .replies import SocialReplyAction
from .stickers import StickerSelectionRequest, recent_successful_sticker_ids


@dataclass(frozen=True)
class SocialDecisionLoop:
    arbiter: SocialArbiter = SocialArbiter()
    reply_provider: SocialReplyProvider = DeterministicSocialReplyProvider()

    def decide(self, request: SocialDecisionRequest) -> SocialDecisionTurn:
        if not isinstance(request, SocialDecisionRequest):
            raise ValueError("request must be a SocialDecisionRequest")
        character_card = _character_card_from_context(request.context)
        suppress_reason = _recent_send_suppression_reason(request)
        if suppress_reason is not None:
            silent = _silent_candidate(suppress_reason, confidence=1.0)
            return SocialDecisionTurn(
                proposed=(silent,),
                selected=(silent,),
                rejected={},
                dry_run=request.dry_run,
            )

        wake_reasons = _wake_reasons(request, character_card)
        if not wake_reasons:
            silent = _silent_candidate("no_wake_reason", confidence=0.5)
            return SocialDecisionTurn(
                proposed=(silent,),
                selected=(silent,),
                rejected={},
                dry_run=request.dry_run,
            )

        proposed = _reply_candidates(
            request,
            character_card,
            wake_reasons[0],
            reply_provider=self.reply_provider,
        )
        if request.dry_run:
            return SocialDecisionTurn(
                proposed=proposed,
                selected=(),
                rejected={
                    candidate.candidate_id: "dry_run:not selected for sending"
                    for candidate in proposed
                    if candidate.is_send_action
                },
                dry_run=True,
            )
        result = self.arbiter.choose(proposed)
        return SocialDecisionTurn(
            proposed=proposed,
            selected=result.selected,
            rejected=result.rejected,
            dry_run=False,
        )


def _character_card_from_context(context: dict[str, Any]) -> CharacterCard:
    data = context.get("character_card")
    if not isinstance(data, dict):
        raise ValueError("decision context.character_card must be a dict")
    return CharacterCard.from_dict(data)


def _recent_send_suppression_reason(
    request: SocialDecisionRequest,
) -> str | None:
    for feedback in request.recent_send_feedback:
        if feedback.status in {"sent", "partial"} and feedback.sent_message_ids:
            if recent_successful_sticker_ids((feedback,)):
                continue
            return f"recent_send_feedback:{feedback.status}"
    return None


def _wake_reasons(
    request: SocialDecisionRequest,
    character_card: CharacterCard,
) -> tuple[str, ...]:
    message = _message_from_context(request.context)
    reasons: list[str] = []
    if _message_mentions_bot(message, request.bot_user_id):
        reasons.append(f"mention:{request.bot_user_id}")
    text = str(message.get("text", ""))
    for keyword in request.wake_keywords:
        if keyword in text:
            reasons.append(f"keyword:{keyword}")
    talkativeness = character_card.social_behavior.talkativeness
    if request.autonomy_score <= talkativeness:
        reasons.append(f"autonomous:{request.autonomy_score:g}<={talkativeness:g}")
    return tuple(reasons)


def _reply_candidates(
    request: SocialDecisionRequest,
    character_card: CharacterCard,
    reason: str,
    reply_provider: SocialReplyProvider | None = None,
) -> tuple[SocialActionCandidate, ...]:
    sticker_candidate = _sticker_candidate(request, character_card, reason)
    if sticker_candidate is not None:
        return (sticker_candidate,)
    provider = reply_provider or DeterministicSocialReplyProvider()
    draft = provider.generate_reply(request, wake_reason=reason)
    return (
        SocialActionCandidate(
            candidate_id="reply_text",
            agent_id=character_card.identity.name,
            kind="respond",
            reason=reason,
            confidence=0.7,
            reply_action=SocialReplyAction(
                action_id="reply_text",
                target=request.target,
                parts=(
                    SocialMessagePart(
                        kind="text",
                        text=draft.text,
                    ),
                ),
            ),
            metadata={"reply_provider": dict(draft.metadata)},
        ),
    )


def _sticker_candidate(
    request: SocialDecisionRequest,
    character_card: CharacterCard,
    reason: str,
) -> SocialActionCandidate | None:
    if request.sticker_library is None:
        return None
    group_id = _group_id_from_context(request.context)
    selected = request.sticker_library.select(
        StickerSelectionRequest(
            group_id=group_id,
            emotion=request.sticker_emotion,
            scene_tags=request.sticker_scene_tags,
            character_stickers=character_card.stickers,
            allow_sticker_only=request.allow_sticker_only,
            recent_send_feedback=request.recent_send_feedback,
        )
    )
    if selected is None:
        return None
    return SocialActionCandidate(
        candidate_id="reply_sticker",
        agent_id=character_card.identity.name,
        kind="respond",
        reason=reason,
        confidence=0.9,
        reply_action=selected.to_reply_action(
            action_id="reply_sticker",
            target=request.target,
        ),
        metadata={"sticker_selection": selected.to_public_dict()},
    )


def _silent_candidate(reason: str, *, confidence: float) -> SocialActionCandidate:
    return SocialActionCandidate(
        candidate_id="silent",
        agent_id="social_decision_loop",
        kind="silent",
        reason=reason,
        confidence=confidence,
    )


def _message_from_context(context: dict[str, Any]) -> dict[str, Any]:
    message = context.get("message")
    if not isinstance(message, dict):
        raise ValueError("decision context.message must be a dict")
    return message


def _group_id_from_context(context: dict[str, Any]) -> str:
    group_id = context.get("group_id")
    if not isinstance(group_id, str) or not group_id.strip():
        raise ValueError("decision context.group_id must be a non-empty string")
    return group_id.strip()


def _message_mentions_bot(message: dict[str, Any], bot_user_id: str) -> bool:
    mentions = message.get("mentions", [])
    if isinstance(mentions, list) and bot_user_id in mentions:
        return True
    parts = message.get("parts", [])
    if not isinstance(parts, list):
        return False
    for part in parts:
        if (
            isinstance(part, dict)
            and part.get("kind") == "mention"
            and part.get("user_id") == bot_user_id
        ):
            return True
    return False
