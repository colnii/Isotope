from __future__ import annotations

from isotope.features.supervisor.lifecycle.decision import (
    build_worker_lifecycle_decision,
)


def test_lifecycle_decision_dispatches_merge_for_ready_workers() -> None:
    decision = build_worker_lifecycle_decision(
        integration_review=_integration_review(ready=2),
        merge_dispatch={
            "status": "ready_to_launch",
            "launch_spec": {"target_name": "supervisor-merge-dispatch"},
        },
    )

    assert decision["kind"] == "worker_lifecycle_decision"
    assert decision["action"] == "dispatch_merge"
    assert decision["source"] == "integration_review"
    assert decision["reason"] == "ready_to_integrate workers require merge dispatch"
    assert decision["summary"]["ready_to_integrate"] == 2
    assert decision["summary"]["merge_dispatch_status"] == "ready_to_launch"


def test_lifecycle_decision_monitors_existing_merge_worker() -> None:
    decision = build_worker_lifecycle_decision(
        integration_review=_integration_review(ready=1),
        merge_dispatch={
            "status": "worker_already_running",
            "running_worker": {"name": "supervisor-merge-dispatch"},
        },
    )

    assert decision["action"] == "monitor"
    assert decision["reason"] == "merge worker already running"
    assert decision["summary"]["running_worker"]["name"] == "supervisor-merge-dispatch"


def test_lifecycle_decision_archives_when_workers_are_integrated() -> None:
    decision = build_worker_lifecycle_decision(
        integration_review=_integration_review(already_integrated=2),
        cleanup_candidates=[{"kind": "managed_worker", "record_id": "managed-a"}],
    )

    assert decision["action"] == "archive_integrated"
    assert decision["source"] == "integration_review"
    assert decision["reason"] == "integrated workers can be archived"
    assert decision["summary"]["already_integrated"] == 2
    assert decision["summary"]["cleanup_candidates"] == 1


def test_lifecycle_decision_records_archive_execution() -> None:
    decision = build_worker_lifecycle_decision(
        cleanup_archived=[
            {
                "kind": "merge_worker",
                "record_id": "managed-merge",
                "managed": {"status": "archived"},
            }
        ],
    )

    assert decision["action"] == "archive_integrated"
    assert decision["source"] == "cleanup"
    assert decision["reason"] == "integrated workers archived"
    assert decision["summary"]["cleanup_archived"] == 1
    assert decision["execution"] == [
        {
            "kind": "merge_worker",
            "record_id": "managed-merge",
            "managed": {"status": "archived"},
        }
    ]


def test_lifecycle_decision_records_worktree_cleanup_execution() -> None:
    decision = build_worker_lifecycle_decision(
        cleanup_deleted_worktrees=[
            {
                "kind": "delete_worktree",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "deleted_worktree": "/repo/.worktrees/supervisor/source-worker",
            }
        ],
    )

    assert decision["action"] == "cleanup_worktree"
    assert decision["source"] == "cleanup"
    assert decision["reason"] == "archived worker worktrees deleted"
    assert decision["summary"]["cleanup_deleted_worktrees"] == 1
    assert decision["execution"] == [
        {
            "kind": "delete_worktree",
            "target_name": "source-worker",
            "record_id": "managed-source",
            "deleted_worktree": "/repo/.worktrees/supervisor/source-worker",
        }
    ]


def test_lifecycle_decision_needs_human_for_conflicts() -> None:
    decision = build_worker_lifecycle_decision(
        integration_review=_integration_review(conflict=1, needs_review=1),
    )

    assert decision["action"] == "needs_human"
    assert decision["source"] == "integration_review"
    assert (
        decision["reason"]
        == "integration review has conflict or review-required workers"
    )
    assert decision["summary"]["conflict_risk"] == 1
    assert decision["summary"]["needs_review"] == 1


def test_lifecycle_decision_monitors_empty_review() -> None:
    decision = build_worker_lifecycle_decision()

    assert decision["action"] == "monitor"
    assert decision["source"] == "worker_review"
    assert decision["reason"] == "no lifecycle-ready worker evidence"


def _integration_review(
    *,
    ready: int = 0,
    conflict: int = 0,
    needs_review: int = 0,
    already_integrated: int = 0,
) -> dict[str, object]:
    return {
        "summary": {
            "ready_to_integrate": ready,
            "conflict_risk": conflict,
            "needs_review": needs_review,
            "already_integrated": already_integrated,
        },
        "groups": {
            "ready_to_integrate": [
                {"record_id": f"ready-{index}"} for index in range(ready)
            ],
            "conflict_risk": [
                {"record_id": f"conflict-{index}"} for index in range(conflict)
            ],
            "needs_review": [
                {"record_id": f"review-{index}"} for index in range(needs_review)
            ],
            "already_integrated": [
                {"record_id": f"done-{index}"}
                for index in range(already_integrated)
            ],
        },
    }
