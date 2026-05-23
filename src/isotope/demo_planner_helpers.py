"""Planner validation helpers for developer demo scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime.in_process import InProcessServer


def _planner_decision_summaries(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "step": decision["step"],
            "action": decision["action"],
            "requested_capability": decision.get("requested_capability", decision["action"]),
            "reason": decision["reason"],
        }
        for decision in decisions
    ]


def _planner_io_validator_input(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "input_digest": "input_summary_hash",
        "available_capabilities": [
            "create_source_artifact",
            "submit_worker_handoff",
            "submit_approval_gated_action",
            "get_pending_approvals",
            "resolve_approval",
            "bind_workspace",
            "verify_replay_checkpoint",
        ],
        "deferred_capabilities": [
            "real_llm_plan",
            "scheduler",
            "provider_adapter",
            "filesystem_mutation",
            "memory_query",
        ],
        "retrieval_grants": {"artifact_summary": True, "artifact_full_text": False},
    }


def _planner_io_fixture(
    fixture_id: str,
    planner_output: object,
    planner_input: dict[str, Any],
) -> dict[str, Any]:
    result = _validate_planner_io_output(planner_output, planner_input)
    return {
        "fixture_id": fixture_id,
        "status": result["status"],
        "error_code": result["error_code"],
        "decision_count": result["decision_count"],
    }


def _fixture_rejected(fixtures: list[dict[str, Any]], fixture_id: str) -> bool:
    return any(
        fixture["fixture_id"] == fixture_id and fixture["status"] == "rejected"
        for fixture in fixtures
    )


def _validate_planner_io_output(
    planner_output: object,
    planner_input: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(planner_output, dict):
        return _planner_rejection("planner_output_malformed")
    if not _non_empty_string(planner_output.get("planner_run_id")):
        return _planner_rejection("planner_output_malformed")
    basis = planner_output.get("basis")
    if not isinstance(basis, dict):
        return _planner_rejection("planner_output_malformed")
    if basis.get("run_id") != planner_input.get("run_id"):
        return _planner_rejection("planner_basis_mismatch")
    if basis.get("input_digest") != planner_input.get("input_digest"):
        return _planner_rejection("planner_basis_mismatch")
    decisions = planner_output.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return _planner_rejection("planner_output_malformed")

    available_capabilities = set(planner_input.get("available_capabilities", []))
    allowed_actions = set(planner_input.get("available_capabilities", []))
    for decision in decisions:
        if not isinstance(decision, dict):
            return _planner_rejection("planner_output_malformed")
        if not isinstance(decision.get("step"), int):
            return _planner_rejection("planner_output_malformed")
        action = decision.get("action")
        if not _non_empty_string(action):
            return _planner_rejection("planner_output_malformed")
        if action not in allowed_actions:
            return _planner_rejection("unknown_planner_action")
        if not _non_empty_string(decision.get("reason")):
            return _planner_rejection("planner_output_malformed")
        intent = decision.get("intent", {})
        if intent is not None and not isinstance(intent, dict):
            return _planner_rejection("planner_output_malformed")
        if isinstance(intent, dict):
            if intent.get("read_artifact_full_text") is True:
                grants = planner_input.get("retrieval_grants", {})
                if not isinstance(grants, dict) or grants.get("artifact_full_text") is not True:
                    return _planner_rejection("artifact_full_content_not_granted")
            if any(
                intent.get(key) is True
                for key in (
                    "direct_append_event",
                    "write_checkpoint",
                    "mutate_artifact_store",
                    "private_server_state",
                )
            ):
                return _planner_rejection("planner_private_state_forbidden")
        requested_capability = decision.get("requested_capability", action)
        if requested_capability not in available_capabilities:
            return _planner_rejection("planner_capability_not_allowed")

    return {
        "status": "accepted",
        "error_code": "",
        "decision_count": len(decisions),
    }


def _planner_rejection(error_code: str) -> dict[str, Any]:
    return {"status": "rejected", "error_code": error_code, "decision_count": 0}


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _planner_happy_fixture_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": "happy_path",
        "status": "ok",
        "session_id": result["session_id"],
        "run_id": result["run_id"],
        "planner_adapter_status": result["planner_adapter_status"],
        "planner_decision_count": result["planner_decision_count"],
        "private_append_required": result["private_append_required"],
        "app_friction": list(result["app_friction"]),
        "replay_ok": result["replay_ok"],
        "checkpoint_ok": result["checkpoint_ok"],
        "event_count": result["event_count"],
    }


def _run_planner_blocked_deferred_fixture() -> dict[str, Any]:
    return {
        "fixture_id": "blocked_deferred_capability",
        "status": "blocked_deferred",
        "blocked_capability": "real_llm_plan",
        "reason": "real LLM planning is product/app-layer deferred and is not a core implementation request",
        "app_deferred_friction": [
            {
                "kind": "deferred_capability",
                "capability": "real_llm_plan",
                "classification": "app_or_product_deferred",
            }
        ],
        "app_friction": [],
        "partial_events_appended": False,
    }


def _run_planner_malformed_action_fixture(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="malformed planner action fixture")
    run_id = run["run_id"]
    before_count = len(api.get_events(run_id))
    unknown_action = "unknown_symbolic_action"
    status = "failed_closed"
    error_code = ""
    try:
        _validate_planner_symbolic_action(unknown_action)
    except ValueError as exc:
        error_code = "unknown_symbolic_action"
        error_message = str(exc)
    else:
        status = "unexpected_success"
        error_message = ""
    after_count = len(api.get_events(run_id))

    return {
        "fixture_id": "malformed_symbolic_action",
        "status": status,
        "unknown_action": unknown_action,
        "error_code": error_code,
        "error_summary": error_message,
        "events_before": before_count,
        "events_after": after_count,
        "partial_events_appended": after_count != before_count,
        "app_friction": [],
    }


def _validate_planner_symbolic_action(action: str) -> None:
    allowed = {
        "create_source_artifact",
        "submit_worker_handoff",
        "submit_approval_gated_action",
        "bind_workspace",
        "resolve_approval",
        "verify_replay_checkpoint",
    }
    if action not in allowed:
        raise ValueError(f"unknown planner symbolic action: {action}")
