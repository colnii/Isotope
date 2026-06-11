from __future__ import annotations

from isotope.features.supervisor.agent_group.codex_chat.contracts import (
    ConnectedCodexMember,
    CoordinatorDecision,
)
from isotope.features.supervisor.agent_group.codex_chat.runtime import (
    CodexGroupChatRuntime,
)


def test_confirm_policy_creates_draft_without_sending(tmp_path):
    runtime = CodexGroupChatRuntime(tmp_path)
    runtime.store.save_member(member(send_policy="confirm", status="active"))

    result = runtime.apply_decision(
        CoordinatorDecision(
            decision_id="decision_1",
            group_id="group_rna",
            action="send_member",
            target_member_id="member_research",
            content="Please inspect the new RNA data schema.",
            reason="Research update is useful.",
            created_at="2026-06-12T00:00:00Z",
        )
    )

    assert result["status"] == "draft"
    assert result["send_policy"] == "confirm"
    assert result["sent"] is False
    assert result["draft"]["target_member_id"] == "member_research"


def test_draft_only_policy_never_sends(tmp_path):
    runtime = CodexGroupChatRuntime(tmp_path)
    runtime.store.save_member(member(send_policy="draft_only", status="active"))

    result = runtime.apply_decision(
        CoordinatorDecision(
            decision_id="decision_1",
            group_id="group_rna",
            action="send_member",
            target_member_id="member_research",
            content="Draft only message.",
            reason="User wants manual copy.",
            created_at="2026-06-12T00:00:00Z",
        )
    )

    assert result["status"] == "draft"
    assert result["send_policy"] == "draft_only"
    assert result["sent"] is False


def test_auto_policy_uses_injected_sender(tmp_path):
    sent: list[dict[str, str]] = []
    runtime = CodexGroupChatRuntime(
        tmp_path,
        sender=lambda member_id, text: sent.append(
            {"member_id": member_id, "text": text}
        ),
    )
    runtime.store.save_member(member(send_policy="auto", status="active"))

    result = runtime.apply_decision(
        CoordinatorDecision(
            decision_id="decision_1",
            group_id="group_rna",
            action="send_member",
            target_member_id="member_research",
            content="Auto message.",
            reason="Safe automatic update.",
            created_at="2026-06-12T00:00:00Z",
        )
    )

    assert result["status"] == "sent"
    assert result["sent"] is True
    assert sent == [{"member_id": "member_research", "text": "Auto message."}]


def test_terminated_member_blocks_auto_send(tmp_path):
    sent: list[dict[str, str]] = []
    runtime = CodexGroupChatRuntime(
        tmp_path,
        sender=lambda member_id, text: sent.append(
            {"member_id": member_id, "text": text}
        ),
    )
    runtime.store.save_member(member(send_policy="auto", status="terminated"))

    result = runtime.apply_decision(
        CoordinatorDecision(
            decision_id="decision_1",
            group_id="group_rna",
            action="send_member",
            target_member_id="member_research",
            content="Should not send.",
            reason="Terminated member must be isolated.",
            created_at="2026-06-12T00:00:00Z",
        )
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "target_member_terminated"
    assert sent == []


def test_member_stop_marks_member_terminated(tmp_path):
    runtime = CodexGroupChatRuntime(tmp_path)
    runtime.store.save_member(member(send_policy="auto", status="active"))

    result = runtime.terminate_member(
        group_id="group_rna",
        member_id="member_research",
        reason="User pressed member Stop.",
    )

    assert result["status"] == "terminated"
    assert result["member"]["status"] == "terminated"
    assert runtime.store.list_members("group_rna")[0].status == "terminated"


def member(*, send_policy: str, status: str) -> ConnectedCodexMember:
    return ConnectedCodexMember(
        member_id="member_research",
        group_id="group_rna",
        display_name="Research Codex",
        member_kind="codex_session",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy=send_policy,
        status=status,
        resume_session_id="session_research",
        source_path="/tmp/research.jsonl",
        managed_record_id=None,
        transcript_policy={},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
