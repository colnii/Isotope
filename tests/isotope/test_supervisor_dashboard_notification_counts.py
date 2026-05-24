from __future__ import annotations

from isotope.features.supervisor.commands.dashboard import dashboard_notification_counts


def test_dashboard_notification_counts_prefers_snapshot_totals():
    notifications = [{"unread": False}]
    state_snapshot = {"notifications": {"total": 22, "unread": 7}}

    assert dashboard_notification_counts(
        notifications,
        state_snapshot=state_snapshot,
    ) == {"total": 22, "unread": 7}


def test_dashboard_notification_counts_falls_back_when_snapshot_counts_incomplete():
    notifications = [
        {"unread": True},
        {"unread": False},
        {"title": "missing unread flag"},
        {"unread": True},
    ]
    state_snapshot = {"notifications": {"total": 99}}

    assert dashboard_notification_counts(
        notifications,
        state_snapshot=state_snapshot,
    ) == {"total": 4, "unread": 2}


def test_dashboard_notification_counts_falls_back_without_snapshot_notifications():
    notifications = [{"unread": True}, {"unread": False}]

    assert dashboard_notification_counts(
        notifications,
        state_snapshot={"status": "ok"},
    ) == {"total": 2, "unread": 1}


def test_dashboard_notification_counts_falls_back_without_snapshot():
    notifications = [{"unread": True}]

    assert dashboard_notification_counts(
        notifications,
        state_snapshot=None,
    ) == {"total": 1, "unread": 1}
