"""Supervisor-specific deterministic capability runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..features.supervisor.notifications.context import request_project_context
from ..features.supervisor.workers.integration_review import (
    GROUPS as INTEGRATION_REVIEW_GROUPS,
    collect_integration_reviews,
)
from ..features.supervisor.workers.review import collect_worker_reviews
from ..platform.schemas.input_contract import missing_required_input_keys


SUPERVISOR_INTEGRATION_REVIEW_CAPABILITY = "supervisor.integration_review"
SUPERVISOR_CODEX_OPERATION_CAPABILITY = "supervisor.codex_operation"
SUPERVISOR_REQUEST_CONTEXT_CAPABILITY = "supervisor.request_context"
SUPERVISOR_WORKER_REVIEW_CAPABILITY = "supervisor.worker_review"

SUPERVISOR_CODEX_OPERATIONS = (
    "request_context",
    "worker_review",
    "integration_review",
    "launch_worker",
    "resume_worker",
)


def is_supervisor_readonly_capability(capability_id: str) -> bool:
    return capability_id in {
        SUPERVISOR_CODEX_OPERATION_CAPABILITY,
        SUPERVISOR_INTEGRATION_REVIEW_CAPABILITY,
        SUPERVISOR_REQUEST_CONTEXT_CAPABILITY,
        SUPERVISOR_WORKER_REVIEW_CAPABILITY,
    }


def validate_supervisor_readonly_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id == SUPERVISOR_REQUEST_CONTEXT_CAPABILITY:
        return _validate_supervisor_request_context_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == SUPERVISOR_CODEX_OPERATION_CAPABILITY:
        return _validate_supervisor_codex_operation_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == SUPERVISOR_INTEGRATION_REVIEW_CAPABILITY:
        return _validate_supervisor_integration_review_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == SUPERVISOR_WORKER_REVIEW_CAPABILITY:
        return _validate_supervisor_worker_review_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    return dict(inputs or {})


def run_supervisor_codex_operation(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    required_inputs = ["operation", "codex_home"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_codex_operation_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    operation = input_mapping["operation"]
    operation_inputs = dict(input_mapping)
    operation_inputs.pop("operation", None)

    if operation == "request_context":
        operation_result = run_supervisor_request_context(inputs=operation_inputs)
    elif operation == "worker_review":
        operation_result = run_supervisor_worker_review(inputs=operation_inputs)
    elif operation == "integration_review":
        operation_result = run_supervisor_integration_review(inputs=operation_inputs)
    else:
        operation_result = {
            "kind": "capability_run_result",
            "capability_id": SUPERVISOR_CODEX_OPERATION_CAPABILITY,
            "status": "skipped",
            "reason": "operation requires Supervisor runtime wrapper",
            "operation": operation,
        }

    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_CODEX_OPERATION_CAPABILITY,
        "status": operation_result.get("status", "completed"),
        "runner_kind": "supervisor_codex_operation",
        "operation": operation,
        "operation_result": operation_result,
    }


def run_supervisor_request_context(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    required_inputs = ["codex_home", "cwd", "query"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_request_context_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    result = request_project_context(
        codex_home=input_mapping["codex_home"],
        cwd=input_mapping["cwd"],
        query=input_mapping["query"],
        max_results=input_mapping["max_results"],
    )
    result_dict = result.to_dict()
    context_result = dict(result_dict)
    context_result["item_count"] = len(result_dict["items"])
    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_REQUEST_CONTEXT_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "context_result": context_result,
    }


def run_supervisor_integration_review(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    required_inputs = ["codex_home"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_integration_review_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = collect_integration_reviews(
        codex_home=Path(input_mapping["codex_home"]),
        base_ref=input_mapping["base_ref"],
        include_unfinished=input_mapping["include_unfinished"],
        include_missing_worktrees=input_mapping["include_missing_worktrees"],
        run_test_gate=input_mapping["run_test_gate"],
        run_candidate_validation=input_mapping["run_candidate_validation"],
    )
    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_INTEGRATION_REVIEW_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "integration_review": _integration_review_capability_payload(payload),
    }


def run_supervisor_worker_review(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    required_inputs = ["codex_home"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_worker_review_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = collect_worker_reviews(
        codex_home=Path(input_mapping["codex_home"]),
        lightweight=True,
    )
    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_WORKER_REVIEW_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "worker_review": _worker_review_capability_payload(payload),
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_supervisor_request_context_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in ("codex_home", "cwd", "query"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")

    max_results = input_mapping.get("max_results", 5)
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise ValueError("max_results must be a positive integer")
    if max_results <= 0:
        raise ValueError("max_results must be a positive integer")

    normalized = dict(input_mapping)
    normalized["max_results"] = max_results
    return normalized


def _validate_supervisor_codex_operation_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    if "operation" not in missing_inputs:
        operation = input_mapping.get("operation")
        if operation not in SUPERVISOR_CODEX_OPERATIONS:
            supported = ", ".join(SUPERVISOR_CODEX_OPERATIONS)
            raise ValueError(f"operation must be one of: {supported}")
    if "codex_home" not in missing_inputs and not isinstance(
        input_mapping.get("codex_home"), str
    ):
        raise ValueError("codex_home must be a string")
    operation = input_mapping.get("operation")
    if operation == "request_context":
        return _validate_supervisor_request_context_inputs(
            inputs=input_mapping,
            missing_inputs=[
                name
                for name in ("codex_home", "cwd", "query")
                if name not in input_mapping or input_mapping.get(name) in (None, "")
            ],
        )
    if operation == "worker_review":
        return _validate_supervisor_worker_review_inputs(
            inputs=input_mapping,
            missing_inputs=["codex_home"] if "codex_home" in missing_inputs else [],
        )
    if operation == "integration_review":
        return _validate_supervisor_integration_review_inputs(
            inputs=input_mapping,
            missing_inputs=["codex_home"] if "codex_home" in missing_inputs else [],
        )
    return dict(input_mapping)


def _validate_supervisor_worker_review_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    if "codex_home" not in missing_inputs and not isinstance(
        input_mapping.get("codex_home"), str
    ):
        raise ValueError("codex_home must be a string")
    return dict(input_mapping)


def _validate_supervisor_integration_review_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    if "codex_home" not in missing_inputs and not isinstance(
        input_mapping.get("codex_home"), str
    ):
        raise ValueError("codex_home must be a string")

    base_ref = input_mapping.get("base_ref", "main")
    if not isinstance(base_ref, str) or not base_ref.strip():
        raise ValueError("base_ref must be a string")

    normalized = dict(input_mapping)
    normalized["base_ref"] = base_ref
    for name in (
        "include_unfinished",
        "include_missing_worktrees",
        "run_test_gate",
        "run_candidate_validation",
    ):
        normalized[name] = _bool_input(input_mapping, name, default=False)
    return normalized


def _bool_input(
    input_mapping: Mapping[str, Any],
    name: str,
    *,
    default: bool,
) -> bool:
    value = input_mapping.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _worker_review_capability_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "summary": dict(payload.get("summary") or {}),
        "decision_summary": dict(payload.get("decision_summary") or {}),
        "automation_candidates": _worker_review_candidates_payload(
            payload.get("automation_candidates")
        ),
        "workers": [
            _worker_review_item_payload(worker)
            for worker in payload.get("workers", [])
            if isinstance(worker, Mapping)
        ],
        "safety": _worker_review_safety_payload(payload.get("safety")),
    }


def _worker_review_candidates_payload(raw: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for bucket in (
        "review_then_merge",
        "continue_or_split",
        "archive_or_wait",
        "recover_or_archive",
    ):
        items = raw.get(bucket)
        if not isinstance(items, list):
            continue
        result[bucket] = [
            _worker_review_candidate_payload(item)
            for item in items
            if isinstance(item, Mapping)
        ]
    return result


def _worker_review_candidate_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "record_id": item.get("record_id"),
        "name": item.get("name"),
        "cwd": item.get("cwd"),
        "branch": item.get("branch"),
        "recommendation": item.get("recommendation"),
        "risk_level": item.get("risk_level"),
        "reason": item.get("reason"),
    }


def _worker_review_item_payload(worker: Mapping[str, Any]) -> dict[str, Any]:
    worktree = worker.get("worktree") if isinstance(worker.get("worktree"), Mapping) else {}
    protocol = (
        worker.get("supervisor_protocol")
        if isinstance(worker.get("supervisor_protocol"), Mapping)
        else {}
    )
    changes = worker.get("changes") if isinstance(worker.get("changes"), Mapping) else {}
    decision = (
        worker.get("next_decision")
        if isinstance(worker.get("next_decision"), Mapping)
        else {}
    )
    return {
        "record_id": worker.get("record_id"),
        "name": worker.get("name"),
        "backend": worker.get("backend"),
        "registry_status": worker.get("registry_status"),
        "cwd": worker.get("cwd"),
        "cwd_exists": worker.get("cwd_exists"),
        "worktree": {
            "exists": worktree.get("exists"),
            "branch": worktree.get("branch"),
            "inferred_branch": worktree.get("inferred_branch"),
        },
        "supervisor_protocol": {
            "status": protocol.get("status"),
            "summary": protocol.get("summary"),
            "next": protocol.get("next"),
        },
        "changes": {
            "status": changes.get("status"),
            "summary": changes.get("summary"),
        },
        "test_status": worker.get("test_status"),
        "test_passed": worker.get("test_passed"),
        "test_exit_code": worker.get("test_exit_code"),
        "next_decision": {
            "recommendation": decision.get("recommendation"),
            "summary": decision.get("summary"),
            "merge_suitable": decision.get("merge_suitable"),
            "continue_or_split_task": decision.get("continue_or_split_task"),
            "risk_level": decision.get("risk_level"),
        },
    }


def _worker_review_safety_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    return {
        "auto_merge": raw.get("auto_merge"),
        "delete_branch": raw.get("delete_branch"),
        "note": raw.get("note"),
    }


def _integration_review_capability_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_groups = payload.get("groups") if isinstance(payload.get("groups"), Mapping) else {}
    return {
        "status": payload.get("status"),
        "base_ref": payload.get("base_ref"),
        "include_unfinished": payload.get("include_unfinished"),
        "include_missing_worktrees": payload.get("include_missing_worktrees"),
        "summary": dict(payload.get("summary") or {}),
        "stale_missing_worktrees": [
            _integration_missing_worktree_payload(item)
            for item in payload.get("stale_missing_worktrees", [])
            if isinstance(item, Mapping)
        ],
        "groups": {
            group: [
                _integration_review_item_payload(item)
                for item in raw_groups.get(group, [])
                if isinstance(item, Mapping)
            ]
            for group in INTEGRATION_REVIEW_GROUPS
        },
        "workers": [
            _integration_review_item_payload(worker)
            for worker in payload.get("workers", [])
            if isinstance(worker, Mapping)
        ],
        "safety": _integration_review_safety_payload(payload.get("safety")),
    }


def _integration_missing_worktree_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "record_id": item.get("record_id"),
        "name": item.get("name"),
        "cwd": item.get("cwd"),
        "branch": item.get("branch"),
        "status": item.get("status"),
    }


def _integration_review_item_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    protocol = (
        item.get("supervisor_protocol")
        if isinstance(item.get("supervisor_protocol"), Mapping)
        else {}
    )
    merge_check = (
        item.get("merge_check") if isinstance(item.get("merge_check"), Mapping) else {}
    )
    validation = (
        item.get("validation") if isinstance(item.get("validation"), Mapping) else {}
    )
    dirty_paths = item.get("dirty_paths")
    dirty_path_count = len(dirty_paths) if isinstance(dirty_paths, list) else 0
    return {
        "record_id": item.get("record_id"),
        "name": item.get("name"),
        "cwd": item.get("cwd"),
        "cwd_exists": item.get("cwd_exists"),
        "branch": item.get("branch"),
        "worker_commit": item.get("worker_commit"),
        "base_ref": item.get("base_ref"),
        "base_commit": item.get("base_commit"),
        "main_contains_worker": item.get("main_contains_worker"),
        "main_has_worker_patch": item.get("main_has_worker_patch"),
        "worker_contains_main": item.get("worker_contains_main"),
        "dirty": item.get("dirty"),
        "dirty_path_count": dirty_path_count,
        "test_status": item.get("test_status"),
        "test_passed": item.get("test_passed"),
        "test_exit_code": item.get("test_exit_code"),
        "supervisor_protocol": {
            "status": protocol.get("status"),
            "summary": protocol.get("summary"),
            "next": protocol.get("next"),
        },
        "merge_worker": item.get("merge_worker"),
        "merge_worker_source": item.get("merge_worker_source"),
        "merge_conflict": item.get("merge_conflict"),
        "merge_check": {
            "available": merge_check.get("available"),
            "conflict": merge_check.get("conflict"),
            "returncode": merge_check.get("returncode"),
        },
        "validation": {
            "status": validation.get("status"),
        },
        "group": item.get("group"),
        "reason": item.get("reason"),
        "reasons": list(item.get("reasons") or []),
    }


def _integration_review_safety_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    return {
        "auto_merge": raw.get("auto_merge"),
        "push": raw.get("push"),
        "delete_branch": raw.get("delete_branch"),
        "note": raw.get("note"),
    }
