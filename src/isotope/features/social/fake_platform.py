"""In-memory fake social platform for integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .character_card import CharacterCard
from .context_builder import SocialContextBuilder
from .decision import SocialDecisionRequest, SocialDecisionTurn
from .loop import SocialDecisionLoop
from .lorebook import Lorebook
from .messages import SocialMessage, SocialMessagePart, _required_string_value
from .replies import SocialReplyAction, SocialTarget
from .send_feedback import SocialSendChunk, SocialSendFeedback
from .stickers import StickerLibrary


@dataclass
class SocialFakePlatform:
    platform: str
    group_id: str
    bot_user_id: str
    _incoming_messages: list[SocialMessage] = field(default_factory=list)
    _outgoing_actions: list[SocialReplyAction] = field(default_factory=list)
    _send_feedback: list[SocialSendFeedback] = field(default_factory=list)

    def __post_init__(self) -> None:
        _required_string_value(self.platform, "fake platform")
        _required_string_value(self.group_id, "fake group_id")
        _required_string_value(self.bot_user_id, "fake bot_user_id")

    @property
    def incoming_messages(self) -> tuple[SocialMessage, ...]:
        return tuple(self._incoming_messages)

    @property
    def outgoing_actions(self) -> tuple[SocialReplyAction, ...]:
        return tuple(self._outgoing_actions)

    @property
    def send_feedback(self) -> tuple[SocialSendFeedback, ...]:
        return tuple(self._send_feedback)

    def emit_message(self, message: SocialMessage) -> None:
        if not isinstance(message, SocialMessage):
            raise ValueError("message must be a SocialMessage")
        self._incoming_messages.append(message)

    def receive_next(self) -> SocialMessage:
        if not self._incoming_messages:
            raise ValueError("no incoming messages queued")
        return self._incoming_messages.pop(0)

    def send(self, action: SocialReplyAction) -> SocialSendFeedback:
        if not isinstance(action, SocialReplyAction):
            raise ValueError("action must be a SocialReplyAction")
        self._outgoing_actions.append(action)
        sent_id = f"fake_sent_{len(self._outgoing_actions)}"
        feedback = SocialSendFeedback(
            status="sent",
            sent_message_ids=(sent_id,),
            chunks=(
                SocialSendChunk(
                    message_id=sent_id,
                    parts=action.parts,
                    rendered_preview=_render_preview(action.parts),
                ),
            ),
            recent_messages_after_send=(
                {
                    "message_id": sent_id,
                    "sender": self.bot_user_id,
                    "preview": _render_preview(action.parts),
                },
            ),
        )
        self._send_feedback.append(feedback)
        return feedback

    def recent_message_previews(self) -> tuple[dict[str, Any], ...]:
        previews = []
        for feedback in self._send_feedback:
            previews.extend(dict(item) for item in feedback.recent_messages_after_send)
        return tuple(previews)


@dataclass(frozen=True)
class SocialFakePlatformTurn:
    message: SocialMessage
    context: dict[str, Any]
    decision: SocialDecisionTurn
    send_feedback: tuple[SocialSendFeedback, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.message, SocialMessage):
            raise ValueError("turn message must be a SocialMessage")
        if not isinstance(self.context, dict):
            raise ValueError("turn context must be a dict")
        if not isinstance(self.decision, SocialDecisionTurn):
            raise ValueError("turn decision must be a SocialDecisionTurn")
        if not isinstance(self.send_feedback, tuple):
            raise ValueError("turn send_feedback must be a tuple")
        for feedback in self.send_feedback:
            if not isinstance(feedback, SocialSendFeedback):
                raise ValueError("turn send_feedback items must be SocialSendFeedback")


@dataclass(frozen=True)
class SocialFakePlatformHarness:
    platform: SocialFakePlatform
    character_card: CharacterCard
    lorebook: Lorebook | None = None
    sticker_library: StickerLibrary | None = None
    decision_loop: SocialDecisionLoop = SocialDecisionLoop()

    def __post_init__(self) -> None:
        if not isinstance(self.platform, SocialFakePlatform):
            raise ValueError("platform must be a SocialFakePlatform")
        if not isinstance(self.character_card, CharacterCard):
            raise ValueError("character_card must be a CharacterCard")
        if self.lorebook is not None and not isinstance(self.lorebook, Lorebook):
            raise ValueError("lorebook must be a Lorebook")
        if self.sticker_library is not None and not isinstance(
            self.sticker_library,
            StickerLibrary,
        ):
            raise ValueError("sticker_library must be a StickerLibrary")
        if not isinstance(self.decision_loop, SocialDecisionLoop):
            raise ValueError("decision_loop must be a SocialDecisionLoop")

    def process_next(
        self,
        *,
        wake_keywords: tuple[str, ...] = (),
        autonomy_score: float = 1.0,
        dry_run: bool = False,
        sticker_emotion: str = "ack",
        sticker_scene_tags: tuple[str, ...] = (),
        allow_sticker_only: bool = False,
    ) -> SocialFakePlatformTurn:
        message = self.platform.receive_next()
        group_id = message.group_id or self.platform.group_id
        context = SocialContextBuilder(
            character_card=self.character_card,
            lorebook=self.lorebook,
        ).build(
            group_id=group_id,
            message=message,
            recent_messages=self.platform.recent_message_previews(),
        )
        decision = self.decision_loop.decide(
            SocialDecisionRequest(
                context=context,
                target=SocialTarget(
                    platform=self.platform.platform,
                    chat_type=message.chat_type,
                    group_id=group_id,
                ),
                bot_user_id=self.platform.bot_user_id,
                wake_keywords=wake_keywords,
                autonomy_score=autonomy_score,
                recent_send_feedback=self.platform.send_feedback,
                dry_run=dry_run,
                sticker_library=self.sticker_library,
                sticker_emotion=sticker_emotion,
                sticker_scene_tags=sticker_scene_tags,
                allow_sticker_only=allow_sticker_only,
            )
        )
        feedback: list[SocialSendFeedback] = []
        if not dry_run:
            for candidate in decision.selected:
                if candidate.is_send_action and candidate.reply_action is not None:
                    feedback.append(self.platform.send(candidate.reply_action))
        return SocialFakePlatformTurn(
            message=message,
            context=context,
            decision=decision,
            send_feedback=tuple(feedback),
        )


def _render_preview(parts: tuple[SocialMessagePart, ...]) -> str:
    rendered: list[str] = []
    for part in parts:
        if part.kind == "text":
            rendered.append(part.text)
        elif part.media_ref:
            rendered.append(f"[{part.kind}: {part.media_ref}]")
        elif part.user_id:
            rendered.append(f"[{part.kind}: {part.user_id}]")
        else:
            rendered.append(f"[{part.kind}]")
    return "".join(rendered).strip()
