"""Program-owned worker lifecycle execution plans."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkerLifecycleExecutionPlan:
    kind: str
    source: str
    next_step: str
    status: str
    merge_dispatch: dict[str, Any] | None = None
    cleanup_candidates: tuple[dict[str, Any], ...] = ()
    delete_worktree_actions: tuple[dict[str, Any], ...] = ()
    delete_worktree_blockers: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "source": self.source,
            "next_step": self.next_step,
            "status": self.status,
        }
        if self.merge_dispatch is not None:
            payload["merge_dispatch"] = dict(self.merge_dispatch)
        if self.cleanup_candidates:
            payload["cleanup_candidates"] = [
                dict(candidate) for candidate in self.cleanup_candidates
            ]
        if self.delete_worktree_actions:
            payload["delete_worktree_actions"] = [
                dict(action) for action in self.delete_worktree_actions
            ]
        if self.delete_worktree_blockers:
            payload["delete_worktree_blockers"] = [
                dict(blocker) for blocker in self.delete_worktree_blockers
            ]
        return payload


def worker_lifecycle_execution_summary(
    plan: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    if not isinstance(plan, Mapping):
        return {
            "archivable": 0,
            "delete_ready": 0,
            "delete_blocked": 0,
            "result_actions": 0,
        }
    cleanup_candidates = plan.get("cleanup_candidates")
    delete_actions = plan.get("delete_worktree_actions")
    delete_blockers = plan.get("delete_worktree_blockers")
    return {
        "archivable": (
            len(cleanup_candidates) if isinstance(cleanup_candidates, list) else 0
        ),
        "delete_ready": len(delete_actions) if isinstance(delete_actions, list) else 0,
        "delete_blocked": len(delete_blockers) if isinstance(delete_blockers, list) else 0,
        "result_actions": _execution_result_action_count(result),
    }


def worker_lifecycle_execution_recommended_next_step(
    plan: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None = None,
) -> str:
    summary = worker_lifecycle_execution_summary(plan, result)
    if summary["result_actions"] > 0:
        return "monitor"
    if summary["delete_ready"] > 0:
        return "delete_ready"
    if summary["delete_blocked"] > 0:
        return "delete_blocked"
    if summary["archivable"] > 0:
        return "archive_ready"
    if isinstance(plan, Mapping) and plan.get("kind") == "merge_dispatch":
        if plan.get("status") == "ready_to_launch":
            return "merge_dispatch_ready"
        if plan.get("status") == "worker_already_running":
            return "monitor"
    return "monitor"


def build_worker_lifecycle_execution_plan(
    *,
    worker_lifecycle_decision: Mapping[str, Any] | None,
    merge_dispatch: Mapping[str, Any] | None = None,
    cleanup_candidates: list[dict[str, Any]] | None = None,
    delete_worktree_candidates: list[dict[str, Any]] | None = None,
    delete_worktree_blockers: list[dict[str, Any]] | None = None,
) -> WorkerLifecycleExecutionPlan | None:
    if not _is_program_resolved_lifecycle_decision(worker_lifecycle_decision):
        return None
    program_action = _program_action(worker_lifecycle_decision)
    if worker_lifecycle_decision.get("next_step") == "archive_worker":
        if program_action != "archive_integrated":
            return None
        return _archive_cleanup_plan(cleanup_candidates)
    if worker_lifecycle_decision.get("next_step") == "cleanup_worktree":
        if program_action != "archive_integrated":
            return None
        return _cleanup_worktree_plan(
            delete_worktree_candidates,
            delete_worktree_blockers=delete_worktree_blockers,
        )
    if worker_lifecycle_decision.get("next_step") != "launch_merge_worker":
        return None
    if program_action != "dispatch_merge":
        return None
    if not isinstance(merge_dispatch, Mapping):
        return None
    status = merge_dispatch.get("status")
    if status not in {"ready_to_launch", "worker_already_running"}:
        return None
    return WorkerLifecycleExecutionPlan(
        kind="merge_dispatch",
        source="worker_lifecycle",
        next_step="launch_merge_worker",
        status=str(status),
        merge_dispatch=dict(merge_dispatch),
    )


def worker_lifecycle_execution_action(plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("kind") == "archive_cleanup":
        candidates = _mapping_list(plan.get("cleanup_candidates"))
        first = candidates[0] if candidates else {}
        return {
            "kind": "archive_cleanup",
            "source": "worker_lifecycle",
            **_lifecycle_route_trace("archive_ready"),
            "count": len(candidates),
            "target_name": first.get("name"),
            "record_id": first.get("record_id"),
            "recommended_next_step": "archive_ready",
        }
    if plan.get("kind") == "cleanup_worktree":
        actions = _mapping_list(plan.get("delete_worktree_actions"))
        blockers = _mapping_list(plan.get("delete_worktree_blockers"))
        if blockers and not actions:
            return {
                "kind": "monitor",
                "source": "worker_lifecycle",
                **_lifecycle_route_trace("delete_blocked"),
                "reason": "worker lifecycle delete is blocked",
                "recommended_next_step": "delete_blocked",
                "blockers": len(blockers),
                "command_suggestion": None,
            }
        first = actions[0] if actions else {}
        return {
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            **_lifecycle_route_trace("delete_ready" if actions else "monitor"),
            "count": len(actions),
            "target_name": first.get("target_name"),
            "record_id": first.get("record_id"),
            "recommended_next_step": "delete_ready" if actions else "monitor",
        }
    merge_dispatch = _merge_dispatch(plan)
    if plan.get("kind") != "merge_dispatch" or merge_dispatch is None:
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": "worker lifecycle execution plan is not executable",
            "command_suggestion": None,
        }
    if plan.get("status") == "worker_already_running":
        action: dict[str, Any] = {
            "kind": "monitor",
            "reason": "merge worker already running",
        }
        running_worker = merge_dispatch.get("running_worker")
        if running_worker is not None:
            action["managed"] = running_worker
        return action
    launch_spec = merge_dispatch.get("launch_spec")
    if isinstance(launch_spec, Mapping):
        return dict(launch_spec)
    return {
        "kind": "monitor",
        "target_name": None,
        "reason": "worker lifecycle merge dispatch has no launch_spec",
        "command_suggestion": None,
    }


def _lifecycle_route_trace(recommended_next_step: str) -> dict[str, str]:
    return {
        "decision_source": "worker_lifecycle_execution",
        "routing_reason": (
            "program-owned lifecycle execution recommended "
            f"{recommended_next_step}"
        ),
    }


def worker_lifecycle_execution_planned_executed(
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    if plan.get("kind") == "archive_cleanup":
        return {
            "kind": "archive_cleanup",
            "source": "worker_lifecycle",
            "skipped": True,
            "reason": "lifecycle archive execution requires --lifecycle-archive-execute",
            "count": len(_mapping_list(plan.get("cleanup_candidates"))),
        }
    if plan.get("kind") == "cleanup_worktree":
        blockers = _mapping_list(plan.get("delete_worktree_blockers"))
        if blockers and not _mapping_list(plan.get("delete_worktree_actions")):
            return {
                "kind": "cleanup_worktree",
                "source": "worker_lifecycle",
                "skipped": True,
                "reason": "worktree delete blockers require attention",
                "count": 0,
                "blockers": len(blockers),
            }
        return {
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "skipped": True,
            "reason": "lifecycle cleanup execution requires --lifecycle-cleanup-execute",
            "count": len(_mapping_list(plan.get("delete_worktree_actions"))),
        }
    action = worker_lifecycle_execution_action(plan)
    if plan.get("status") == "worker_already_running":
        action["skipped"] = True
        return action
    return {
        "kind": "launch_session",
        "display_kind": "merge_dispatch",
        "source": "integration_review",
        "target_name": action.get("target_name"),
        "skipped": True,
        "reason": "merge dispatch launch adapter required",
    }


def worker_lifecycle_execution_launch_spec(
    plan: Mapping[str, Any],
) -> dict[str, Any] | None:
    merge_dispatch = _merge_dispatch(plan)
    if plan.get("kind") != "merge_dispatch" or merge_dispatch is None:
        return None
    launch_spec = merge_dispatch.get("launch_spec")
    return dict(launch_spec) if isinstance(launch_spec, Mapping) else None


def _is_program_resolved_lifecycle_decision(
    worker_lifecycle_decision: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(worker_lifecycle_decision, Mapping):
        return False
    policy = worker_lifecycle_decision.get("policy")
    if not isinstance(policy, Mapping):
        return False
    return policy.get("policy_status") == "program_resolved"


def _program_action(worker_lifecycle_decision: Mapping[str, Any]) -> Any:
    policy = worker_lifecycle_decision.get("policy")
    return policy.get("program_action") if isinstance(policy, Mapping) else None


def _merge_dispatch(plan: Mapping[str, Any]) -> dict[str, Any] | None:
    merge_dispatch = plan.get("merge_dispatch")
    return dict(merge_dispatch) if isinstance(merge_dispatch, Mapping) else None


def _archive_cleanup_plan(
    cleanup_candidates: list[dict[str, Any]] | None,
) -> WorkerLifecycleExecutionPlan | None:
    candidates = tuple(
        dict(candidate)
        for candidate in cleanup_candidates or []
        if candidate.get("kind") == "managed_worker"
        and isinstance(candidate.get("name"), str)
        and isinstance(candidate.get("record_id"), str)
    )
    if not candidates:
        return None
    return WorkerLifecycleExecutionPlan(
        kind="archive_cleanup",
        source="worker_lifecycle",
        next_step="archive_worker",
        status="ready_to_archive",
        cleanup_candidates=candidates,
    )


def _cleanup_worktree_plan(
    delete_worktree_candidates: list[dict[str, Any]] | None,
    *,
    delete_worktree_blockers: list[dict[str, Any]] | None = None,
) -> WorkerLifecycleExecutionPlan | None:
    actions = tuple(
        action
        for candidate in delete_worktree_candidates or []
        for action in (_delete_worktree_action(candidate),)
        if action is not None
    )
    blockers = tuple(dict(item) for item in delete_worktree_blockers or [])
    if not actions and not blockers:
        return None
    return WorkerLifecycleExecutionPlan(
        kind="cleanup_worktree",
        source="worker_lifecycle",
        next_step="cleanup_worktree",
        status="ready_to_delete" if actions else "blocked",
        delete_worktree_actions=actions,
        delete_worktree_blockers=blockers,
    )


def _delete_worktree_action(candidate: Mapping[str, Any]) -> dict[str, Any] | None:
    target_name = candidate.get("target_name") or candidate.get("name")
    record_id = candidate.get("record_id")
    if not isinstance(target_name, str) or not target_name:
        return None
    if not isinstance(record_id, str) or not record_id:
        return None
    if candidate.get("archived") is not True:
        return None
    if candidate.get("integration_group") != "already_integrated":
        return None
    base_ref = str(candidate.get("base_ref") or "main")
    return {
        "kind": "delete_worktree",
        "target_name": target_name,
        "record_id": record_id,
        "confirm_delete_worktree": True,
        "base_ref": base_ref,
        "source": "worker_lifecycle",
        "delete_evidence": _delete_worktree_evidence(candidate, base_ref=base_ref),
    }


def _delete_worktree_evidence(
    candidate: Mapping[str, Any],
    *,
    base_ref: str,
) -> dict[str, Any]:
    return {
        "archived": candidate.get("archived") is True,
        "supervisor_protocol_status": str(
            candidate.get("supervisor_protocol_status") or ""
        ),
        "supervisor_worktree": candidate.get("supervisor_worktree") is True,
        "integration_group": candidate.get("integration_group"),
        "main_contains_worker": candidate.get("main_contains_worker"),
        "main_has_worker_patch": candidate.get("main_has_worker_patch"),
        "dirty": candidate.get("dirty"),
        "base_ref": base_ref,
    }


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _execution_result_action_count(result: Mapping[str, Any] | None) -> int:
    if not isinstance(result, Mapping):
        return 0
    result_actions = result.get("result_actions")
    if isinstance(result_actions, list):
        return len([item for item in result_actions if isinstance(item, Mapping)])
    count = 0
    count += len(_mapping_list(result.get("deleted")))
    count += len(_mapping_list(result.get("archived")))
    if isinstance(result.get("managed"), Mapping):
        count += 1
    return count
