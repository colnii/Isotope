"""Supervisor-specific deterministic capability runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..features.supervisor.capability_gaps import read_open_capability_gaps
from ..features.supervisor.notifications.context import request_project_context
from ..features.supervisor.registry import (
    adopt_codex_session,
    default_registry_path,
    read_managed_records,
    resume_managed_codex,
)
from ..features.supervisor.registry.records import ManagedCodexRecord
from ..features.supervisor.registry.session_matcher import (
    SessionMatchCandidate,
    match_codex_sessions_by_description,
)
from ..features.supervisor.workers.integration_review import (
    GROUPS as INTEGRATION_REVIEW_GROUPS,
    collect_integration_reviews,
)
from ..features.supervisor.workers.review import collect_worker_reviews
from ..platform.schemas.input_contract import missing_required_input_keys


SUPERVISOR_INTEGRATION_REVIEW_CAPABILITY = "supervisor.integration_review"
SUPERVISOR_CODEX_OPERATION_CAPABILITY = "supervisor.codex_operation"
SUPERVISOR_PROJECT_STATUS_CAPABILITY = "supervisor.project_status"
SUPERVISOR_REQUEST_CONTEXT_CAPABILITY = "supervisor.request_context"
SUPERVISOR_WORKER_REVIEW_CAPABILITY = "supervisor.worker_review"

SUPERVISOR_CODEX_OPERATIONS = (
    "request_context",
    "worker_review",
    "integration_review",
    "launch_worker",
    "resume_worker",
    "adopt_resume_by_description",
)

SUPERVISOR_STATE_ROOT_INPUT = "state_root"
LEGACY_SUPERVISOR_STATE_ROOT_INPUT = "codex_home"


def is_supervisor_projection_capability(capability_id: str) -> bool:
    return capability_id in {
        SUPERVISOR_CODEX_OPERATION_CAPABILITY,
        SUPERVISOR_INTEGRATION_REVIEW_CAPABILITY,
        SUPERVISOR_PROJECT_STATUS_CAPABILITY,
        SUPERVISOR_REQUEST_CONTEXT_CAPABILITY,
        SUPERVISOR_WORKER_REVIEW_CAPABILITY,
    }


def validate_supervisor_projection_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    inputs = normalize_supervisor_state_root_inputs(inputs)
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
    if capability_id == SUPERVISOR_PROJECT_STATUS_CAPABILITY:
        return _validate_supervisor_project_status_inputs(
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
    inputs = normalize_supervisor_state_root_inputs(inputs)
    required_inputs = ["operation", SUPERVISOR_STATE_ROOT_INPUT]
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
    elif operation == "adopt_resume_by_description":
        operation_result = run_supervisor_adopt_resume_by_description(
            inputs=operation_inputs,
        )
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


def run_supervisor_adopt_resume_by_description(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    inputs = normalize_supervisor_state_root_inputs(inputs)
    required_inputs = [SUPERVISOR_STATE_ROOT_INPUT, "description"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    state_root = _required_string(inputs, SUPERVISOR_STATE_ROOT_INPUT)
    description = _required_string(inputs, "description")
    prompt = _optional_string(inputs.get("prompt")) or (
        "继续推进用户描述匹配到的 Codex 会话，并按 Supervisor 协议汇报。"
    )
    target_name = _optional_string(inputs.get("target_name"))

    match = match_codex_sessions_by_description(
        codex_home=state_root,
        description=description,
    )
    if match.status != "clear" or match.selected is None:
        return {
            "kind": "capability_run_result",
            "capability_id": SUPERVISOR_CODEX_OPERATION_CAPABILITY,
            "status": match.status,
            "matched_session_id": None,
            "match": match.to_dict(),
            "candidates": [candidate.to_dict() for candidate in match.candidates],
        }

    selected = match.selected
    adopted = _adopted_record_for_session(
        codex_home=state_root,
        selected=selected,
        target_name=target_name,
    )
    resumed = resume_managed_codex(
        codex_home=state_root,
        cwd=selected.cwd,
        name=adopted.name,
        prompt=prompt,
        session_id=selected.session_id,
    )
    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_CODEX_OPERATION_CAPABILITY,
        "status": "resumed",
        "matched_session_id": selected.session_id,
        "match": match.to_dict(),
        "adopted": adopted.to_dict(),
        "resumed": resumed.to_dict(),
    }


def _adopted_record_for_session(
    *,
    codex_home: str,
    selected: SessionMatchCandidate,
    target_name: str | None,
) -> ManagedCodexRecord:
    records = read_managed_records(default_registry_path(codex_home))
    for record in reversed(records):
        if record.resume_session_id == selected.session_id:
            return record
    return adopt_codex_session(
        codex_home=codex_home,
        cwd=selected.cwd,
        name=target_name or _default_adopted_lane_name(selected),
        session_id=selected.session_id,
        prompt="按用户描述自动接管已有 Codex 会话",
    )


def _default_adopted_lane_name(selected: SessionMatchCandidate) -> str:
    return "resume-" + selected.session_id.split("-", 1)[0]


def run_supervisor_request_context(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    inputs = normalize_supervisor_state_root_inputs(inputs)
    required_inputs = [SUPERVISOR_STATE_ROOT_INPUT, "cwd", "query"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_request_context_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    result = request_project_context(
        codex_home=input_mapping[SUPERVISOR_STATE_ROOT_INPUT],
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
        "runner_kind": "deterministic_projection",
        "context_result": context_result,
    }


def run_supervisor_project_status(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    inputs = normalize_supervisor_state_root_inputs(inputs)
    required_inputs = [SUPERVISOR_STATE_ROOT_INPUT]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_project_status_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )

    from ..features.supervisor.desktop_snapshot import build_desktop_snapshot

    snapshot = build_desktop_snapshot(
        state_root=input_mapping[SUPERVISOR_STATE_ROOT_INPUT]
    )
    worker_review = collect_worker_reviews(
        codex_home=Path(input_mapping[SUPERVISOR_STATE_ROOT_INPUT]),
        lightweight=True,
    )
    self_repair_workers = _self_repair_workers_payload(worker_review)[:10]
    open_capability_gaps = read_open_capability_gaps(
        state_root=Path(input_mapping[SUPERVISOR_STATE_ROOT_INPUT]),
        limit=10,
    )
    summary = {
        "snapshot_id": snapshot.get("snapshotId"),
        "generated_at": snapshot.get("generatedAt"),
        "source": snapshot.get("source"),
        "active_goal": snapshot.get("activeGoal"),
        "active_agent": snapshot.get("activeAgent"),
        "counts": snapshot.get("counts", {}),
        "approvals": snapshot.get("approvals", [])[:10],
        "activities": snapshot.get("activities", [])[:20],
        "artifacts": snapshot.get("artifacts", [])[:10],
        "self_repair_workers": self_repair_workers,
        "latest_self_repair": _latest_self_repair_payload(self_repair_workers),
        "open_capability_gaps": open_capability_gaps,
    }
    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_PROJECT_STATUS_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_projection",
        "project_state": summary,
    }


def run_supervisor_integration_review(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    inputs = normalize_supervisor_state_root_inputs(inputs)
    required_inputs = [SUPERVISOR_STATE_ROOT_INPUT]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_integration_review_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = collect_integration_reviews(
        codex_home=Path(input_mapping[SUPERVISOR_STATE_ROOT_INPUT]),
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
        "runner_kind": "deterministic_projection",
        "integration_review": _integration_review_capability_payload(payload),
    }


def run_supervisor_worker_review(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    inputs = normalize_supervisor_state_root_inputs(inputs)
    required_inputs = [SUPERVISOR_STATE_ROOT_INPUT]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_worker_review_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = collect_worker_reviews(
        codex_home=Path(input_mapping[SUPERVISOR_STATE_ROOT_INPUT]),
        lightweight=True,
    )
    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_WORKER_REVIEW_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_projection",
        "worker_review": _worker_review_capability_payload(payload),
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _required_string(inputs: Mapping[str, Any], name: str) -> str:
    value = inputs.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalize_supervisor_state_root_inputs(
    inputs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    if LEGACY_SUPERVISOR_STATE_ROOT_INPUT not in input_mapping:
        return input_mapping
    legacy_value = input_mapping[LEGACY_SUPERVISOR_STATE_ROOT_INPUT]
    if (
        SUPERVISOR_STATE_ROOT_INPUT in input_mapping
        and input_mapping[SUPERVISOR_STATE_ROOT_INPUT] != legacy_value
    ):
        raise ValueError("state_root and codex_home must refer to the same directory")
    input_mapping[SUPERVISOR_STATE_ROOT_INPUT] = legacy_value
    input_mapping.pop(LEGACY_SUPERVISOR_STATE_ROOT_INPUT, None)
    return input_mapping


def _validate_supervisor_request_context_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in (SUPERVISOR_STATE_ROOT_INPUT, "cwd", "query"):
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


def _validate_supervisor_project_status_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    if SUPERVISOR_STATE_ROOT_INPUT not in missing_inputs and not isinstance(
        input_mapping.get(SUPERVISOR_STATE_ROOT_INPUT), str
    ):
        raise ValueError("state_root must be a string")
    return dict(input_mapping)


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
    if SUPERVISOR_STATE_ROOT_INPUT not in missing_inputs and not isinstance(
        input_mapping.get(SUPERVISOR_STATE_ROOT_INPUT), str
    ):
        raise ValueError("state_root must be a string")
    operation = input_mapping.get("operation")
    if operation == "request_context":
        return _validate_supervisor_request_context_inputs(
            inputs=input_mapping,
            missing_inputs=[
                name
                for name in (SUPERVISOR_STATE_ROOT_INPUT, "cwd", "query")
                if name not in input_mapping or input_mapping.get(name) in (None, "")
            ],
        )
    if operation == "worker_review":
        return _validate_supervisor_worker_review_inputs(
            inputs=input_mapping,
            missing_inputs=(
                [SUPERVISOR_STATE_ROOT_INPUT]
                if SUPERVISOR_STATE_ROOT_INPUT in missing_inputs
                else []
            ),
        )
    if operation == "integration_review":
        return _validate_supervisor_integration_review_inputs(
            inputs=input_mapping,
            missing_inputs=(
                [SUPERVISOR_STATE_ROOT_INPUT]
                if SUPERVISOR_STATE_ROOT_INPUT in missing_inputs
                else []
            ),
        )
    return dict(input_mapping)


def _validate_supervisor_worker_review_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    if SUPERVISOR_STATE_ROOT_INPUT not in missing_inputs and not isinstance(
        input_mapping.get(SUPERVISOR_STATE_ROOT_INPUT), str
    ):
        raise ValueError("state_root must be a string")
    return dict(input_mapping)


def _validate_supervisor_integration_review_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    if SUPERVISOR_STATE_ROOT_INPUT not in missing_inputs and not isinstance(
        input_mapping.get(SUPERVISOR_STATE_ROOT_INPUT), str
    ):
        raise ValueError("state_root must be a string")

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


def _self_repair_workers_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    workers = payload.get("workers")
    if not isinstance(workers, list):
        return []
    return [
        _worker_review_item_payload(worker)
        for worker in workers
        if isinstance(worker, Mapping) and worker.get("worker_role") == "self_repair"
    ]


def _latest_self_repair_payload(
    workers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not workers:
        return None
    latest = max(workers, key=lambda worker: str(worker.get("started_at") or ""))
    worktree = latest.get("worktree") if isinstance(latest.get("worktree"), Mapping) else {}
    protocol = (
        latest.get("supervisor_protocol")
        if isinstance(latest.get("supervisor_protocol"), Mapping)
        else {}
    )
    changes = latest.get("changes") if isinstance(latest.get("changes"), Mapping) else {}
    decision = (
        latest.get("next_decision")
        if isinstance(latest.get("next_decision"), Mapping)
        else {}
    )
    return {
        "record_id": latest.get("record_id"),
        "name": latest.get("name"),
        "worker_role": latest.get("worker_role"),
        "registry_status": latest.get("registry_status"),
        "started_at": latest.get("started_at"),
        "cwd": latest.get("cwd"),
        "cwd_exists": latest.get("cwd_exists"),
        "branch": worktree.get("branch") or worktree.get("inferred_branch"),
        "protocol_status": protocol.get("status"),
        "summary": protocol.get("summary"),
        "next": protocol.get("next"),
        "changes_status": changes.get("status"),
        "changes_summary": changes.get("summary"),
        "test_status": latest.get("test_status"),
        "test_passed": latest.get("test_passed"),
        "test_exit_code": latest.get("test_exit_code"),
        "recommendation": decision.get("recommendation"),
        "decision_summary": decision.get("summary"),
        "merge_suitable": decision.get("merge_suitable"),
        "continue_or_split_task": decision.get("continue_or_split_task"),
        "risk_level": decision.get("risk_level"),
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
        "worker_role": worker.get("worker_role"),
        "backend": worker.get("backend"),
        "registry_status": worker.get("registry_status"),
        "cwd": worker.get("cwd"),
        "cwd_exists": worker.get("cwd_exists"),
        "started_at": worker.get("started_at"),
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
