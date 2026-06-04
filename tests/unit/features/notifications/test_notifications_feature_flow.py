from __future__ import annotations

from typing import Any

import pytest

from isotope.features.notifications.flow import NotificationFlow


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "text",
}


def _assert_public_metadata(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_public_metadata(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_metadata(nested)


def test_notification_flow_creates_filters_and_marks_read(tmp_path):
    flow = NotificationFlow.in_process(tmp_path)

    decision = flow.create_notification(
        notification_type="approval",
        title="Worker needs approval",
        source_ref={"ref_type": "supervisor_run", "run_id": "run_123"},
    )
    status = flow.create_notification(
        notification_type="worker_status",
        title="Worker finished stage",
    )

    assert decision.notification_id.startswith("notif_")
    assert decision.notification_type == "approval"
    assert decision.title == "Worker needs approval"
    assert decision.unread is True
    assert decision.read_at is None
    assert decision.source_ref == {"ref_type": "supervisor_run", "run_id": "run_123"}
    assert flow.list_notifications() == [decision, status]
    assert flow.list_notifications(unread=True) == [decision, status]
    assert flow.list_notifications(notification_type="approval") == [decision]

    marked = flow.mark_read(decision.notification_id)

    assert marked.notification_id == decision.notification_id
    assert marked.unread is False
    assert marked.read_at is not None
    assert flow.list_notifications(unread=True) == [status]
    assert flow.list_notifications(unread=False) == [marked]
    _assert_public_metadata({"notifications": [item.to_dict() for item in flow.list_notifications()]})


def test_notification_flow_reloads_public_metadata_index(tmp_path):
    flow = NotificationFlow.in_process(tmp_path)
    created = flow.create_notification(
        notification_type="worker_status",
        title="Worker finished stage",
    )
    marked = flow.mark_read(created.notification_id)

    reloaded = NotificationFlow.in_process(tmp_path)

    assert reloaded.list_notifications() == [marked]
    assert reloaded.list_notifications(unread=False) == [marked]
    assert reloaded.get_notification(created.notification_id) == marked
    _assert_public_metadata(reloaded.get_notification(created.notification_id).to_dict())


def test_notification_flow_rejects_sensitive_source_ref_fields(tmp_path):
    flow = NotificationFlow.in_process(tmp_path)

    with pytest.raises(ValueError, match="source_ref must stay public"):
        flow.create_notification(
            notification_type="approval",
            title="Worker needs approval",
            source_ref={"ref_type": "artifact", "raw_content": "secret transcript"},
        )


def test_notification_flow_source_ref_is_deep_copied_and_revalidated(tmp_path):
    flow = NotificationFlow.in_process(tmp_path)
    source_ref = {
        "ref_type": "supervisor_worker",
        "worker": {"name": "worker-a"},
    }

    created = flow.create_notification(
        notification_type="worker_status",
        title="Worker finished stage",
        source_ref=source_ref,
    )

    source_ref["worker"]["raw_content"] = "secret transcript"
    created.source_ref["worker"]["text"] = "mutated returned object"
    marked = flow.mark_read(created.notification_id)
    reloaded = NotificationFlow.in_process(tmp_path).get_notification(
        created.notification_id
    )

    assert marked.source_ref == {
        "ref_type": "supervisor_worker",
        "worker": {"name": "worker-a"},
    }
    assert reloaded.source_ref == marked.source_ref
    _assert_public_metadata(reloaded.to_dict())


def test_notification_flow_merges_stale_writers(tmp_path):
    first = NotificationFlow.in_process(tmp_path)
    second = NotificationFlow.in_process(tmp_path)

    first_created = first.create_notification(
        notification_type="approval",
        title="First notification",
    )
    second_created = second.create_notification(
        notification_type="worker_status",
        title="Second notification",
    )

    reloaded = NotificationFlow.in_process(tmp_path)

    assert reloaded.list_notifications() == [first_created, second_created]


def test_notification_flow_atomic_save_does_not_leave_temp_file(tmp_path, monkeypatch):
    class FixedUuid:
        hex = "fixedtmp"

    monkeypatch.setattr(
        "isotope.features.notifications.flow.uuid4",
        lambda: FixedUuid(),
    )
    flow = NotificationFlow.in_process(tmp_path)

    created = flow.create_notification(
        notification_type="worker_status",
        title="Worker finished stage",
    )

    index_path = tmp_path / "notifications" / "index.json"
    temp_path = tmp_path / "notifications" / ".index.json.fixedtmp.tmp"
    assert index_path.is_file()
    assert not temp_path.exists()
    assert NotificationFlow.in_process(tmp_path).get_notification(
        created.notification_id
    ) == created
