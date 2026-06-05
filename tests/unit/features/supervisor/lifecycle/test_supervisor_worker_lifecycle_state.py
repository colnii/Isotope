from __future__ import annotations

import json
from datetime import UTC, datetime

from isotope.features.supervisor.state.worker_lifecycle import (
    default_worker_lifecycle_path,
    read_latest_worker_lifecycle_event,
    read_latest_worker_lifecycle,
    record_worker_lifecycle_decision,
    worker_lifecycle_projection_payload,
)


def test_worker_lifecycle_projection_payload_redacts_decision_to_public_fields() -> None:
    projection = worker_lifecycle_projection_payload(
        worker_lifecycle_decision=_decision(
            extra={"summary": {"raw": "details"}, "execution": {"command": "secret"}}
        )
    )

    assert projection == {
        "status": "ok",
        "stage": "archived",
        "next_step": "cleanup_worktree",
        "policy_status": "program_resolved",
        "program_action": "archive_integrated",
        "remaining_step": "cleanup_worktree",
        "blocked_reason": None,
        "timeline": [
            {
                "stage": "archived",
                "action": "archive_integrated",
                "source": "cleanup",
                "status": "executed",
                "executed": True,
            }
        ],
    }


def test_record_worker_lifecycle_decision_appends_and_deduplicates(tmp_path) -> None:
    now = lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC)

    first = record_worker_lifecycle_decision(
        codex_home=tmp_path,
        worker_lifecycle_decision=_decision(),
        now=now,
    )
    duplicate = record_worker_lifecycle_decision(
        codex_home=tmp_path,
        worker_lifecycle_decision=_decision(),
        now=now,
    )

    assert first is not None
    assert first["event"] == "worker_lifecycle_projection"
    assert first["created_at"] == "2026-06-04T12:00:00+00:00"
    assert first["worker_lifecycle"]["stage"] == "archived"
    assert duplicate is None
    lines = default_worker_lifecycle_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == first
    assert read_latest_worker_lifecycle(codex_home=tmp_path) == first["worker_lifecycle"]


def test_record_worker_lifecycle_decision_persists_execution_projection(tmp_path) -> None:
    event = record_worker_lifecycle_decision(
        codex_home=tmp_path,
        worker_lifecycle_decision=_decision(),
        worker_lifecycle_execution={
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
                    "command": "private command is not projected",
                    "delete_evidence": {
                        "archived": True,
                        "supervisor_protocol_status": "done",
                        "supervisor_worktree": True,
                        "integration_group": "already_integrated",
                        "main_contains_worker": True,
                        "main_has_worker_patch": False,
                        "dirty": False,
                        "base_ref": "main",
                        "private_path": "/repo/.worktrees/supervisor/source-worker",
                    },
                }
            ],
        },
        worker_lifecycle_execution_result={
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "deleted": [
                {
                    "kind": "delete_worktree",
                    "target_name": "source-worker",
                    "command": "private command is not projected",
                    "deleted_worktree": "/repo/.worktrees/supervisor/source-worker",
                    "managed": {
                        "record_id": "managed-source",
                        "name": "source-worker",
                        "status": "archived",
                        "prompt": "private prompt is not projected",
                    },
                }
            ],
        },
    )

    assert event is not None
    assert event["worker_lifecycle_execution"] == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "next_step": "cleanup_worktree",
        "status": "ready_to_delete",
        "delete_worktree_actions": [
            {
                "kind": "delete_worktree",
                "target_name": "source-worker",
                "record_id": "managed-source",
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
    assert event["worker_lifecycle_execution_result"] == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "skipped": False,
        "reason": None,
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
    assert read_latest_worker_lifecycle_event(codex_home=tmp_path) == event


def test_record_worker_lifecycle_decision_persists_delete_blocker_projection(
    tmp_path,
) -> None:
    event = record_worker_lifecycle_decision(
        codex_home=tmp_path,
        worker_lifecycle_decision=_decision(),
        worker_lifecycle_execution={
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "next_step": "cleanup_worktree",
            "status": "blocked",
            "delete_worktree_blockers": [
                {
                    "name": "dirty-worker",
                    "target_name": "dirty-worker",
                    "record_id": "managed-dirty",
                    "cwd": "/repo/.worktrees/supervisor/dirty-worker",
                    "archived": True,
                    "supervisor_protocol_status": "done",
                    "supervisor_worktree": True,
                    "integration_group": "needs_review",
                    "main_contains_worker": True,
                    "main_has_worker_patch": True,
                    "dirty": True,
                    "worker_commit": "dirty111",
                    "base_ref": "main",
                    "reason": "worker worktree is dirty",
                }
            ],
        },
    )

    assert event is not None
    assert event["worker_lifecycle_execution"] == {
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
                "worker_commit": "dirty111",
                "base_ref": "main",
                "reason": "worker worktree is dirty",
            }
        ],
    }


def test_read_latest_worker_lifecycle_skips_malformed_entries(tmp_path) -> None:
    path = default_worker_lifecycle_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            [
                "{bad json",
                json.dumps(
                    {
                        "event": "other",
                        "worker_lifecycle": {"status": "ok", "stage": "ignored"},
                    }
                ),
                json.dumps(
                    {
                        "event": "worker_lifecycle_projection",
                        "worker_lifecycle": {
                            "status": "ok",
                            "stage": "ready_to_merge",
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    assert read_latest_worker_lifecycle(codex_home=tmp_path) == {
        "status": "ok",
        "stage": "ready_to_merge",
    }


def _decision(*, extra: dict | None = None) -> dict:
    decision = {
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
                "stage": "archived",
                "action": "archive_integrated",
                "source": "cleanup",
                "status": "executed",
                "executed": True,
                "execution": [{"record_id": "managed-merge"}],
            }
        ],
    }
    if extra:
        decision.update(extra)
    return decision
