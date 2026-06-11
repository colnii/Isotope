"""Runtime policy for Codex-backed Agent Group Chat."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .contracts import CoordinatorDecision
from .store import CodexGroupChatStore


SendMember = Callable[[str, str], None]


class CodexGroupChatRuntime:
    def __init__(
        self,
        root: Path | str,
        *,
        sender: SendMember | None = None,
    ) -> None:
        self.store = CodexGroupChatStore(root)
        self.sender = sender

    def apply_decision(self, decision: CoordinatorDecision) -> dict[str, object]:
        if decision.action == "reply_private":
            message = self.store.append_private_chat(
                group_id=decision.group_id,
                role="assistant",
                content=decision.content,
            )
            return {"status": "private_reply", "message": message.to_public_dict()}
        if decision.action in {"draft_member_send", "send_member"}:
            return self._apply_member_send(decision)
        return {
            "status": "recorded",
            "decision": decision.to_public_dict(),
        }

    def terminate_member(
        self,
        *,
        group_id: str,
        member_id: str,
        reason: str,
    ) -> dict[str, object]:
        control = self.store.record_control(
            group_id=group_id,
            intent="terminate",
            target="member",
            target_member_id=member_id,
            reason=reason,
        )
        member = self.store.update_member_status(
            group_id=group_id,
            member_id=member_id,
            status="terminated",
        )
        return {
            "status": "terminated",
            "control": control.to_public_dict(),
            "member": member.to_public_dict(),
        }

    def stop_current_run(self, *, group_id: str, reason: str) -> dict[str, object]:
        control = self.store.record_control(
            group_id=group_id,
            intent="terminate",
            target="current_run",
            target_member_id=None,
            reason=reason,
        )
        return {"status": "stop_requested", "control": control.to_public_dict()}

    def _apply_member_send(self, decision: CoordinatorDecision) -> dict[str, object]:
        if decision.target_member_id is None:
            raise ValueError("target_member_id is required")
        member = self._member(decision.group_id, decision.target_member_id)
        if member.status == "terminated":
            return {
                "status": "blocked",
                "sent": False,
                "reason": "target_member_terminated",
                "decision": decision.to_public_dict(),
            }
        if (
            decision.action == "draft_member_send"
            or member.send_policy in {"confirm", "draft_only"}
        ):
            return {
                "status": "draft",
                "sent": False,
                "send_policy": member.send_policy,
                "draft": decision.to_public_dict(),
            }
        if self.sender is None:
            return {
                "status": "draft",
                "sent": False,
                "send_policy": member.send_policy,
                "draft": decision.to_public_dict(),
                "reason": "sender_not_configured",
            }
        self.sender(member.member_id, decision.content)
        return {
            "status": "sent",
            "sent": True,
            "send_policy": member.send_policy,
            "decision": decision.to_public_dict(),
        }

    def _member(self, group_id: str, member_id: str):
        for member in self.store.list_members(group_id):
            if member.member_id == member_id:
                return member
        raise ValueError(f"connected member not found: {member_id}")
