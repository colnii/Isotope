from __future__ import annotations

from types import SimpleNamespace

from isotope.features.supervisor.commands.dashboard import dashboard_current_payload


class _FakeDashboardApi:
    def _cwd_is_existing_dir(self, value):
        return value in {"/repo/current-goal", "/repo/current-worker"}

    def _session_marks_terminal_done(self, session):
        return False

    def _is_completed_session(self, session):
        return False

    def _managed_tmux_command_suggestions(self, session):
        return []


def _managed_session(**overrides):
    values = {
        "session_id": "managed-session",
        "short_session_id": "managed-s",
        "display_title": "Managed worker",
        "thread_name": "Managed worker",
        "thread_id": "thread-managed",
        "initial_user_title": None,
        "agent_nickname": None,
        "agent_role": None,
        "managed_name": "current-worker",
        "git_branch": "feature/current-worker",
        "status": "working",
        "status_label": "working",
        "status_evidence": {"source": "supervisor_protocol"},
        "supervisor_status": "working",
        "supervisor_summary": "running tests",
        "supervisor_next": "report status",
        "managed": True,
        "managed_backend": "tmux",
        "managed_tmux_session": None,
        "managed_terminal_excerpt": "",
        "managed_terminal_ready": False,
        "managed_bell": False,
        "managed_bell_event_at": None,
        "managed_bell_hook_installed": False,
        "reason": "active",
        "age_seconds": 12,
        "cwd": "/repo/current-worker",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_dashboard_current_payload_marks_current_goals_and_workers():
    payload = dashboard_current_payload(
        [(_managed_session(), None, None)],
        active_goals=[
            {
                "goal_id": "goal-current",
                "target_name": "current-goal",
                "goal": "continue current goal",
                "cwd": "/repo/current-goal",
                "last_status": "working",
            },
            {
                "goal_id": "goal-done",
                "target_name": "done-goal",
                "goal": "already done",
                "cwd": "/repo/current-goal",
                "last_status": "done",
            },
            {
                "goal_id": "goal-missing",
                "target_name": "missing-goal",
                "goal": "missing worktree",
                "cwd": "/repo/missing",
                "last_status": "working",
            },
        ],
        api=_FakeDashboardApi(),
    )

    assert [goal["goal_id"] for goal in payload["active_goals"]] == ["goal-current"]
    assert payload["active_goals"][0]["cwd_exists"] is True
    assert payload["active_goals"][0]["current"] is True
    assert [worker["name"] for worker in payload["managed_workers"]] == [
        "current-worker"
    ]
    assert payload["managed_workers"][0]["cwd_exists"] is True
    assert payload["managed_workers"][0]["current"] is True
    assert payload["counts"] == {
        "active_goals": 1,
        "managed_workers": 1,
        "worker_reviews": 0,
        "automation_candidates": 0,
        "total": 2,
    }
    assert payload["target_names"] == ["current-goal", "current-worker"]


def test_dashboard_current_payload_can_read_active_goals_from_state_snapshot():
    payload = dashboard_current_payload(
        [],
        state_snapshot={
            "active_goals": [
                {
                    "goal_id": "goal-from-snapshot",
                    "target_name": "snapshot-goal",
                    "goal": "continue from projected snapshot",
                    "cwd": "/repo/current-goal",
                    "last_status": "working",
                }
            ]
        },
        api=_FakeDashboardApi(),
    )

    assert [goal["goal_id"] for goal in payload["active_goals"]] == [
        "goal-from-snapshot"
    ]
    assert payload["active_goals"][0]["current"] is True
    assert payload["target_names"] == ["snapshot-goal"]
