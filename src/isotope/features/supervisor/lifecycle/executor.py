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
    merge_dispatch: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "next_step": self.next_step,
            "status": self.status,
            "merge_dispatch": dict(self.merge_dispatch),
        }


def build_worker_lifecycle_execution_plan(
    *,
    worker_lifecycle_decision: Mapping[str, Any] | None,
    merge_dispatch: Mapping[str, Any] | None = None,
) -> WorkerLifecycleExecutionPlan | None:
    if not _is_program_resolved_lifecycle_decision(worker_lifecycle_decision):
        return None
    if worker_lifecycle_decision.get("next_step") != "launch_merge_worker":
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


def worker_lifecycle_execution_planned_executed(
    plan: Mapping[str, Any],
) -> dict[str, Any]:
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
    return (
        policy.get("policy_status") == "program_resolved"
        and policy.get("program_action") == "dispatch_merge"
    )


def _merge_dispatch(plan: Mapping[str, Any]) -> dict[str, Any] | None:
    merge_dispatch = plan.get("merge_dispatch")
    return dict(merge_dispatch) if isinstance(merge_dispatch, Mapping) else None
