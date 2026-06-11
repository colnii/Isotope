from __future__ import annotations

from isotope.features.supervisor.agent_group.codex_chat.contracts import (
    ConnectedCodexMember,
)
from isotope.features.supervisor.agent_group.codex_chat.store import (
    CodexGroupChatStore,
)


def test_store_saves_connected_member_and_private_chat(tmp_path):
    store = CodexGroupChatStore(tmp_path)
    member = ConnectedCodexMember(
        member_id="member_research",
        group_id="group_rna",
        display_name="Research Codex",
        member_kind="codex_session",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy="confirm",
        status="active",
        resume_session_id="session_research",
        source_path="/tmp/research.jsonl",
        managed_record_id=None,
        transcript_policy={"page_size": 200},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )

    store.save_member(member)
    store.append_private_chat(
        group_id="group_rna",
        role="assistant",
        content="Ask before sending this engineering update.",
    )

    assert (
        store.list_members("group_rna")[0].to_public_dict()["display_name"]
        == "Research Codex"
    )
    private_messages = store.list_private_chat("group_rna")
    assert private_messages[0].role == "assistant"
    assert private_messages[0].content == "Ask before sending this engineering update."


def test_store_updates_member_status_to_terminated(tmp_path):
    store = CodexGroupChatStore(tmp_path)
    store.save_member(
        ConnectedCodexMember(
            member_id="member_engineering",
            group_id="group_rna",
            display_name="Engineering Codex",
            member_kind="codex_session",
            role="Push engineering work.",
            goal="Keep Docker submission moving.",
            send_policy="auto",
            status="active",
            resume_session_id="session_engineering",
            source_path="/tmp/engineering.jsonl",
            managed_record_id="managed_engineering",
            transcript_policy={},
            created_at="2026-06-12T00:00:00Z",
            updated_at="2026-06-12T00:00:00Z",
        )
    )

    updated = store.update_member_status(
        group_id="group_rna",
        member_id="member_engineering",
        status="terminated",
    )

    assert updated.status == "terminated"
    assert store.list_members("group_rna")[0].status == "terminated"


def test_store_records_runtime_control_event(tmp_path):
    store = CodexGroupChatStore(tmp_path)

    control = store.record_control(
        group_id="group_rna",
        intent="terminate",
        target="member",
        target_member_id="member_research",
        reason="User pressed member Stop.",
    )

    assert control.intent == "terminate"
    events = store.list_control_events("group_rna")
    assert events[0]["payload"]["intent"] == "terminate"
    assert events[0]["payload"]["target_member_id"] == "member_research"
