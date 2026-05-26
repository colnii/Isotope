from __future__ import annotations

from isotope.features.supervisor.commands.dashboard import (
    dashboard_state_snapshot_from_items,
)


def test_dashboard_state_snapshot_from_items_counts_summary_fields():
    active_goals = [
        {"goal_id": "goal-done", "last_status": "done"},
        {"goal_id": "goal-blocked", "last_status": "blocked"},
        {"goal_id": "goal-needs-user", "last_status": "needs_user"},
        {"goal_id": "goal-working", "last_status": "working"},
        {"goal_id": "goal-missing-status"},
    ]
    decision_requests = [{"decision_id": "decision-1"}, {"decision_id": "decision-2"}]
    notifications = [
        {"notification_id": "notice-1", "unread": True},
        {"notification_id": "notice-2", "unread": False},
        {"notification_id": "notice-3"},
        {"notification_id": "notice-4", "unread": True},
    ]

    snapshot = dashboard_state_snapshot_from_items(
        active_goals=active_goals,
        decision_requests=decision_requests,
        notifications=notifications,
    )

    assert snapshot["status"] == "ok"
    assert snapshot["kind"] == "supervisor_state_snapshot"
    assert snapshot["schema_version"] == 1
    assert snapshot["summary"] == {
        "active_goals": 5,
        "goals_done": 1,
        "goals_blocked": 1,
        "goals_needs_user": 1,
        "active_decisions": 2,
        "failed_lanes": 0,
        "worker_events": 0,
        "notifications": 4,
        "unread_notifications": 2,
    }
    assert snapshot["notifications"] == {
        "total": 4,
        "unread": 2,
        "recent": notifications,
    }


def test_dashboard_state_snapshot_from_items_copies_input_lists():
    active_goals = [{"goal_id": "goal-1"}]
    decision_requests = [{"decision_id": "decision-1"}]
    notifications = [{"notification_id": "notice-1"}]

    snapshot = dashboard_state_snapshot_from_items(
        active_goals=active_goals,
        decision_requests=decision_requests,
        notifications=notifications,
    )

    active_goals.append({"goal_id": "goal-late"})
    decision_requests.append({"decision_id": "decision-late"})
    notifications.append({"notification_id": "notice-late"})

    assert snapshot["active_goals"] == [{"goal_id": "goal-1"}]
    assert snapshot["active_decisions"] == [{"decision_id": "decision-1"}]
    assert snapshot["notifications"]["recent"] == [{"notification_id": "notice-1"}]
