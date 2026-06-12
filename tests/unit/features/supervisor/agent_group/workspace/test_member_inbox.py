from __future__ import annotations

from isotope.features.supervisor.agent_group.workspace.coordination.inbox import (
    MemberInboxItem,
    MemberInboxStore,
)


def test_member_inbox_enqueue_is_idempotent_by_source_and_target(tmp_path):
    store = MemberInboxStore(tmp_path / ".codex")

    first = store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_user_1",
        from_actor="user",
        summary="请同步当前进展。",
        payload={"runtime_group_id": "group_workspace_1"},
    )
    repeated = store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_user_1",
        from_actor="user",
        summary="请同步当前进展。",
        payload={"runtime_group_id": "group_workspace_1"},
    )

    assert repeated == first
    assert store.list_pending("workspace_1", "channel_1", "member_training") == [
        first
    ]


def test_member_inbox_marks_items_dispatched(tmp_path):
    store = MemberInboxStore(tmp_path / ".codex")
    item = store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_user_1",
        from_actor="user",
        summary="请同步当前进展。",
        payload={},
    )

    dispatched = store.mark_dispatched(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        inbox_item_ids=(item.inbox_item_id,),
        managed_record_id="managed-training",
    )

    assert dispatched[0].status == "dispatched"
    assert dispatched[0].managed_record_id == "managed-training"
    assert store.list_pending("workspace_1", "channel_1", "member_training") == []


def test_member_inbox_pending_counts_by_member(tmp_path):
    store = MemberInboxStore(tmp_path / ".codex")
    store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_1",
        from_actor="user",
        summary="one",
        payload={},
    )
    store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_research",
        source_message_id="msg_2",
        from_actor="member_training",
        summary="two",
        payload={},
    )

    assert store.pending_counts_by_member("workspace_1", "channel_1") == {
        "member_training": 1,
        "member_research": 1,
    }


def test_member_inbox_public_dict_has_no_raw_payload_fields() -> None:
    item = MemberInboxItem(
        inbox_item_id="inbox_1",
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_1",
        from_actor="user",
        summary="hello",
        status="pending",
        payload={"raw_prompt": "should stay private", "safe": "visible"},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
        managed_record_id=None,
    )

    assert item.to_public_dict() == {
        "inbox_item_id": "inbox_1",
        "workspace_id": "workspace_1",
        "channel_id": "channel_1",
        "target_member_id": "member_training",
        "source_message_id": "msg_1",
        "from_actor": "user",
        "summary": "hello",
        "status": "pending",
        "payload": {"safe": "visible"},
        "created_at": "2026-06-12T00:00:00Z",
        "updated_at": "2026-06-12T00:00:00Z",
        "managed_record_id": None,
    }
