"""Planner-output adapter for the Agent loop step driver."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


RAW_PLANNER_FIELDS = {
    "artifact_content",
    "full_content",
    "full_text",
    "model_prompt",
    "model_response",
    "raw_artifact_content",
    "raw_content",
}


def run_agent_loop_planner_step(api: Any, run_id: str, planner_output: dict[str, Any]) -> dict[str, Any]:
    """Validate one symbolic planner decision, then execute it via the step driver."""
    if not isinstance(planner_output, dict):
        raise ValueError("planner output must be a dict")
    _reject_raw_planner_payload(planner_output)

    planner_run_id = _required_string(planner_output, "planner_run_id")
    control = api.get_agent_loop_control(run_id)
    _validate_basis(planner_output.get("basis"), control)

    decision = planner_output.get("decision")
    if not isinstance(decision, dict):
        raise ValueError("planner decision must be a dict")
    step = _required_string(decision, "step")
    if step not in control["next_actions"]:
        raise ValueError(f"planner selected step {step} is not available in current phase {control['phase']}")

    request = decision.get("request", {})
    if not isinstance(request, dict):
        raise ValueError("planner decision request must be a dict")
    request = deepcopy(request)
    requested_step = request.get("step")
    if requested_step is not None and requested_step != step:
        raise ValueError("planner decision step does not match request step")
    request["step"] = step

    step_result = api.run_agent_loop_step(run_id, request)
    return {
        "planner_run_id": planner_run_id,
        "planner_status": "accepted",
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "selected_step": step,
        "step_result": step_result,
        "control": step_result["control"],
    }


def _validate_basis(raw_basis: object, control: dict[str, Any]) -> None:
    if not isinstance(raw_basis, dict):
        raise ValueError("planner basis must be a dict")
    if raw_basis.get("run_id") != control["run_id"]:
        raise ValueError("planner basis run_id does not match current run")
    if raw_basis.get("last_event_id") != control["last_event_id"]:
        raise ValueError("planner basis last_event_id is stale")


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _reject_raw_planner_payload(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = RAW_PLANNER_FIELDS.intersection(value)
        if forbidden:
            raise ValueError("raw planner payload is not accepted by this adapter")
        for nested in value.values():
            _reject_raw_planner_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_planner_payload(nested)
