"""Runtime for Supervisor internal Agent group chat."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from isotope.agents.loop.conversation import (
    AgentConversationMessage,
    arbitrate_agent_conversation_turn,
)
from isotope.features.supervisor.llm_action.llm_pool import (
    SummaryProvider,
    resolve_summary_provider_from_env,
)

from .contracts import AgentMember
from .store import AgentGroupStore


class AgentGroupProvider(Protocol):
    def candidate_for_member(
        self,
        *,
        member: AgentMember,
        group: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> AgentConversationMessage:
        ...


class StaticAgentGroupProvider:
    def __init__(self, candidates: dict[str, AgentConversationMessage]) -> None:
        self.candidates = dict(candidates)

    def candidate_for_member(
        self,
        *,
        member: AgentMember,
        group: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> AgentConversationMessage:
        candidate = self.candidates.get(member.name)
        if candidate is None:
            return AgentConversationMessage(
                message_id=f"candidate_{member.name}_silent",
                agent_id=member.member_id,
                intent="silent",
                summary="No update.",
                priority=0,
            )
        return replace(candidate, agent_id=member.member_id)


class SummaryAgentGroupProvider:
    def __init__(self, summary_provider: SummaryProvider) -> None:
        self.summary_provider = summary_provider

    def candidate_for_member(
        self,
        *,
        member: AgentMember,
        group: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> AgentConversationMessage:
        answer = self.summary_provider.summarize(
            [
                {
                    "role": "system",
                    "content": (
                        "You are one internal Isotope Agent group member. "
                        "Reply with one concise low-sensitive message. "
                        "Do not include raw prompts, raw tool output, or private data."
                    ),
                },
                {
                    "role": "user",
                    "content": _member_prompt(
                        member=member,
                        group=group,
                        messages=messages,
                    ),
                },
            ]
        ).strip()
        if not answer:
            answer = "No update."
        return AgentConversationMessage(
            message_id=f"candidate_{member.member_id}",
            agent_id=member.member_id,
            intent="respond" if answer != "No update." else "silent",
            summary=answer,
            priority=10,
        )


class AgentGroupRuntime:
    def __init__(
        self,
        root: str | Path,
        *,
        provider: AgentGroupProvider | None = None,
    ) -> None:
        self.store = AgentGroupStore(root)
        self.provider = provider

    def create_group(
        self,
        *,
        title: str,
        goal: str,
        member_specs: list[dict[str, Any]],
        initial_message: str,
    ) -> dict[str, Any]:
        pending_members = [
            AgentMember(
                member_id=f"member_{_safe_member_name(spec.get('name'))}",
                group_id="pending",
                name=_safe_member_name(spec.get("name")),
                role=_required_text(spec.get("role"), "role"),
                goal=_required_text(spec.get("goal"), "goal"),
                model_profile=str(spec.get("model_profile") or "default"),
                allowed_capabilities=tuple(spec.get("allowed_capabilities") or ()),
                status="active",
            )
            for spec in member_specs
        ]
        group = self.store.create_group(
            title=title,
            goal=goal,
            members=pending_members,
            initial_message=initial_message,
        )
        return self.list_group(group.group_id)

    def send_message(
        self,
        *,
        group_id: str,
        message: str,
        from_member: str = "supervisor",
        to_member: str | None = None,
        message_type: str = "task",
    ) -> dict[str, Any]:
        self.store.load_group(group_id)
        published = self.store.publish_message(
            group_id=group_id,
            turn_id="turn_manual",
            from_member=from_member,
            to_member=to_member,
            message_type=message_type,
            summary=message,
            payload={"source": "agent_group_send"},
        )
        return {"status": "ok", "message": published.to_public_dict()}

    def tick_group(
        self,
        group_id: str,
        *,
        max_visible_messages: int = 2,
    ) -> dict[str, Any]:
        group = self.store.load_group(group_id)
        members = [
            member
            for member in self.store.list_members(group_id)
            if member.status == "active"
        ]
        messages = [
            message.to_public_dict()
            for message in self.store.list_group_messages(group_id)
        ]
        provider = self._active_provider()
        candidates = [
            provider.candidate_for_member(
                member=member,
                group=group.to_public_dict(),
                messages=messages,
            )
            for member in members
        ]
        turn_id = f"turn_{len(self.store.list_turns(group_id)) + 1:04d}"
        arbitration = arbitrate_agent_conversation_turn(
            candidates,
            turn_id=turn_id,
            max_visible_messages=max_visible_messages,
        )
        selected_message_ids: list[str] = []
        for selected in arbitration["visible_messages"]:
            message_type = "interrupt" if selected["intent"] == "interrupt" else "reply"
            published = self.store.publish_message(
                group_id=group_id,
                turn_id=turn_id,
                from_member=str(selected["agent_id"]),
                to_member=None,
                message_type=message_type,
                summary=str(selected["summary"]),
                payload={
                    "candidate_message_id": selected["message_id"],
                    "intent": selected["intent"],
                    "priority": selected["priority"],
                },
            )
            selected_message_ids.append(published.message_id)
        supervisor_summary = _turn_summary(arbitration)
        turn = self.store.record_turn(
            group_id=group_id,
            input_message_ids=tuple(
                message["message_id"]
                for message in messages[-10:]
                if isinstance(message.get("message_id"), str)
            ),
            candidate_messages=tuple(candidate.message_id for candidate in candidates),
            selected_message_ids=tuple(selected_message_ids),
            queued_messages=tuple(arbitration["queued_messages"]),
            dropped_messages=tuple(arbitration["dropped_messages"]),
            status=str(arbitration["status"]),
            supervisor_summary=supervisor_summary,
        )
        return {"status": "ok", "turn": turn.to_public_dict()}

    def list_group(self, group_id: str) -> dict[str, Any]:
        group = self.store.load_group(group_id)
        return {
            "status": "ok",
            "group": group.to_public_dict(),
            "members": [
                member.to_public_dict()
                for member in self.store.list_members(group_id)
            ],
            "messages": [
                message.to_public_dict()
                for message in self.store.list_group_messages(group_id)
            ],
            "turns": [
                turn.to_public_dict() for turn in self.store.list_turns(group_id)
            ],
        }

    def list_groups(self) -> dict[str, Any]:
        groups = [group.to_public_dict() for group in self.store.list_groups()]
        return {
            "status": "ok",
            "summary": {"group_count": len(groups)},
            "groups": groups,
        }

    def _active_provider(self) -> AgentGroupProvider:
        if self.provider is not None:
            return self.provider
        return SummaryAgentGroupProvider(resolve_summary_provider_from_env())


def _member_prompt(
    *,
    member: AgentMember,
    group: dict[str, Any],
    messages: list[dict[str, Any]],
) -> str:
    recent = [
        {
            "from_member": message.get("from_member"),
            "to_member": message.get("to_member"),
            "message_type": message.get("message_type"),
            "summary": message.get("summary"),
        }
        for message in messages[-8:]
        if isinstance(message, dict)
    ]
    return (
        "Group goal: {group_goal}\n"
        "Your name: {name}\n"
        "Your role: {role}\n"
        "Your goal: {goal}\n"
        "Allowed capabilities: {capabilities}\n"
        "Recent public messages: {recent}\n"
        "Return the next useful group-chat message only."
    ).format(
        group_goal=group.get("goal", ""),
        name=member.name,
        role=member.role,
        goal=member.goal,
        capabilities=", ".join(member.allowed_capabilities) or "none",
        recent=recent,
    )


def _safe_member_name(value: object) -> str:
    text = _required_text(value, "name")
    safe = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_" for char in text
    )
    return safe.strip("_") or "agent"


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _turn_summary(arbitration: dict[str, Any]) -> str:
    visible = len(arbitration.get("visible_messages") or [])
    queued = len(arbitration.get("queued_messages") or [])
    dropped = len(arbitration.get("dropped_messages") or [])
    if visible == 0:
        return f"No visible agent replies; queued {queued}, dropped {dropped}."
    return f"Selected {visible} agent replies; queued {queued}, dropped {dropped}."
