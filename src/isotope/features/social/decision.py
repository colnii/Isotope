"""Decision request and result shapes for social-agent turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .candidates import SocialActionCandidate
from .messages import _required_string_value, _string_tuple
from .replies import SocialTarget
from .send_feedback import SocialSendFeedback
from .stickers import StickerLibrary


@dataclass(frozen=True)
class SocialDecisionRequest:
    context: dict[str, Any]
    target: SocialTarget
    bot_user_id: str
    wake_keywords: tuple[str, ...] = ()
    autonomy_score: float = 1.0
    recent_send_feedback: tuple[SocialSendFeedback, ...] = ()
    dry_run: bool = False
    sticker_library: StickerLibrary | None = None
    sticker_emotion: str = "ack"
    sticker_scene_tags: tuple[str, ...] = ()
    allow_sticker_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.context, dict):
            raise ValueError("decision context must be a dict")
        if not isinstance(self.target, SocialTarget):
            raise ValueError("decision target must be a SocialTarget")
        _required_string_value(self.bot_user_id, "bot_user_id")
        _string_tuple(self.wake_keywords, "wake_keywords")
        if isinstance(self.autonomy_score, bool) or not isinstance(
            self.autonomy_score,
            (int, float),
        ):
            raise ValueError("autonomy_score must be between 0 and 1")
        if self.autonomy_score < 0 or self.autonomy_score > 1:
            raise ValueError("autonomy_score must be between 0 and 1")
        if not isinstance(self.recent_send_feedback, tuple):
            raise ValueError("recent_send_feedback must be a tuple")
        for item in self.recent_send_feedback:
            if not isinstance(item, SocialSendFeedback):
                raise ValueError("recent_send_feedback items must be SocialSendFeedback")
        if not isinstance(self.dry_run, bool):
            raise ValueError("dry_run must be a bool")
        if self.sticker_library is not None and not isinstance(
            self.sticker_library,
            StickerLibrary,
        ):
            raise ValueError("sticker_library must be a StickerLibrary")
        _required_string_value(self.sticker_emotion, "sticker_emotion")
        _string_tuple(self.sticker_scene_tags, "sticker_scene_tags")
        if not isinstance(self.allow_sticker_only, bool):
            raise ValueError("allow_sticker_only must be a bool")


@dataclass(frozen=True)
class SocialDecisionTurn:
    proposed: tuple[SocialActionCandidate, ...]
    selected: tuple[SocialActionCandidate, ...]
    rejected: dict[str, str]
    dry_run: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.proposed, tuple):
            raise ValueError("proposed candidates must be a tuple")
        for candidate in self.proposed:
            if not isinstance(candidate, SocialActionCandidate):
                raise ValueError("proposed items must be SocialActionCandidate")
        if not isinstance(self.selected, tuple):
            raise ValueError("selected candidates must be a tuple")
        for candidate in self.selected:
            if not isinstance(candidate, SocialActionCandidate):
                raise ValueError("selected items must be SocialActionCandidate")
        if not isinstance(self.rejected, dict):
            raise ValueError("rejected candidates must be a dict")
        if not isinstance(self.dry_run, bool):
            raise ValueError("dry_run must be a bool")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "proposed": [candidate.to_public_dict() for candidate in self.proposed],
            "selected": [candidate.to_public_dict() for candidate in self.selected],
            "rejected": dict(self.rejected),
            "dry_run": self.dry_run,
        }
