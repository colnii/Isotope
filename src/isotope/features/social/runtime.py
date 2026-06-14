"""Runtime wiring for social adapters and the social decision loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .capability_bridge import SocialCapabilityBridge
from .candidates import SocialActionCandidate
from .character_card import CharacterCard
from .context_builder import SocialContextBuilder
from .decision import SocialDecisionRequest, SocialDecisionTurn
from .loop import SocialDecisionLoop
from .lorebook import Lorebook
from .messages import SocialMessage, SocialMessagePart, _required_string_value, _string_tuple
from .operations import SocialOperationsController, SocialPolicyDecision
from .replies import SocialReplyAction, SocialTarget
from .send_feedback import SocialSendFeedback
from .stickers import StickerLibrary


@dataclass(frozen=True)
class SocialCapabilityRuntimeConfig:
    enabled: bool = False
    capability_id: str = ""
    trigger_keywords: tuple[str, ...] = ()
    input_defaults: dict[str, Any] = field(default_factory=dict)
    query_input_key: str = "query"
    approval_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("capability enabled must be a bool")
        if self.enabled:
            _required_string_value(self.capability_id, "capability_id")
        elif self.capability_id:
            _required_string_value(self.capability_id, "capability_id")
        _string_tuple(self.trigger_keywords, "capability trigger_keywords")
        if not isinstance(self.input_defaults, dict):
            raise ValueError("capability input_defaults must be a dict")
        _required_string_value(self.query_input_key, "capability query_input_key")
        _string_tuple(self.approval_keywords, "capability approval_keywords")


@dataclass(frozen=True)
class SocialRuntimeConfig:
    bot_user_id: str
    dry_run: bool = True
    wake_keywords: tuple[str, ...] = ()
    autonomy_score: float = 1.0
    sticker_emotion: str = "ack"
    sticker_scene_tags: tuple[str, ...] = ()
    allow_sticker_only: bool = False
    capability: SocialCapabilityRuntimeConfig = field(
        default_factory=SocialCapabilityRuntimeConfig
    )

    def __post_init__(self) -> None:
        _required_string_value(self.bot_user_id, "runtime bot_user_id")
        if not isinstance(self.dry_run, bool):
            raise ValueError("runtime dry_run must be a bool")
        _string_tuple(self.wake_keywords, "runtime wake_keywords")
        if isinstance(self.autonomy_score, bool) or not isinstance(
            self.autonomy_score,
            (int, float),
        ):
            raise ValueError("runtime autonomy_score must be between 0 and 1")
        if self.autonomy_score < 0 or self.autonomy_score > 1:
            raise ValueError("runtime autonomy_score must be between 0 and 1")
        _required_string_value(self.sticker_emotion, "runtime sticker_emotion")
        _string_tuple(self.sticker_scene_tags, "runtime sticker_scene_tags")
        if not isinstance(self.allow_sticker_only, bool):
            raise ValueError("runtime allow_sticker_only must be a bool")
        if not isinstance(self.capability, SocialCapabilityRuntimeConfig):
            raise ValueError("runtime capability must be SocialCapabilityRuntimeConfig")


@dataclass(frozen=True)
class SocialRuntimeTurn:
    message: SocialMessage
    policy: SocialPolicyDecision
    context: dict[str, Any] | None = None
    decision: SocialDecisionTurn | None = None
    send_feedback: tuple[SocialSendFeedback, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.message, SocialMessage):
            raise ValueError("runtime turn message must be a SocialMessage")
        if not isinstance(self.policy, SocialPolicyDecision):
            raise ValueError("runtime turn policy must be a SocialPolicyDecision")
        if self.context is not None and not isinstance(self.context, dict):
            raise ValueError("runtime turn context must be a dict")
        if self.decision is not None and not isinstance(self.decision, SocialDecisionTurn):
            raise ValueError("runtime turn decision must be a SocialDecisionTurn")
        if not isinstance(self.send_feedback, tuple):
            raise ValueError("runtime turn send_feedback must be a tuple")
        for feedback in self.send_feedback:
            if not isinstance(feedback, SocialSendFeedback):
                raise ValueError("runtime turn send_feedback items must be SocialSendFeedback")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "message": self.message.to_public_dict(),
            "policy": self.policy.to_public_dict(),
            "context": dict(self.context) if self.context is not None else None,
            "decision": (
                self.decision.to_public_dict() if self.decision is not None else None
            ),
            "send_feedback": [feedback.to_public_dict() for feedback in self.send_feedback],
        }


@dataclass(frozen=True)
class SocialRuntime:
    adapter: Any
    character_card: CharacterCard
    operations: SocialOperationsController
    config: SocialRuntimeConfig
    lorebook: Lorebook | None = None
    sticker_library: StickerLibrary | None = None
    decision_loop: SocialDecisionLoop = SocialDecisionLoop()
    capability_bridge: SocialCapabilityBridge | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.character_card, CharacterCard):
            raise ValueError("character_card must be a CharacterCard")
        if not isinstance(self.operations, SocialOperationsController):
            raise ValueError("operations must be a SocialOperationsController")
        if not isinstance(self.config, SocialRuntimeConfig):
            raise ValueError("config must be a SocialRuntimeConfig")
        if self.lorebook is not None and not isinstance(self.lorebook, Lorebook):
            raise ValueError("lorebook must be a Lorebook")
        if self.sticker_library is not None and not isinstance(
            self.sticker_library,
            StickerLibrary,
        ):
            raise ValueError("sticker_library must be a StickerLibrary")
        if not isinstance(self.decision_loop, SocialDecisionLoop):
            raise ValueError("decision_loop must be a SocialDecisionLoop")
        if self.capability_bridge is not None and not isinstance(
            self.capability_bridge,
            SocialCapabilityBridge,
        ):
            raise ValueError("capability_bridge must be SocialCapabilityBridge")

    def process_next(
        self,
        *,
        dry_run: bool | None = None,
        wake_keywords: tuple[str, ...] | None = None,
        autonomy_score: float | None = None,
        sticker_emotion: str | None = None,
        sticker_scene_tags: tuple[str, ...] | None = None,
        allow_sticker_only: bool | None = None,
    ) -> SocialRuntimeTurn | None:
        message = self.adapter.receive_next()
        if message is None:
            return None
        if not isinstance(message, SocialMessage):
            raise ValueError("adapter.receive_next must return SocialMessage or None")
        group_id = _policy_group_id(message)
        policy = self.operations.can_process_group(group_id)
        if not policy.allowed:
            return SocialRuntimeTurn(message=message, policy=policy)

        effective_dry_run = self.config.dry_run if dry_run is None else dry_run
        if not isinstance(effective_dry_run, bool):
            raise ValueError("dry_run must be a bool")
        context = self._build_context(message=message, group_id=group_id)
        target = _target_for_message(message)
        decision = self._capability_decision(message=message, dry_run=effective_dry_run)
        if decision is None:
            decision = self.decision_loop.decide(
                SocialDecisionRequest(
                    context=context,
                    target=target,
                    bot_user_id=self.config.bot_user_id,
                    wake_keywords=(
                        self.config.wake_keywords if wake_keywords is None else wake_keywords
                    ),
                    autonomy_score=(
                        self.config.autonomy_score
                        if autonomy_score is None
                        else autonomy_score
                    ),
                    recent_send_feedback=self._recent_send_feedback(),
                    dry_run=effective_dry_run,
                    sticker_library=self.sticker_library,
                    sticker_emotion=(
                        self.config.sticker_emotion
                        if sticker_emotion is None
                        else sticker_emotion
                    ),
                    sticker_scene_tags=(
                        self.config.sticker_scene_tags
                        if sticker_scene_tags is None
                        else sticker_scene_tags
                    ),
                    allow_sticker_only=(
                        self.config.allow_sticker_only
                        if allow_sticker_only is None
                        else allow_sticker_only
                    ),
                )
            )
        self.operations.audit_log.append("decision", group_id, decision.to_public_dict())
        feedback = self._send_selected(decision=decision, group_id=group_id, target=target)
        return SocialRuntimeTurn(
            message=message,
            policy=policy,
            context=context,
            decision=decision,
            send_feedback=feedback,
        )

    def health(self) -> dict[str, Any]:
        connection_state = self.adapter.connection_state()
        state = (
            connection_state.to_public_dict()
            if hasattr(connection_state, "to_public_dict")
            else dict(connection_state)
        )
        return self.operations.health_check(adapter_states=(state,))

    def _build_context(self, *, message: SocialMessage, group_id: str) -> dict[str, Any]:
        return SocialContextBuilder(
            character_card=self.character_card,
            lorebook=self.lorebook,
        ).build(
            group_id=group_id,
            message=message,
            recent_messages=_recent_message_previews(self._recent_send_feedback()),
        )

    def _send_selected(
        self,
        *,
        decision: SocialDecisionTurn,
        group_id: str,
        target: SocialTarget,
    ) -> tuple[SocialSendFeedback, ...]:
        feedback_items: list[SocialSendFeedback] = []
        if decision.dry_run:
            return ()
        for candidate in decision.selected:
            if candidate.is_send_action and candidate.reply_action is not None:
                feedback = self.adapter.send_action(candidate.reply_action)
                if not isinstance(feedback, SocialSendFeedback):
                    raise ValueError("adapter.send_action must return SocialSendFeedback")
                self.operations.record_send(group_id, feedback)
                feedback_items.append(feedback)
            elif candidate.kind == "call_capability" and self.capability_bridge is not None:
                report = self.capability_bridge.run(
                    candidate,
                    character_card=self.character_card.for_group(group_id),
                    group_id=group_id,
                    inputs=dict(candidate.metadata.get("capability_inputs", {})),
                    operator_approved=bool(candidate.metadata.get("operator_approved", False)),
                )
                self.operations.record_capability(group_id, report)
                feedback = self.adapter.send_action(
                    SocialReplyAction(
                        action_id="capability_report",
                        target=target,
                        parts=(
                            SocialMessagePart(
                                kind="text",
                                text=_capability_report_text(report.to_public_dict()),
                            ),
                        ),
                    )
                )
                if not isinstance(feedback, SocialSendFeedback):
                    raise ValueError("adapter.send_action must return SocialSendFeedback")
                self.operations.record_send(group_id, feedback)
                feedback_items.append(feedback)
        return tuple(feedback_items)

    def _capability_decision(
        self,
        *,
        message: SocialMessage,
        dry_run: bool,
    ) -> SocialDecisionTurn | None:
        capability = self.config.capability
        if not capability.enabled or self.capability_bridge is None:
            return None
        text = message.text.strip()
        if not text:
            return None
        if not any(keyword in text for keyword in capability.trigger_keywords):
            return None
        inputs = dict(capability.input_defaults)
        inputs[capability.query_input_key] = text
        operator_approved = self.operations.is_operator(message.sender.user_id) and any(
            keyword in text for keyword in capability.approval_keywords
        )
        candidate = SocialActionCandidate(
            candidate_id=f"call_{capability.capability_id}",
            agent_id=self.character_card.identity.name,
            kind="call_capability",
            reason="social_capability_intent",
            confidence=0.8,
            capability_id=capability.capability_id,
            metadata={
                "capability_inputs": inputs,
                "operator_approved": operator_approved,
                "trigger_keywords": list(capability.trigger_keywords),
            },
        )
        if dry_run:
            return SocialDecisionTurn(
                proposed=(candidate,),
                selected=(),
                rejected={candidate.candidate_id: "dry_run:not executed"},
                dry_run=True,
            )
        return SocialDecisionTurn(
            proposed=(candidate,),
            selected=(candidate,),
            rejected={},
            dry_run=False,
        )

    def _recent_send_feedback(self) -> tuple[SocialSendFeedback, ...]:
        feedback: list[SocialSendFeedback] = []
        for entry in self.operations.audit_log.entries:
            if entry.kind != "send":
                continue
            feedback.append(_feedback_from_payload(entry.payload))
        return tuple(feedback)


def _policy_group_id(message: SocialMessage) -> str:
    if message.chat_type == "group" and message.group_id is not None:
        return message.group_id
    return message.sender.user_id


def _target_for_message(message: SocialMessage) -> SocialTarget:
    if message.chat_type == "group":
        return SocialTarget(platform=message.platform, chat_type="group", group_id=message.group_id)
    return SocialTarget(
        platform=message.platform,
        chat_type="private",
        user_id=message.sender.user_id,
    )


def _recent_message_previews(
    feedback_items: tuple[SocialSendFeedback, ...],
) -> tuple[dict[str, Any], ...]:
    previews: list[dict[str, Any]] = []
    for feedback in feedback_items:
        previews.extend(dict(item) for item in feedback.recent_messages_after_send)
    return tuple(previews)


def _feedback_from_payload(payload: dict[str, Any]) -> SocialSendFeedback:
    chunks = tuple()
    return SocialSendFeedback(
        status=str(payload.get("status", "failed")),
        sent_message_ids=tuple(str(item) for item in payload.get("sent_message_ids", [])),
        chunks=chunks,
        recent_messages_after_send=tuple(
            dict(item) for item in payload.get("recent_messages_after_send", [])
        ),
        platform_error=payload.get("platform_error"),
    )


def _capability_report_text(report: dict[str, Any]) -> str:
    status = str(report.get("status", ""))
    capability_id = str(report.get("capability_id", "capability"))
    content = str(report.get("content", "")).strip()
    if status == "requires_operator_approval":
        return f"需要管理员批准后才能调用 {capability_id}。"
    if content:
        return content
    if status == "missing_inputs":
        return f"{capability_id} 缺少必要输入，暂时不能执行。"
    if status == "blocked":
        return f"{capability_id} 当前被策略阻止，暂时不能执行。"
    if status == "failed":
        return f"{capability_id} 执行失败。"
    return f"{capability_id} 返回状态：{status or 'unknown'}"
