from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.planner.decision_requests import record_decision_request
from isotope.features.supervisor.planner.goal_queue import (
    record_supervisor_goal,
    record_supervisor_goal_status,
)
from isotope.features.supervisor.planner.decision_requests import record_decision_answer


ALLOWED_SOURCE_REF_KEYS = {
    "ref_type",
    "goal_id",
    "request_id",
    "record_id",
    "group",
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
    "answer",
}


def _assert_public_metadata_source_ref(value: dict[str, Any]) -> None:
    assert set(value) <= ALLOWED_SOURCE_REF_KEYS
    assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)


@pytest.mark.parametrize("status", ["done", "blocked", "needs_user"])
def test_goal_status_writeback_creates_public_metadata_notification(tmp_path, status):
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
    _assert_public_metadata_source_ref(summary.source_ref)


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


def test_decision_request_write_creates_public_metadata_notification(tmp_path):
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
    _assert_public_metadata_source_ref(summary.source_ref)


def test_duplicate_decision_request_reuses_active_request_without_notification(tmp_path):
    action = {
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
    }

    first = record_decision_request(codex_home=tmp_path, action=action)
    second = record_decision_request(codex_home=tmp_path, action={**action, "reason": "Retry"})

    assert second.request_id == first.request_id
    ledger_path = tmp_path / "supervisor" / "decision_requests.jsonl"
    records = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["decision_request"]
    assert len(NotificationFlow.in_process(tmp_path).list_notifications()) == 1


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


def test_goal_status_webhook_posts_public_metadata_signed_payload(tmp_path, monkeypatch):
    requests: list[dict[str, Any]] = []

    def stub_urlopen(request, timeout):
        requests.append(
            {
                "url": request.full_url,
                "body": json.loads(request.data.decode("utf-8")),
                "headers": dict(request.header_items()),
                "timeout": timeout,
            }
        )

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"ok"

        return Response()

    monkeypatch.setattr(
        "isotope.features.supervisor.notifications.notifications.urllib.request.urlopen",
        stub_urlopen,
    )
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="Ship supervisor notifications",
        target_name="worker-a",
    )

    event = record_supervisor_goal_status(
        codex_home=tmp_path,
        goal_id=goal.goal_id,
        status="done",
        target_name="worker-a",
        session_id="session-secret",
        summary="contains task details",
        next_step="contains next step",
        webhook_url="https://example.test/supervisor",
        webhook_secret="shared-secret",
    )

    assert event is not None
    assert len(requests) == 1
    assert requests[0]["url"] == "https://example.test/supervisor"
    body = requests[0]["body"]
    assert body["event_type"] == "supervisor_goal_status"
    assert body["source_ref"] == {
        "ref_type": "supervisor_goal_status",
        "goal_id": goal.goal_id,
        "status": "done",
    }
    assert requests[0]["headers"]["X-isotope-event"] == "supervisor_goal_status"
    assert requests[0]["headers"]["X-isotope-signature"].startswith("sha256=")
    _assert_public_metadata_source_ref(body["source_ref"])
    assert "shared-secret" not in json.dumps(requests[0], ensure_ascii=False)


def test_decision_answer_webhook_posts_without_answer_text(tmp_path, monkeypatch):
    payloads: list[dict[str, Any]] = []

    def stub_urlopen(request, timeout):
        payloads.append(json.loads(request.data.decode("utf-8")))

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"ok"

        return Response()

    monkeypatch.setattr(
        "isotope.features.supervisor.notifications.notifications.urllib.request.urlopen",
        stub_urlopen,
    )
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

    answer = record_decision_answer(
        codex_home=tmp_path,
        request_id=request.request_id,
        answer="Use the private branch details.",
        webhook_url="https://example.test/supervisor",
    )

    assert answer["request_id"] == request.request_id
    assert payloads == [
        {
            "event_type": "supervisor_decision_answer",
            "source_ref": {
                "ref_type": "supervisor_decision_answer",
                "goal_id": "goal-123",
                "request_id": request.request_id,
            },
        }
    ]
    assert "Use the private branch details" not in json.dumps(payloads, ensure_ascii=False)


def test_webhook_failure_warns_without_breaking_goal_ledger(tmp_path, monkeypatch, caplog):
    def stub_urlopen(_request, _timeout):
        raise OSError("network down")

    monkeypatch.setattr(
        "isotope.features.supervisor.notifications.notifications.urllib.request.urlopen",
        stub_urlopen,
    )
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="Ship supervisor notifications",
        target_name="worker-a",
    )

    with caplog.at_level(logging.WARNING):
        event = record_supervisor_goal_status(
            codex_home=tmp_path,
            goal_id=goal.goal_id,
            status="blocked",
            webhook_url="https://example.test/supervisor",
        )

    assert event is not None
    assert event["status"] == "blocked"
    assert "supervisor webhook POST failed" in caplog.text
