"""Provider-shaped contract wrapper for future real planner adapters."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .loop_planner_adapter import run_agent_loop_planner_step


RAW_PROVIDER_FIELDS = {
    "api_key",
    "artifact_content",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_artifact_content",
    "raw_content",
    "raw_prompt",
    "raw_response",
}


def run_agent_loop_real_planner_contract_step(
    api: Any,
    run_id: str,
    provider_result: dict[str, Any],
) -> dict[str, Any]:
    """Accept a quarantined provider-shaped result, then run parsed symbolic output."""
    if not isinstance(provider_result, dict):
        raise ValueError("planner provider result must be a dict")
    _reject_raw_provider_payload(provider_result)

    provider_result_id = _required_string(provider_result, "provider_result_id")
    provider_status = _required_string(provider_result, "provider_status")
    if provider_status != "completed":
        raise ValueError("planner provider result must be completed before kernel execution")
    if provider_result.get("raw_prompt_quarantined") is not True:
        raise ValueError("raw planner provider payload must be quarantined before kernel execution")
    if provider_result.get("raw_response_quarantined") is not True:
        raise ValueError("raw planner provider payload must be quarantined before kernel execution")

    parsed_output = provider_result.get("parsed_planner_output")
    if not isinstance(parsed_output, dict):
        raise ValueError("parsed planner output must be a dict")

    planner_result = run_agent_loop_planner_step(api, run_id, deepcopy(parsed_output))
    return {
        "contract_status": "accepted",
        "provider_result_id": provider_result_id,
        "provider_status": provider_status,
        "raw_prompt_quarantined": True,
        "raw_response_quarantined": True,
        "planner_result": planner_result,
        "control": planner_result["control"],
    }


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _reject_raw_provider_payload(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = RAW_PROVIDER_FIELDS.intersection(value)
        if forbidden:
            raise ValueError("raw planner provider payload is not accepted by this contract")
        for nested in value.values():
            _reject_raw_provider_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_provider_payload(nested)
