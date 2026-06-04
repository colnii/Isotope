from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from isotope.features.supervisor.commands.dashboard import (
    dashboard_payload,
    print_dashboard_plain,
)
from isotope.features.supervisor.dashboard.html import dashboard_page_html


class _StubRecommendation:
    def to_dict(self) -> dict[str, Any]:
        return {"label": "继续监控", "action": "monitor"}


class _StubDashboardApi:
    DASHBOARD_GROUP_LABELS = {
        "needs_attention": "需要看",
        "done": "已完成",
        "working": "工作中",
    }

    def _cwd_is_existing_dir(self, value: Any) -> bool:
        return False

    def _session_marks_terminal_done(self, session: Any) -> bool:
        return False

    def _is_completed_session(self, session: Any) -> bool:
        return False

    def _managed_tmux_command_suggestions(self, session: Any) -> list[dict[str, Any]]:
        return []


def _report() -> SimpleNamespace:
    return SimpleNamespace(
        sessions=[],
        generated_at="2026-06-04T12:00:00Z",
        recommendation=_StubRecommendation(),
    )


def _state_snapshot_with_lifecycle() -> dict[str, Any]:
    return {
        "status": "ok",
        "kind": "supervisor_state_snapshot",
        "schema_version": 1,
        "active_goals": [],
        "active_decisions": [],
        "notifications": {"total": 0, "unread": 0, "recent": []},
        "worker_lifecycle_decision": {
            "kind": "worker_lifecycle_decision",
            "stage": "archived",
            "next_step": "cleanup_worktree",
            "policy": {
                "policy_status": "program_resolved",
                "program_action": "archive_integrated",
                "remaining_step": "cleanup_worktree",
                "blocked_reason": None,
            },
            "timeline": [
                {
                    "stage": "integrated",
                    "action": "archive_integrated",
                    "source": "integration_review",
                    "status": "observed",
                    "executed": False,
                },
                {
                    "stage": "archived",
                    "action": "archive_integrated",
                    "source": "cleanup",
                    "status": "executed",
                    "executed": True,
                },
            ],
        },
    }


def test_dashboard_payload_projects_worker_lifecycle_from_state_snapshot() -> None:
    payload = dashboard_payload(
        _report(),
        state_snapshot=_state_snapshot_with_lifecycle(),
        api=_StubDashboardApi(),
    )

    assert payload["worker_lifecycle"] == {
        "status": "ok",
        "stage": "archived",
        "next_step": "cleanup_worktree",
        "policy_status": "program_resolved",
        "program_action": "archive_integrated",
        "remaining_step": "cleanup_worktree",
        "blocked_reason": None,
        "timeline": [
            {
                "stage": "integrated",
                "action": "archive_integrated",
                "source": "integration_review",
                "status": "observed",
                "executed": False,
            },
            {
                "stage": "archived",
                "action": "archive_integrated",
                "source": "cleanup",
                "status": "executed",
                "executed": True,
            },
        ],
    }


def test_dashboard_plain_prints_worker_lifecycle(capsys) -> None:
    payload = dashboard_payload(
        _report(),
        state_snapshot=_state_snapshot_with_lifecycle(),
        api=_StubDashboardApi(),
    )

    print_dashboard_plain(payload, api=_StubDashboardApi())

    text = capsys.readouterr().out
    assert "Worker 生命周期：stage=archived next_step=cleanup_worktree policy=program_resolved" in text
    assert "remaining_step=cleanup_worktree" in text
    assert "timeline: integrated/archive_integrated observed; archived/archive_integrated executed" in text


def test_dashboard_html_includes_worker_lifecycle_card() -> None:
    html = dashboard_page_html()

    assert 'id="worker-lifecycle-card"' in html
    assert "renderWorkerLifecycle" in html
