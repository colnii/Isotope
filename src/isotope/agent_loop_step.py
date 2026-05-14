"""Product-facing Agent loop one-step driver."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import Any

from .refs import ResourceRef


def run_agent_loop_step(api: Any, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Run one currently available Agent loop step through public helpers."""
    if not isinstance(request, dict):
        raise ValueError("agent loop step request must be a dict")
    step = request.get("step")
    if not isinstance(step, str) or not step:
        raise ValueError("step must be a non-empty string")

    control = api.get_agent_loop_control(run_id)
    if step not in control["next_actions"]:
        raise ValueError(f"agent loop step {step} is not available in current phase {control['phase']}")

    action_result = _dispatch_step(api, run_id, step, request)
    updated_control = api.get_agent_loop_control(run_id)
    return {
        "step": step,
        "status": str(action_result.get("status", updated_control["status"])),
        "action_result": _public_action_result(action_result),
        "control": updated_control,
    }


def _dispatch_step(api: Any, run_id: str, step: str, request: dict[str, Any]) -> dict[str, Any]:
    if step == "create_source_artifact":
        return api.create_source_artifact(
            run_id,
            summary=_required_string(request, "summary"),
            content=_required_string(request, "content"),
        )
    if step == "submit_worker_handoff":
        return api.submit_worker_handoff(
            run_id,
            delegation_intent=_required_dict(request, "delegation_intent"),
            artifact_ref=_resource_ref_from_dict(_required_dict(request, "artifact_ref")),
            summary=_required_string(request, "summary"),
        )
    if step == "submit_approval_gated_action":
        return api.submit_action(
            run_id,
            deepcopy(_required_dict(request, "intent")),
            requires_approval=True,
        )
    if step == "get_approval":
        approval_id = _approval_id_from_request_or_control(request, api.get_agent_loop_control(run_id))
        return {
            "status": "ok",
            "approval": api.get_approval(run_id, approval_id),
        }
    if step == "resolve_approval":
        approval_id = _approval_id_from_request_or_control(request, api.get_agent_loop_control(run_id))
        return api.resolve_approval(
            approval_id,
            deepcopy(_required_dict(request, "resolution")),
        )
    raise ValueError(f"unsupported agent loop step: {step}")


def _approval_id_from_request_or_control(request: dict[str, Any], control: dict[str, Any]) -> str:
    approval_id = request.get("approval_id")
    if approval_id is None:
        pending_ids = control.get("approvals", {}).get("pending_ids", [])
        if isinstance(pending_ids, list) and len(pending_ids) == 1:
            approval_id = pending_ids[0]
    if not isinstance(approval_id, str) or not approval_id:
        raise ValueError("approval_id must be a non-empty string")
    return approval_id


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _required_dict(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = data.get(field_name)
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field_name} must be a non-empty dict")
    return value


def _resource_ref_from_dict(raw: dict[str, Any]) -> ResourceRef:
    return ResourceRef(
        ref_type=_required_string(raw, "ref_type"),
        scope=_required_string(raw, "scope"),
        run_id=_required_string(raw, "run_id"),
        artifact_id=_required_string(raw, "artifact_id"),
    )


def _public_action_result(value: Any) -> Any:
    if isinstance(value, ResourceRef):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {
            str(key): _public_action_result(nested)
            for key, nested in value.items()
            if key not in {"run_state", "decision", "execution"}
        }
    if isinstance(value, list):
        return [_public_action_result(item) for item in value]
    return value
