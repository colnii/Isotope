from __future__ import annotations

from typing import Any

from isotope.features.supervisor.commands.plain_rendering import print_supervise_plain


class _StubApi:
    def _dashboard_payload(self, report: Any, *, decision_requests: list[dict[str, Any]]):
        return {"report": report, "decision_requests": decision_requests}

    def _print_dashboard_plain(self, payload: dict[str, Any]) -> None:
        print("[dashboard]")

    def _is_merge_dispatch_launch_action(self, action: dict[str, Any]) -> bool:
        return False


def test_supervise_plain_prints_worker_lifecycle_summary(capsys):
    payload = {
        "automation": {"ready": True, "reason": "ready"},
        "recommendation": {"label": "继续监控", "action": "monitor"},
        "worker_lifecycle_decision": {
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
                    "status": "observed",
                    "executed": False,
                },
                {
                    "stage": "archived",
                    "action": "archive_integrated",
                    "status": "executed",
                    "executed": True,
                },
            ],
        },
    }

    print_supervise_plain(payload, report=object(), api=_StubApi())

    text = capsys.readouterr().out
    assert "[Worker 生命周期]" in text
    assert "stage=archived next_step=cleanup_worktree policy=program_resolved" in text
    assert "remaining_step=cleanup_worktree" in text
    assert "timeline: integrated/archive_integrated observed; archived/archive_integrated executed" in text
