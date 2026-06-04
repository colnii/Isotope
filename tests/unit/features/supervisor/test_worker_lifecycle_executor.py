from __future__ import annotations

import argparse

from isotope.features.supervisor.lifecycle.executor import (
    build_worker_lifecycle_execution_plan,
    worker_lifecycle_execution_action,
    worker_lifecycle_execution_planned_executed,
    worker_lifecycle_execution_recommended_next_step,
    worker_lifecycle_execution_summary,
)
from isotope.features.supervisor.commands.supervise.action import (
    append_supervise_llm_action,
)
from isotope.features.supervisor.commands.supervise.execution import (
    append_supervise_execution,
)
from isotope.features.supervisor.commands.supervise.planning import (
    append_supervise_planning_payload,
)


def test_lifecycle_execution_plan_launches_merge_worker_from_program_next_step() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(next_step="launch_merge_worker"),
        merge_dispatch={
            "status": "ready_to_launch",
            "launch_spec": {
                "kind": "launch_session",
                "target_name": "supervisor-merge-dispatch",
                "source": "integration_review",
            },
        },
    )

    assert plan is not None
    assert plan.to_dict() == {
        "kind": "merge_dispatch",
        "source": "worker_lifecycle",
        "next_step": "launch_merge_worker",
        "status": "ready_to_launch",
        "merge_dispatch": {
            "status": "ready_to_launch",
            "launch_spec": {
                "kind": "launch_session",
                "target_name": "supervisor-merge-dispatch",
                "source": "integration_review",
            },
        },
    }
    assert worker_lifecycle_execution_action(plan.to_dict()) == {
        "kind": "launch_session",
        "target_name": "supervisor-merge-dispatch",
        "source": "integration_review",
    }


def test_lifecycle_execution_summary_counts_queue_and_result_actions() -> None:
    assert worker_lifecycle_execution_summary(None) == {
        "archivable": 0,
        "delete_ready": 0,
        "delete_blocked": 0,
        "result_actions": 0,
    }
    plan = {
        "cleanup_candidates": [{"name": "archivable-worker"}],
        "delete_worktree_actions": [{"target_name": "delete-ready-worker"}],
        "delete_worktree_blockers": [{"target_name": "dirty-worker"}],
    }

    assert worker_lifecycle_execution_summary(
        plan,
        {"deleted": [{"target_name": "delete-ready-worker"}]},
    ) == {
        "archivable": 1,
        "delete_ready": 1,
        "delete_blocked": 1,
        "result_actions": 1,
    }
    assert worker_lifecycle_execution_summary(
        plan,
        {"result_actions": [{"target_name": "projected-worker"}]},
    )["result_actions"] == 1


def test_lifecycle_execution_recommended_next_step_is_program_readable() -> None:
    assert worker_lifecycle_execution_recommended_next_step(None) == "monitor"
    assert (
        worker_lifecycle_execution_recommended_next_step(
            {"cleanup_candidates": [{"name": "archivable-worker"}]}
        )
        == "archive_ready"
    )
    assert (
        worker_lifecycle_execution_recommended_next_step(
            {"delete_worktree_actions": [{"target_name": "delete-ready-worker"}]}
        )
        == "delete_ready"
    )
    assert (
        worker_lifecycle_execution_recommended_next_step(
            {"delete_worktree_blockers": [{"target_name": "dirty-worker"}]}
        )
        == "delete_blocked"
    )
    assert (
        worker_lifecycle_execution_recommended_next_step(
            {"delete_worktree_actions": [{"target_name": "deleted-worker"}]},
            {"deleted": [{"target_name": "deleted-worker"}]},
        )
        == "monitor"
    )


def test_lifecycle_execution_plan_monitors_existing_merge_worker() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(next_step="launch_merge_worker"),
        merge_dispatch={
            "status": "worker_already_running",
            "running_worker": {
                "name": "supervisor-merge-dispatch",
                "record_id": "managed-merge",
            },
        },
    )

    assert plan is not None
    plan_payload = plan.to_dict()
    assert worker_lifecycle_execution_action(plan_payload) == {
        "kind": "monitor",
        "reason": "merge worker already running",
        "managed": {
            "name": "supervisor-merge-dispatch",
            "record_id": "managed-merge",
        },
    }
    assert worker_lifecycle_execution_planned_executed(plan_payload) == {
        "kind": "monitor",
        "reason": "merge worker already running",
        "managed": {
            "name": "supervisor-merge-dispatch",
            "record_id": "managed-merge",
        },
        "skipped": True,
    }


def test_lifecycle_execution_plan_ignores_non_program_decisions() -> None:
    assert (
        build_worker_lifecycle_execution_plan(
            worker_lifecycle_decision=_decision(
                next_step="monitor",
                policy_status="model_required",
                program_action=None,
            ),
            merge_dispatch={
                "status": "ready_to_launch",
                "launch_spec": {"kind": "launch_session"},
            },
        )
        is None
    )


def test_lifecycle_execution_plan_archives_ready_cleanup_workers() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(
            next_step="archive_worker",
            program_action="archive_integrated",
        ),
        cleanup_candidates=[
            {
                "kind": "managed_worker",
                "name": "source-worker",
                "record_id": "managed-source",
                "status": "done",
            },
            {
                "kind": "notification",
                "notification_id": "notification-done",
            },
        ],
    )

    assert plan is not None
    assert plan.to_dict() == {
        "kind": "archive_cleanup",
        "source": "worker_lifecycle",
        "next_step": "archive_worker",
        "status": "ready_to_archive",
        "cleanup_candidates": [
            {
                "kind": "managed_worker",
                "name": "source-worker",
                "record_id": "managed-source",
                "status": "done",
            }
        ],
    }
    assert worker_lifecycle_execution_action(plan.to_dict()) == {
        "kind": "archive_cleanup",
        "source": "worker_lifecycle",
        "decision_source": "worker_lifecycle_execution",
        "routing_reason": (
            "program-owned lifecycle execution recommended archive_ready"
        ),
        "count": 1,
        "target_name": "source-worker",
        "record_id": "managed-source",
        "recommended_next_step": "archive_ready",
    }
    assert worker_lifecycle_execution_planned_executed(plan.to_dict()) == {
        "kind": "archive_cleanup",
        "source": "worker_lifecycle",
        "skipped": True,
        "reason": "lifecycle archive execution requires --lifecycle-archive-execute",
        "count": 1,
    }


def test_lifecycle_execution_plan_deletes_guarded_worktree_candidates() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(
            next_step="cleanup_worktree",
            program_action="archive_integrated",
        ),
        delete_worktree_candidates=[
            {
                "name": "source-worker",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "archived": True,
                "integration_group": "already_integrated",
                "main_contains_worker": True,
                "main_has_worker_patch": False,
                "dirty": False,
                "supervisor_protocol_status": "done",
                "supervisor_worktree": True,
            },
            {
                "name": "review-worker",
                "target_name": "review-worker",
                "record_id": "managed-review",
                "archived": True,
                "integration_group": "needs_review",
            },
        ],
    )

    assert plan is not None
    assert plan.to_dict() == {
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
    assert worker_lifecycle_execution_action(plan.to_dict()) == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "decision_source": "worker_lifecycle_execution",
        "routing_reason": (
            "program-owned lifecycle execution recommended delete_ready"
        ),
        "count": 1,
        "target_name": "source-worker",
        "record_id": "managed-source",
        "recommended_next_step": "delete_ready",
    }


def test_lifecycle_execution_plan_reports_cleanup_worktree_blockers() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(
            next_step="cleanup_worktree",
            program_action="archive_integrated",
        ),
        delete_worktree_candidates=[],
        delete_worktree_blockers=[
            {
                "name": "dirty-worker",
                "target_name": "dirty-worker",
                "record_id": "managed-dirty",
                "archived": True,
                "supervisor_protocol_status": "done",
                "supervisor_worktree": True,
                "reason": "worker worktree is dirty",
            }
        ],
    )

    assert plan is not None
    assert plan.to_dict() == {
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
                "reason": "worker worktree is dirty",
            }
        ],
    }
    assert worker_lifecycle_execution_planned_executed(plan.to_dict()) == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "skipped": True,
        "reason": "worktree delete blockers require attention",
        "count": 0,
        "blockers": 1,
    }


def test_lifecycle_execution_action_monitors_delete_blockers() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(
            next_step="cleanup_worktree",
            program_action="archive_integrated",
        ),
        delete_worktree_blockers=[
            {
                "name": "dirty-worker",
                "target_name": "dirty-worker",
                "record_id": "managed-dirty",
                "reason": "worker worktree is dirty",
            }
        ],
    )

    assert plan is not None
    assert worker_lifecycle_execution_action(plan.to_dict()) == {
        "kind": "monitor",
        "source": "worker_lifecycle",
        "decision_source": "worker_lifecycle_execution",
        "routing_reason": (
            "program-owned lifecycle execution recommended delete_blocked"
        ),
        "reason": "worker lifecycle delete is blocked",
        "recommended_next_step": "delete_blocked",
        "blockers": 1,
        "command_suggestion": None,
    }


def test_supervise_action_uses_lifecycle_execution_plan() -> None:
    payload: dict[str, object] = {}
    action = append_supervise_llm_action(
        argparse.Namespace(llm_action=True, llm_execute=False),
        payload,
        action_report=object(),
        active_goals=[],
        explicit_goal=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=_merge_dispatch_plan(),
        api=_StubActionApi(),
    )

    assert action == {
        "kind": "launch_session",
        "target_name": "supervisor-merge-dispatch",
        "source": "integration_review",
    }
    assert payload["llm_action"] == action


def test_supervise_action_routes_delete_blockers_without_llm() -> None:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(
            next_step="cleanup_worktree",
            program_action="archive_integrated",
        ),
        delete_worktree_blockers=[
            {
                "name": "dirty-worker",
                "target_name": "dirty-worker",
                "record_id": "managed-dirty",
                "reason": "worker worktree is dirty",
            }
        ],
    )
    assert plan is not None
    payload: dict[str, object] = {}

    action = append_supervise_llm_action(
        argparse.Namespace(llm_action=True, llm_execute=False),
        payload,
        action_report=object(),
        active_goals=[],
        explicit_goal=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=plan.to_dict(),
        api=_StubActionApi(),
    )

    assert action == {
        "kind": "monitor",
        "source": "worker_lifecycle",
        "decision_source": "worker_lifecycle_execution",
        "routing_reason": (
            "program-owned lifecycle execution recommended delete_blocked"
        ),
        "reason": "worker lifecycle delete is blocked",
        "recommended_next_step": "delete_blocked",
        "blockers": 1,
        "command_suggestion": None,
    }
    assert payload["llm_action"] == action


def test_supervise_planning_builds_archive_worker_lifecycle_execution() -> None:
    payload: dict[str, object] = {}
    planning = append_supervise_planning_payload(
        argparse.Namespace(
            command="loop",
            codex_home="/tmp/codex-home",
            llm_action=True,
            llm_execute=False,
            max_fanout_launches=5,
        ),
        payload,
        report=object(),
        active_goals=[],
        goal_updates=[],
        goal_replenishment=None,
        worker_reviews=None,
        api=_StubPlanningApi(
            integration_review={
                "summary": {
                    "ready_to_integrate": 0,
                    "conflict_risk": 0,
                    "needs_review": 0,
                    "already_integrated": 1,
                }
            },
            cleanup_candidates=[
                {
                    "kind": "managed_worker",
                    "name": "source-worker",
                    "record_id": "managed-source",
                }
            ],
        ),
    )

    assert planning.lifecycle_execution == {
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
    }
    assert payload["worker_lifecycle_decision"]["next_step"] == "archive_worker"
    assert payload["worker_lifecycle_execution"] == planning.lifecycle_execution


def test_supervise_planning_builds_cleanup_worktree_lifecycle_execution() -> None:
    payload: dict[str, object] = {
        "cleanup_archived": [
            {
                "kind": "managed_worker",
                "name": "source-worker",
                "record_id": "managed-source",
            }
        ]
    }
    planning = append_supervise_planning_payload(
        argparse.Namespace(
            command="loop",
            codex_home="/tmp/codex-home",
            llm_action=True,
            llm_execute=False,
            max_fanout_launches=5,
        ),
        payload,
        report=object(),
        active_goals=[],
        goal_updates=[],
        goal_replenishment=None,
        worker_reviews=None,
        api=_StubPlanningApi(
            delete_worktree_candidates=[
                {
                    "name": "source-worker",
                    "target_name": "source-worker",
                    "record_id": "managed-source",
                    "archived": True,
                    "integration_group": "already_integrated",
                }
            ],
        ),
    )

    assert planning.lifecycle_execution == {
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
                        "supervisor_protocol_status": "",
                        "supervisor_worktree": False,
                        "integration_group": "already_integrated",
                        "main_contains_worker": None,
                        "main_has_worker_patch": None,
                        "dirty": None,
                        "base_ref": "main",
                    },
                }
            ],
        }
    assert payload["worker_lifecycle_decision"]["next_step"] == "cleanup_worktree"
    assert payload["worker_lifecycle_execution"] == planning.lifecycle_execution


def test_supervise_planning_builds_cleanup_worktree_blocker_execution() -> None:
    payload: dict[str, object] = {
        "cleanup_archived": [
            {
                "kind": "managed_worker",
                "name": "dirty-worker",
                "record_id": "managed-dirty",
            }
        ]
    }
    planning = append_supervise_planning_payload(
        argparse.Namespace(
            command="loop",
            codex_home="/tmp/codex-home",
            llm_action=True,
            llm_execute=False,
            max_fanout_launches=5,
        ),
        payload,
        report=object(),
        active_goals=[],
        goal_updates=[],
        goal_replenishment=None,
        worker_reviews=None,
        api=_StubPlanningApi(
            delete_worktree_blockers=[
                {
                    "name": "dirty-worker",
                    "target_name": "dirty-worker",
                    "record_id": "managed-dirty",
                    "reason": "worker worktree is dirty",
                }
            ],
        ),
    )

    assert planning.lifecycle_execution == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "next_step": "cleanup_worktree",
        "status": "blocked",
        "delete_worktree_blockers": [
            {
                "name": "dirty-worker",
                "target_name": "dirty-worker",
                "record_id": "managed-dirty",
                "reason": "worker worktree is dirty",
            }
        ],
    }
    assert payload["worker_lifecycle_execution"] == planning.lifecycle_execution


def test_supervise_execution_archives_lifecycle_cleanup_candidates() -> None:
    api = _StubExecutionApi()
    payload: dict[str, object] = {
        "worker_lifecycle_decision": _decision(
            next_step="archive_worker",
            program_action="archive_integrated",
        )
    }
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=payload["worker_lifecycle_decision"],
        cleanup_candidates=[
            {
                "kind": "managed_worker",
                "name": "source-worker",
                "record_id": "managed-source",
            }
        ],
    )
    assert plan is not None

    executed = append_supervise_execution(
        argparse.Namespace(
            llm_execute=True,
            auto_execute=False,
            execute=False,
            codex_home="/tmp/codex-home",
            merge_dispatch_execute=False,
            lifecycle_cleanup_execute=True,
        ),
        payload,
        report=object(),
        action_report=object(),
        active_goals=[],
        goal_replenishment=None,
        worker_reviews=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=plan.to_dict(),
        api=api,
    )

    assert executed == {
        "kind": "archive_cleanup",
        "source": "worker_lifecycle",
        "archived": [
            {
                "kind": "managed_worker",
                "name": "source-worker",
                "record_id": "managed-source",
                "archived": True,
            }
        ],
    }
    assert payload["worker_lifecycle_decision"]["execution"] == executed
    assert api.archived == [
        {
            "kind": "managed_worker",
            "name": "source-worker",
            "record_id": "managed-source",
        }
    ]


def test_supervise_execution_archives_with_archive_execute_flag() -> None:
    api = _StubExecutionApi()
    payload: dict[str, object] = {}
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(
            next_step="archive_worker",
            program_action="archive_integrated",
        ),
        cleanup_candidates=[
            {
                "kind": "managed_worker",
                "name": "source-worker",
                "record_id": "managed-source",
            }
        ],
    )
    assert plan is not None

    executed = append_supervise_execution(
        argparse.Namespace(
            llm_execute=True,
            auto_execute=False,
            execute=False,
            codex_home="/tmp/codex-home",
            merge_dispatch_execute=False,
            lifecycle_archive_execute=True,
            lifecycle_cleanup_execute=False,
        ),
        payload,
        report=object(),
        action_report=object(),
        active_goals=[],
        goal_replenishment=None,
        worker_reviews=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=plan.to_dict(),
        api=api,
    )

    assert executed == {
        "kind": "archive_cleanup",
        "source": "worker_lifecycle",
        "archived": [
            {
                "kind": "managed_worker",
                "name": "source-worker",
                "record_id": "managed-source",
                "archived": True,
            }
        ],
    }
    assert api.archived == [
        {
            "kind": "managed_worker",
            "name": "source-worker",
            "record_id": "managed-source",
        }
    ]


def test_supervise_execution_deletes_lifecycle_worktree_candidates() -> None:
    api = _StubExecutionApi()
    payload: dict[str, object] = {
        "worker_lifecycle_decision": _decision(
            next_step="cleanup_worktree",
            program_action="archive_integrated",
        )
    }
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=payload["worker_lifecycle_decision"],
        delete_worktree_candidates=[
            {
                "name": "source-worker",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "archived": True,
                "integration_group": "already_integrated",
            }
        ],
    )
    assert plan is not None

    executed = append_supervise_execution(
        argparse.Namespace(
            llm_execute=True,
            auto_execute=False,
            execute=False,
            codex_home="/tmp/codex-home",
            merge_dispatch_execute=False,
            lifecycle_cleanup_execute=True,
        ),
        payload,
        report=object(),
        action_report=object(),
        active_goals=[],
        goal_replenishment=None,
        worker_reviews=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=plan.to_dict(),
        api=api,
    )

    assert executed == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "deleted": [
            {
                "kind": "delete_worktree",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "deleted_worktree": "/tmp/source-worker",
            }
        ],
    }
    assert payload["worker_lifecycle_decision"]["execution"] == executed
    assert api.deleted == [
        {
            "kind": "delete_worktree",
            "target_name": "source-worker",
            "record_id": "managed-source",
            "confirm_delete_worktree": True,
            "base_ref": "main",
            "source": "worker_lifecycle",
            "delete_evidence": {
                "archived": True,
                "supervisor_protocol_status": "",
                "supervisor_worktree": False,
                "integration_group": "already_integrated",
                "main_contains_worker": None,
                "main_has_worker_patch": None,
                "dirty": None,
                "base_ref": "main",
            },
        }
    ]


def test_supervise_execution_does_not_delete_worktrees_with_archive_execute_flag() -> None:
    api = _StubExecutionApi()
    payload: dict[str, object] = {}
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(
            next_step="cleanup_worktree",
            program_action="archive_integrated",
        ),
        delete_worktree_candidates=[
            {
                "name": "source-worker",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "archived": True,
                "integration_group": "already_integrated",
            }
        ],
    )
    assert plan is not None

    executed = append_supervise_execution(
        argparse.Namespace(
            llm_execute=True,
            auto_execute=False,
            execute=False,
            codex_home="/tmp/codex-home",
            merge_dispatch_execute=False,
            lifecycle_archive_execute=True,
            lifecycle_cleanup_execute=False,
        ),
        payload,
        report=object(),
        action_report=object(),
        active_goals=[],
        goal_replenishment=None,
        worker_reviews=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=plan.to_dict(),
        api=api,
    )

    assert executed == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "skipped": True,
        "reason": "lifecycle cleanup execution requires --lifecycle-cleanup-execute",
        "count": 1,
    }
    assert api.deleted == []


def test_supervise_execution_skips_cleanup_worktree_blockers_even_with_cleanup_flag() -> None:
    api = _StubExecutionApi()
    payload: dict[str, object] = {}
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(
            next_step="cleanup_worktree",
            program_action="archive_integrated",
        ),
        delete_worktree_candidates=[],
        delete_worktree_blockers=[
            {
                "name": "dirty-worker",
                "target_name": "dirty-worker",
                "record_id": "managed-dirty",
                "reason": "worker worktree is dirty",
            }
        ],
    )
    assert plan is not None

    executed = append_supervise_execution(
        argparse.Namespace(
            llm_execute=True,
            auto_execute=False,
            execute=False,
            codex_home="/tmp/codex-home",
            merge_dispatch_execute=False,
            lifecycle_archive_execute=False,
            lifecycle_cleanup_execute=True,
        ),
        payload,
        report=object(),
        action_report=object(),
        active_goals=[],
        goal_replenishment=None,
        worker_reviews=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=plan.to_dict(),
        api=api,
    )

    assert executed == {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "skipped": True,
        "reason": "worktree delete blockers require attention",
        "count": 0,
        "blockers": 1,
    }
    assert api.deleted == []


def test_supervise_execution_uses_lifecycle_execution_plan() -> None:
    api = _StubExecutionApi()
    payload: dict[str, object] = {}

    executed = append_supervise_execution(
        argparse.Namespace(
            llm_execute=True,
            auto_execute=False,
            execute=False,
            merge_dispatch_execute=True,
        ),
        payload,
        report=object(),
        action_report=object(),
        active_goals=[],
        goal_replenishment=None,
        worker_reviews=None,
        fanout_status=None,
        fanout_paused=False,
        worker_role_guard=None,
        merge_dispatch=None,
        fanout_plan=None,
        lifecycle_execution=_merge_dispatch_plan(),
        api=api,
    )

    assert executed == {
        "kind": "launch_session",
        "display_kind": "merge_dispatch",
        "target_name": "supervisor-merge-dispatch",
        "source": "integration_review",
    }
    assert payload["executed"] == executed
    assert api.launched == [
        {
            "kind": "launch_session",
            "target_name": "supervisor-merge-dispatch",
            "source": "integration_review",
        }
    ]


def _decision(
    *,
    next_step: str,
    policy_status: str = "program_resolved",
    program_action: str | None = "dispatch_merge",
) -> dict[str, object]:
    return {
        "kind": "worker_lifecycle_decision",
        "action": program_action or "monitor",
        "stage": "ready_to_merge",
        "next_step": next_step,
        "policy": {
            "policy_status": policy_status,
            "program_action": program_action,
            "remaining_step": next_step,
            "blocked_reason": None,
        },
    }


def _merge_dispatch_plan() -> dict[str, object]:
    plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=_decision(next_step="launch_merge_worker"),
        merge_dispatch={
            "status": "ready_to_launch",
            "launch_spec": {
                "kind": "launch_session",
                "target_name": "supervisor-merge-dispatch",
                "source": "integration_review",
            },
        },
    )
    assert plan is not None
    return plan.to_dict()


class _StubActionApi:
    def _fanout_paused_action(self, fanout_status):
        raise AssertionError("fanout should not be used")

    def _fanout_llm_action(self, fanout_plan):
        raise AssertionError("fanout should not be used")

    def _recursive_worker_role_guard_action(self, worker_role_guard):
        raise AssertionError("worker role guard should not be used")

    def _loop_without_autonomous_scope(self, *args, **kwargs):
        return False

    def _decide_action_with_llm(self, *args, **kwargs):
        raise AssertionError("LLM should not be called for lifecycle execution")

    def _promote_llm_command_suggestion(self, payload):
        raise AssertionError("LLM promotion should not run")


class _StubPlanningApi:
    DEFAULT_FANOUT_LIMIT = 5

    def __init__(
        self,
        *,
        integration_review: dict[str, object] | None = None,
        cleanup_candidates: list[dict[str, object]] | None = None,
        delete_worktree_candidates: list[dict[str, object]] | None = None,
        delete_worktree_blockers: list[dict[str, object]] | None = None,
    ) -> None:
        self.integration_review = integration_review
        self.cleanup_candidates = cleanup_candidates or []
        self.delete_worktree_candidates = delete_worktree_candidates or []
        self.delete_worktree_blockers = delete_worktree_blockers or []

    def _current_batch_payload(self, *args, **kwargs):
        return {"target_names": []}

    def _fanout_candidate_active_goals(self, active_goals):
        return active_goals

    def _fanout_status_payload(self, *args, **kwargs):
        return None

    def _goal_replenishment_wrote_goals(self, goal_replenishment):
        return False

    def _recursive_worker_role_guard_payload(self, args):
        return None

    def _integration_merge_dispatch_payload(self, args):
        return None

    def _replenished_goal_plan_fanout_launch_plan(self, *args, **kwargs):
        return None

    def _active_goals_fanout_launch_plan(self, *args, **kwargs):
        return None

    def collect_integration_reviews(self, *args, **kwargs):
        return self.integration_review

    def _cleanup_candidate_dicts(self, codex_home):
        return self.cleanup_candidates

    def _delete_worktree_candidate_payloads(self, args):
        return self.delete_worktree_candidates

    def _delete_worktree_blocker_payloads(self, args):
        return self.delete_worktree_blockers


class _StubExecutionApi:
    def __init__(self) -> None:
        self.launched: list[dict[str, object]] = []
        self.archived: list[dict[str, object]] = []
        self.deleted: list[dict[str, object]] = []

    def _fanout_paused_executed(self, fanout_status):
        raise AssertionError("fanout should not be used")

    def _execute_fanout_launch_actions(self, *args, **kwargs):
        raise AssertionError("fanout should not be used")

    def _recursive_worker_role_guard_executed(self, worker_role_guard):
        raise AssertionError("worker role guard should not be used")

    def _execute_llm_action(self, *args, **kwargs):
        raise AssertionError("LLM action should not execute lifecycle plan")

    def _maybe_replan_after_context_request(self, *args, **kwargs):
        raise AssertionError("context replan should not run")

    def _execute_auto_action(self, *args, **kwargs):
        raise AssertionError("auto execution should not be used")

    def _auto_execute_action(self, *args, **kwargs):
        raise AssertionError("auto execution should not be used")

    def _execute_advice(self, *args, **kwargs):
        raise AssertionError("advice execution should not be used")

    def _execute_launch_action(self, args, action):
        self.launched.append(dict(action))
        return {
            "kind": "launch_session",
            "target_name": action["target_name"],
            "source": action["source"],
        }

    def _archive_cleanup_candidate(self, codex_home, candidate):
        del codex_home
        self.archived.append(dict(candidate))
        return {
            "kind": candidate["kind"],
            "name": candidate["name"],
            "record_id": candidate["record_id"],
            "archived": True,
        }

    def _execute_delete_worktree_action(self, args, action):
        del args
        self.deleted.append(dict(action))
        return {
            "kind": "delete_worktree",
            "target_name": action["target_name"],
            "record_id": action["record_id"],
            "deleted_worktree": f"/tmp/{action['target_name']}",
        }

    def _execute_failure_guarded_action(self, args, *, action, execute, **kwargs):
        del args, action, kwargs
        return execute()

    def _mark_merge_dispatch_execution(self, executed):
        executed = dict(executed)
        executed["display_kind"] = "merge_dispatch"
        return executed

    def _refresh_current_batch_after_execution(self, *args, **kwargs):
        return True
