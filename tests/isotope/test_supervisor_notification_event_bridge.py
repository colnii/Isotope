from __future__ import annotations

import json
from typing import Any

import pytest

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.decision_requests import record_decision_request
from isotope.features.supervisor.goal_queue import (
    record_supervisor_goal,
    record_supervisor_goal_status,
)


ALLOWED_SOURCE_REF_KEYS = {
    "ref_type",
    "goal_id",
    "request_id",
    "status",
}
FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "text",
    "session_id",
    "summary",
    "next",
    "question",
    "reason",
    "gate",
}


def _assert_low_sensitive_source_ref(value: dict[str, Any]) -> None:
    assert set(value) <= ALLOWED_SOURCE_REF_KEYS
    assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)


@pytest.mark.parametrize("status", ["done", "blocked", "needs_user"])
def test_goal_status_writeback_creates_low_sensitive_notification(tmp_path, status):
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="Ship supervisor notifications",
        target_name="worker-a",
    )

    event = record_supervisor_goal_status(
        codex_home=tmp_path,
        goal_id=goal.goal_id,
        status=status,
        target_name="worker-a",
        session_id="session-secret",
        summary="contains task details",
        next_step="contains next step",
    )

    notifications = NotificationFlow.in_process(tmp_path).list_notifications()
    assert event is not None
    assert len(notifications) == 1
    summary = notifications[0]
    assert summary.notification_type == "supervisor_goal_status"
    assert summary.title == f"Supervisor goal status: {status}"
    assert summary.source_ref == {
        "ref_type": "supervisor_goal_status",
        "goal_id": goal.goal_id,
        "status": status,
    }
    _assert_low_sensitive_source_ref(summary.source_ref)


def test_duplicate_goal_status_writeback_does_not_duplicate_notification(tmp_path):
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="Ship supervisor notifications",
        target_name="worker-a",
    )
    kwargs = {
        "codex_home": tmp_path,
        "goal_id": goal.goal_id,
        "status": "done",
        "target_name": "worker-a",
    }

    assert record_supervisor_goal_status(**kwargs) is not None
    assert record_supervisor_goal_status(**kwargs) is None

    assert len(NotificationFlow.in_process(tmp_path).list_notifications()) == 1


def test_decision_request_write_creates_low_sensitive_notification(tmp_path):
    request = record_decision_request(
        codex_home=tmp_path,
        action={
            "session_id": "session-secret",
            "target_name": "worker-a",
            "goal_id": "goal-123",
            "question": "Should we continue?",
            "reason": "Need a human decision",
            "context_status": "current",
            "gate": {
                "codex_requested_decision": True,
                "instructions_exhausted": True,
                "context_status": "current",
            },
        },
    )

    notifications = NotificationFlow.in_process(tmp_path).list_notifications()
    assert len(notifications) == 1
    summary = notifications[0]
    assert summary.notification_type == "supervisor_decision_request"
    assert summary.title == "Supervisor decision request"
    assert summary.source_ref == {
        "ref_type": "supervisor_decision_request",
        "goal_id": "goal-123",
        "request_id": request.request_id,
    }
    _assert_low_sensitive_source_ref(summary.source_ref)


def test_goal_status_notification_failure_does_not_break_goal_ledger(tmp_path):
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="Ship supervisor notifications",
        target_name="worker-a",
    )
    notification_dir = tmp_path / "notifications"
    notification_dir.mkdir()
    (notification_dir / "index.json").write_text("{bad json", encoding="utf-8")

    event = record_supervisor_goal_status(
        codex_home=tmp_path,
        goal_id=goal.goal_id,
        status="blocked",
        target_name="worker-a",
    )

    assert event is not None
    assert event["goal_id"] == goal.goal_id
    assert event["status"] == "blocked"


def test_decision_notification_failure_does_not_break_decision_ledger(tmp_path):
    notification_dir = tmp_path / "notifications"
    notification_dir.mkdir()
    (notification_dir / "index.json").write_text("{bad json", encoding="utf-8")

    request = record_decision_request(
        codex_home=tmp_path,
        action={
            "session_id": "session-secret",
            "target_name": "worker-a",
            "question": "Should we continue?",
            "reason": "Need a human decision",
            "context_status": "current",
            "gate": {
                "codex_requested_decision": True,
                "instructions_exhausted": True,
                "context_status": "current",
            },
        },
    )

    assert request.request_id.startswith("decision-")
    ledger_path = tmp_path / "supervisor" / "decision_requests.jsonl"
    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 1


def test_notification_bridge_does_not_leak_target_name_value(tmp_path):
    unsafe_target = "raw_content=secret prompt text"
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="Ship supervisor notifications",
        target_name=unsafe_target,
    )

    record_supervisor_goal_status(
        codex_home=tmp_path,
        goal_id=goal.goal_id,
        status="needs_user",
        target_name=unsafe_target,
    )
    record_decision_request(
        codex_home=tmp_path,
        action={
            "session_id": "session-secret",
            "target_name": unsafe_target,
            "goal_id": goal.goal_id,
            "question": "Should we continue?",
            "reason": "Need a human decision",
            "context_status": "current",
            "gate": {
                "codex_requested_decision": True,
                "instructions_exhausted": True,
                "context_status": "current",
            },
        },
    )

    payload = {
        "notifications": [
            item.to_dict()
            for item in NotificationFlow.in_process(tmp_path).list_notifications()
        ]
    }
    assert unsafe_target not in json.dumps(payload, ensure_ascii=False)
