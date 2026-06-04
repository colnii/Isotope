"""Product-facing Agent loop one-step driver."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any

from .loop_engine import LoopEngine, LoopStepContext
from ...platform.ids import new_id
from ...platform.schemas.input_contract import contract_properties
from ...platform.schemas.refs import ResourceRef


def run_agent_loop_step(api: Any, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Run one currently available Agent loop step through public helpers."""
    engine = LoopEngine(
        get_control=api.get_agent_loop_control,
        step_handlers=_agent_loop_step_handlers(api),
        interrupt_policy=_agent_loop_interrupt_policy,
    )
    return engine.run_step(run_id, request)


def _agent_loop_step_handlers(api: Any):
    return {
        "create_source_artifact": lambda context: _public_action_result(
            api.create_source_artifact(
                context.run_id,
                summary=_required_string(context.request, "summary"),
                content=_required_string(context.request, "content"),
            )
        ),
        "submit_worker_handoff": lambda context: _public_action_result(
            api.submit_worker_handoff(
                context.run_id,
                delegation_intent=_required_dict(context.request, "delegation_intent"),
                artifact_ref=_resource_ref_from_dict(_required_dict(context.request, "artifact_ref")),
                summary=_required_string(context.request, "summary"),
            )
        ),
        "submit_approval_gated_action": lambda context: _public_action_result(
            api.submit_action(
                context.run_id,
                deepcopy(_required_dict(context.request, "intent")),
                requires_approval=True,
            )
        ),
        "record_turn_memory": lambda context: _public_action_result(
            api.record_agent_loop_turn_memory(context.run_id, context.request)
        ),
        "promote_run_memory": lambda context: _public_action_result(
            api.promote_agent_loop_run_memory(context.run_id, context.request)
        ),
        "query_memory": lambda context: _public_action_result(
            api.query_agent_loop_memory(context.run_id, context.request)
        ),
        "call_capability": lambda context: _public_action_result(
            _call_capability_step(api, context.run_id, context.request)
        ),
        "get_approval": lambda context: _public_action_result(
            {
                "status": "ok",
                "approval": api.get_approval(
                    context.run_id,
                    _approval_id_from_request_or_control(context.request, context.control),
                ),
            }
        ),
        "resolve_approval": lambda context: _public_action_result(
            api.resolve_approval(
                _approval_id_from_request_or_control(context.request, context.control),
                deepcopy(_required_dict(context.request, "resolution")),
            )
        ),
    }


def _agent_loop_interrupt_policy(context: LoopStepContext) -> str | None:
    if context.step in context.control["next_actions"]:
        return None
    raise ValueError(
        f"agent loop step {context.step} is not available in current phase {context.control['phase']}"
    )


def _call_capability_step(api: Any, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
    from ...capabilities.runner import CapabilityRunner

    capability_id = _required_string(request, "capability_id")
    runner = CapabilityRunner()
    inputs = _capability_inputs_for_agent_loop(
        runner=runner,
        capability_id=capability_id,
        run_id=run_id,
        request=request,
    )
    capability_run = runner.run_capability(
        capability_id,
        root_path=_capability_run_root(api, run_id, capability_id),
        inputs=inputs,
    )
    artifact_result = api.create_source_artifact(
        run_id,
        summary=f"Capability {capability_id} completed",
        content=json.dumps(
            {
                "kind": "agent_loop_capability_call",
                "capability_run": capability_run,
            },
            sort_keys=True,
        ),
    )
    return {
        "status": capability_run["status"],
        "capability_run": capability_run,
        "artifact_ref": artifact_result["artifact_ref"],
        "artifact_summary": artifact_result["artifact_summary"],
        "proposal_id": artifact_result["proposal_id"],
        "decision_id": artifact_result["decision_id"],
        "execution_id": artifact_result["execution_id"],
    }


def _capability_inputs_for_agent_loop(
    *,
    runner: Any,
    capability_id: str,
    run_id: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    inputs = _optional_dict(request, "inputs") or {}
    capability = runner.describe_capability(capability_id)
    properties = contract_properties(capability.get("input_contract", {}))
    system_inputs: dict[str, str] = {}
    if "run_id" in properties:
        system_inputs["run_id"] = run_id
    if "execution_id" in properties:
        system_inputs["execution_id"] = new_id("exec")
    return {**system_inputs, **inputs}


def _capability_run_root(api: Any, run_id: str, capability_id: str) -> Path:
    root = getattr(api, "root", None)
    if root is None:
        return Path.cwd() / ".isotope-capability-runs" / run_id / _path_segment(capability_id)
    return Path(root) / "capability-runs" / run_id / _path_segment(capability_id)


def _path_segment(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)


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


def _optional_dict(data: dict[str, Any], field_name: str) -> dict[str, Any] | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return deepcopy(value)


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
