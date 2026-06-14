"""Operator controls and inspection surfaces for social group bots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .arbiter import SocialArbiterResult
from .audit_log import SocialAuditLog
from .character_card import CharacterCard
from .config import SocialOperationsConfig
from .information_report import SocialInformationReport
from .lorebook import Lorebook
from .messages import _required_string_value
from .send_feedback import SocialSendFeedback
from .stickers import StickerLibrary


@dataclass(frozen=True)
class SocialPolicyDecision:
    allowed: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise ValueError("policy decision allowed must be a bool")
        _required_string_value(self.reason, "policy decision reason")

    def to_public_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason}


@dataclass
class SocialOperationsController:
    config: SocialOperationsConfig = SocialOperationsConfig()
    audit_log: SocialAuditLog = field(default_factory=SocialAuditLog)
    _paused_groups: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not isinstance(self.config, SocialOperationsConfig):
            raise ValueError("config must be a SocialOperationsConfig")
        if not isinstance(self.audit_log, SocialAuditLog):
            raise ValueError("audit_log must be a SocialAuditLog")
        self._paused_groups.update(self.config.group_policy.paused_groups)

    def can_process_group(self, group_id: str) -> SocialPolicyDecision:
        clean_group_id = _required_string_value(group_id, "group_id")
        policy = self.config.group_policy
        if clean_group_id in policy.blocked_groups:
            return SocialPolicyDecision(False, f"group_blocked:{clean_group_id}")
        if policy.allowed_groups and clean_group_id not in policy.allowed_groups:
            return SocialPolicyDecision(False, f"group_not_allowed:{clean_group_id}")
        if clean_group_id in self._paused_groups:
            return SocialPolicyDecision(False, f"group_paused:{clean_group_id}")
        return SocialPolicyDecision(True, "group_allowed")

    def pause_group(self, group_id: str, *, operator_user_id: str) -> dict[str, Any]:
        clean_group_id = _required_string_value(group_id, "group_id")
        operator = _required_string_value(operator_user_id, "operator_user_id")
        if not self._is_operator(operator):
            return {"ok": False, "reason": f"operator_required:{operator}"}
        self._paused_groups.add(clean_group_id)
        return {"ok": True, "reason": f"group_paused:{clean_group_id}"}

    def resume_group(self, group_id: str, *, operator_user_id: str) -> dict[str, Any]:
        clean_group_id = _required_string_value(group_id, "group_id")
        operator = _required_string_value(operator_user_id, "operator_user_id")
        if not self._is_operator(operator):
            return {"ok": False, "reason": f"operator_required:{operator}"}
        self._paused_groups.discard(clean_group_id)
        return {"ok": True, "reason": f"group_resumed:{clean_group_id}"}

    def is_operator(self, user_id: str) -> bool:
        return self._is_operator(_required_string_value(user_id, "operator_user_id"))

    def record_decision(
        self,
        group_id: str,
        decision: SocialArbiterResult,
    ) -> None:
        if not isinstance(decision, SocialArbiterResult):
            raise ValueError("decision must be a SocialArbiterResult")
        self.audit_log.append("decision", group_id, decision.to_public_dict())

    def record_send(self, group_id: str, feedback: SocialSendFeedback) -> None:
        if not isinstance(feedback, SocialSendFeedback):
            raise ValueError("feedback must be a SocialSendFeedback")
        self.audit_log.append("send", group_id, feedback.to_public_dict())

    def record_capability(
        self,
        group_id: str,
        report: SocialInformationReport,
    ) -> None:
        if not isinstance(report, SocialInformationReport):
            raise ValueError("report must be a SocialInformationReport")
        self.audit_log.append("capability", group_id, report.to_public_dict())

    def review_dry_run(self, decision: SocialArbiterResult) -> dict[str, Any]:
        if not isinstance(decision, SocialArbiterResult):
            raise ValueError("decision must be a SocialArbiterResult")
        return decision.to_public_dict()

    def health_check(
        self,
        *,
        adapter_states: tuple[dict[str, Any], ...] = (),
    ) -> dict[str, Any]:
        if not isinstance(adapter_states, tuple):
            raise ValueError("adapter_states must be a tuple")
        return {
            "status": "ok",
            "paused_groups": sorted(self._paused_groups),
            "audit_counts": self.audit_log.counts_by_kind(),
            "adapter_states": [dict(item) for item in adapter_states],
        }

    def inspect_role(self, card: CharacterCard) -> dict[str, Any]:
        if not isinstance(card, CharacterCard):
            raise ValueError("card must be a CharacterCard")
        return card.to_dict()

    def inspect_lorebook(self, lorebook: Lorebook) -> dict[str, Any]:
        if not isinstance(lorebook, Lorebook):
            raise ValueError("lorebook must be a Lorebook")
        return {"entries": [entry.to_public_dict() for entry in lorebook.entries]}

    def inspect_stickers(self, stickers: StickerLibrary) -> dict[str, Any]:
        if not isinstance(stickers, StickerLibrary):
            raise ValueError("stickers must be a StickerLibrary")
        return {"entries": [entry.to_public_dict() for entry in stickers.entries]}

    def _is_operator(self, user_id: str) -> bool:
        return user_id in self.config.group_policy.operator_user_ids
