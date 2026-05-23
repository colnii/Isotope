from __future__ import annotations

from datetime import UTC, datetime

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.decision_requests import record_decision_request
from isotope.features.supervisor.lane_state import record_lane_failure
from isotope.features.supervisor.state.projection import build_supervisor_state_snapshot
from isotope.memory.worker_event_channel import publish_worker_event


def test_supervisor_state_snapshot_empty_root_is_read_only(tmp_path):
    snapshot = build_supervisor_state_snapshot(codex_home=tmp_path)

    assert snapshot == {
        "status": "ok",
        "codex_home": str(tmp_path),
        "summary": {
            "active_decisions": 0,
            "failed_lanes": 0,
            "worker_events": 0,
            "notifications": 0,
            "unread_notifications": 0,
        },
        "active_decisions": [],
        "failed_lanes": [],
        "recent_worker_events": [],
        "notifications": {"total": 0, "unread": 0, "recent": []},
    }
    assert list(tmp_path.rglob("*")) == []


def test_supervisor_state_snapshot_projects_existing_low_sensitive_state(tmp_path):
    record_decision_request(
        codex_home=tmp_path,
        action={
            "session_id": "session-1",
            "target_name": "worker-a",
            "question": "是否继续合并？",
            "reason": "worker 需要用户确认",
            "context_status": "conflict",
            "gate": {"context_status": "conflict"},
        },
        now=lambda: datetime(2026, 5, 24, 1, 2, tzinfo=UTC),
    )
    record_lane_failure(
        codex_home=tmp_path,
        name="worker-a",
        tmux_session=None,
        reason="exit_code",
        exit_code=1,
        stderr_summary="pytest failed",
        record_id="managed-1",
        now=datetime(2026, 5, 24, 1, 3, tzinfo=UTC),
    )
    publish_worker_event(
        root=tmp_path,
        from_worker="worker-a",
        to_worker="worker-b",
        event_type="handoff",
        message="Ready for review.",
        payload={"branch": "feature/a"},
    )
    NotificationFlow(
        tmp_path,
        clock=lambda: datetime(2026, 5, 24, 1, 4, tzinfo=UTC),
        id_factory=lambda: "notif_manual",
    ).create_notification(
        notification_type="manual",
        title="人工提醒",
        source_ref={"worker": "worker-a"},
    )

    snapshot = build_supervisor_state_snapshot(codex_home=tmp_path)

    assert snapshot["summary"] == {
        "active_decisions": 1,
        "failed_lanes": 1,
        "worker_events": 1,
        "notifications": 2,
        "unread_notifications": 2,
    }
    assert snapshot["active_decisions"] == [
        {
            "request_id": snapshot["active_decisions"][0]["request_id"],
            "session_id": "session-1",
            "target_name": "worker-a",
            "goal_id": None,
            "question": "是否继续合并？",
            "reason": "worker 需要用户确认",
            "context_status": "conflict",
            "created_at": "2026-05-24T01:02:00+00:00",
        }
    ]
    assert snapshot["failed_lanes"] == [
        {
            "name": "worker-a",
            "last_failure_reason": "exit_code",
            "last_failure_exit_code": 1,
            "last_failure_stderr_summary": "pytest failed",
            "last_failure_record_id": "managed-1",
            "last_failed_at": "2026-05-24T01:03:00+00:00",
            "failure_count": 1,
            "worker_retry_count": 0,
        }
    ]
    assert snapshot["recent_worker_events"][0]["from_worker"] == "worker-a"
    assert snapshot["recent_worker_events"][0]["to_worker"] == "worker-b"
    assert snapshot["recent_worker_events"][0]["event_type"] == "handoff"
    assert snapshot["recent_worker_events"][0]["payload"] == {"branch": "feature/a"}
    assert snapshot["notifications"]["total"] == 2
    assert snapshot["notifications"]["unread"] == 2
    assert [item["type"] for item in snapshot["notifications"]["recent"]] == [
        "supervisor_decision_request",
        "manual",
    ]
    assert "content" not in repr(snapshot)
