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


def test_dashboard_payload_projects_persisted_worker_lifecycle_from_snapshot() -> None:
    state_snapshot = _state_snapshot_with_lifecycle()
    state_snapshot["worker_lifecycle"] = {
        "status": "ok",
        "stage": "worktree_cleaned",
        "next_step": "monitor",
        "policy_status": "program_resolved",
        "program_action": "cleanup_worktree",
        "remaining_step": "monitor",
        "blocked_reason": None,
        "timeline": [
            {
                "stage": "worktree_cleaned",
                "action": "cleanup_worktree",
                "source": "cleanup",
                "status": "executed",
                "executed": True,
            }
        ],
    }
    state_snapshot.pop("worker_lifecycle_decision")

    payload = dashboard_payload(
        _report(),
        state_snapshot=state_snapshot,
        api=_StubDashboardApi(),
    )

    assert payload["worker_lifecycle"] == state_snapshot["worker_lifecycle"]


def test_dashboard_payload_projects_worker_lifecycle_execution_from_snapshot() -> None:
    state_snapshot = _state_snapshot_with_lifecycle()
    state_snapshot["worker_lifecycle_execution"] = {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "next_step": "cleanup_worktree",
        "status": "ready_to_delete",
        "delete_worktree_actions": [
            {
                "kind": "delete_worktree",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "confirm_delete_worktree": True,
                "base_ref": "main",
                "source": "worker_lifecycle",
                "delete_evidence": {
                    "archived": True,
                    "supervisor_protocol_status": "done",
                    "supervisor_worktree": True,
                    "integration_group": "already_integrated",
                    "main_contains_worker": True,
                    "main_has_worker_patch": False,
                    "dirty": False,
                    "base_ref": "main",
                },
            }
        ],
    }
    state_snapshot["worker_lifecycle_execution_result"] = {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "skipped": False,
        "count": 1,
        "result_actions": [
            {
                "kind": "delete_worktree",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "status": "deleted",
            }
        ],
    }

    payload = dashboard_payload(
        _report(),
        state_snapshot=state_snapshot,
        api=_StubDashboardApi(),
    )

    assert payload["worker_lifecycle_execution"] == {
        "status": "ready_to_delete",
        "kind": "cleanup_worktree",
        "next_step": "cleanup_worktree",
        "source": "worker_lifecycle",
        "action_count": 1,
        "execution_status": "executed",
        "execution_reason": "",
        "summary": {
            "archivable": 0,
            "delete_ready": 1,
            "delete_blocked": 0,
            "result_actions": 1,
        },
        "recommended_next_step": "monitor",
        "result_summary": "deleted source-worker",
        "decision_source": "worker_lifecycle_execution",
        "routing_reason": (
            "program-owned lifecycle execution recommended delete_ready"
        ),
        "result_actions": [
            {
                "kind": "delete_worktree",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "status": "deleted",
            }
        ],
        "delete_evidence": [
            {
                "target_name": "source-worker",
                "record_id": "managed-source",
                "archived": True,
                "supervisor_protocol_status": "done",
                "supervisor_worktree": True,
                "integration_group": "already_integrated",
                "main_contains_worker": True,
                "main_has_worker_patch": False,
                "dirty": False,
                "base_ref": "main",
            }
        ],
        "execute_hint": "--lifecycle-cleanup-execute",
        "execute_command": "isotope-supervisor loop --iterations 1 --lifecycle-cleanup-execute",
    }


def test_dashboard_payload_projects_merge_lifecycle_execute_command() -> None:
    state_snapshot = _state_snapshot_with_lifecycle()
    state_snapshot["worker_lifecycle_execution"] = {
        "kind": "merge_dispatch",
        "source": "worker_lifecycle",
        "next_step": "launch_merge_worker",
        "status": "ready_to_launch",
        "merge_dispatch": {
            "status": "ready_to_launch",
            "target_name": "source-worker",
        },
    }
    state_snapshot["worker_lifecycle_execution_result"] = {
        "kind": "launch_session",
        "display_kind": "merge_dispatch",
        "source": "integration_review",
        "skipped": True,
        "reason": "merge dispatch launch adapter required",
    }

    payload = dashboard_payload(
        _report(),
        state_snapshot=state_snapshot,
        api=_StubDashboardApi(),
    )

    assert payload["worker_lifecycle_execution"]["execute_command"] == (
        "isotope-supervisor loop --iterations 1 --merge-dispatch-execute"
    )


def test_dashboard_payload_projects_worker_lifecycle_delete_blockers() -> None:
    state_snapshot = _state_snapshot_with_lifecycle()
    state_snapshot["worker_lifecycle_execution"] = {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "next_step": "cleanup_worktree",
        "status": "blocked",
        "delete_worktree_blockers": [
            {
                "name": "dirty-worker",
                "target_name": "dirty-worker",
                "record_id": "managed-dirty",
                "archived": True,
                "supervisor_protocol_status": "done",
                "supervisor_worktree": True,
                "integration_group": "needs_review",
                "main_contains_worker": True,
                "main_has_worker_patch": True,
                "dirty": True,
                "reason": "worker worktree is dirty",
            }
        ],
    }

    payload = dashboard_payload(
        _report(),
        state_snapshot=state_snapshot,
        api=_StubDashboardApi(),
    )

    assert payload["worker_lifecycle_execution"]["action_count"] == 0
    assert payload["worker_lifecycle_execution"]["summary"] == {
        "archivable": 0,
        "delete_ready": 0,
        "delete_blocked": 1,
        "result_actions": 0,
    }
    assert (
        payload["worker_lifecycle_execution"]["recommended_next_step"]
        == "delete_blocked"
    )
    assert payload["worker_lifecycle_execution"]["delete_blockers"] == [
        {
            "target_name": "dirty-worker",
            "record_id": "managed-dirty",
            "archived": True,
            "supervisor_protocol_status": "done",
            "supervisor_worktree": True,
            "integration_group": "needs_review",
            "main_contains_worker": True,
            "main_has_worker_patch": True,
            "dirty": True,
            "reason": "worker worktree is dirty",
        }
    ]
    assert "execute_hint" not in payload["worker_lifecycle_execution"]
    assert "execute_command" not in payload["worker_lifecycle_execution"]


def test_dashboard_plain_prints_worker_lifecycle_delete_evidence(capsys) -> None:
    print_dashboard_plain(
        {
            "generated_at": "2026-06-04T12:00:00Z",
            "recommendation": {"label": "继续监控"},
            "pending_decisions_count": 0,
            "capability_calls_count": 0,
            "groups": {"needs_attention": [], "done": [], "working": []},
            "worker_lifecycle": {},
            "worker_lifecycle_execution": {
                "status": "ready_to_delete",
                "kind": "cleanup_worktree",
                "action_count": 1,
                "execution_status": "planned",
                "decision_source": "worker_lifecycle_execution",
                "routing_reason": (
                    "program-owned lifecycle execution recommended delete_ready"
                ),
                "delete_evidence": [
                    {
                        "target_name": "source-worker",
                        "archived": True,
                        "supervisor_protocol_status": "done",
                        "supervisor_worktree": True,
                        "integration_group": "already_integrated",
                        "main_contains_worker": True,
                        "main_has_worker_patch": False,
                        "dirty": False,
                    }
                ],
            },
        },
        api=_StubDashboardApi(),
    )

    text = capsys.readouterr().out
    assert "summary: archivable=0 delete_ready=1 delete_blocked=0 result_actions=0" in text
    assert "recommended_next_step=delete_ready" in text
    assert "decision_source=worker_lifecycle_execution" in text
    assert (
        "routing_reason=program-owned lifecycle execution recommended delete_ready"
        in text
    )
    assert (
        "delete_evidence=source-worker archived=true protocol=done "
        "worktree=true group=already_integrated integrated=true clean=true"
    ) in text


def test_dashboard_plain_prints_worker_lifecycle_delete_blockers(capsys) -> None:
    print_dashboard_plain(
        {
            "generated_at": "2026-06-04T12:00:00Z",
            "recommendation": {"label": "继续监控"},
            "pending_decisions_count": 0,
            "capability_calls_count": 0,
            "groups": {"needs_attention": [], "done": [], "working": []},
            "worker_lifecycle": {},
            "worker_lifecycle_execution": {
                "status": "blocked",
                "kind": "cleanup_worktree",
                "action_count": 0,
                "execution_status": "planned",
                "delete_blockers": [
                    {
                        "target_name": "dirty-worker",
                        "reason": "worker worktree is dirty",
                        "archived": True,
                        "supervisor_protocol_status": "done",
                        "supervisor_worktree": True,
                        "dirty": True,
                    }
                ],
            },
        },
        api=_StubDashboardApi(),
    )

    text = capsys.readouterr().out
    assert "summary: archivable=0 delete_ready=0 delete_blocked=1 result_actions=0" in text
    assert "recommended_next_step=delete_blocked" in text
    assert (
        "delete_blockers=dirty-worker reason=worker worktree is dirty "
        "archived=true protocol=done worktree=true clean=false"
    ) in text


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


def test_dashboard_plain_prints_worker_lifecycle_execution(capsys) -> None:
    payload = dashboard_payload(
        _report(),
        state_snapshot={
            **_state_snapshot_with_lifecycle(),
            "worker_lifecycle_execution": {
                "kind": "archive_cleanup",
                "source": "worker_lifecycle",
                "next_step": "archive_worker",
                "status": "ready_to_archive",
                "cleanup_candidates": [
                    {
                        "kind": "managed_worker",
                        "name": "source-worker",
                        "record_id": "managed-source",
                    }
                ],
            },
            "worker_lifecycle_execution_result": {
                "kind": "archive_cleanup",
                "source": "worker_lifecycle",
                "count": 1,
                "result_actions": [
                    {
                        "kind": "managed_worker",
                        "target_name": "source-worker",
                        "record_id": "managed-source",
                        "status": "archived",
                    }
                ],
            },
        },
        api=_StubDashboardApi(),
    )

    print_dashboard_plain(payload, api=_StubDashboardApi())

    text = capsys.readouterr().out
    assert "execution=archive_cleanup status=executed actions=1" in text
    assert "summary: archivable=1 delete_ready=0 delete_blocked=0 result_actions=1" in text
    assert "recommended_next_step=monitor" in text
    assert "result=archived source-worker" in text
    assert "execute_hint=--lifecycle-archive-execute" in text
    assert (
        "execute_command=isotope-supervisor loop --iterations 1 "
        "--lifecycle-archive-execute"
    ) in text


def test_dashboard_html_includes_worker_lifecycle_card() -> None:
    html = dashboard_page_html()

    assert 'id="worker-lifecycle-card"' in html
    assert 'id="worker-lifecycle-execution"' in html
    assert 'id="worker-lifecycle-execution-copy"' in html
    assert 'id="worker-lifecycle-execution-run"' in html
    assert "copyWorkerLifecycleExecutionCommand" in html
    assert "executeWorkerLifecyclePlan" in html
    assert "/worker-lifecycle/execute" in html
    assert "renderDashboardPayload(payload.dashboard)" in html
    assert "renderWorkerLifecycle" in html
