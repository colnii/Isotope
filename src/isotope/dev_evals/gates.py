from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import CapabilityScenario


def evaluate_required_capacity_called(
    scenario: CapabilityScenario,
    steps: list[Mapping[str, Any]],
) -> dict[str, Any]:
    called = [str(step.get("capacity_id")) for step in steps if step.get("capacity_id")]
    missing = [item for item in scenario.capability_ids if item not in called]
    return {
        "gate": "required_capacity_called",
        "passed": not missing,
        "details": {
            "expected_capacity_ids": list(scenario.capability_ids),
            "called_capacity_ids": called,
            "missing_capacity_ids": missing,
        },
    }


def evaluate_result_status(
    scenario: CapabilityScenario,
    steps: list[Mapping[str, Any]],
) -> dict[str, Any]:
    bad_steps = [
        {"capacity_id": step.get("capacity_id"), "status": step.get("status")}
        for step in steps
        if step.get("capacity_id") in scenario.capability_ids
        and step.get("status") not in scenario.allowed_result_statuses
    ]
    return {
        "gate": "result_status_allowed",
        "passed": not bad_steps,
        "details": {
            "allowed_result_statuses": list(scenario.allowed_result_statuses),
            "bad_steps": bad_steps,
        },
    }


def low_sensitive_report_passed(value: Any) -> bool:
    rendered = repr(value).lower()
    forbidden = (
        "api_key",
        "must_not_leak",
        "prompt_should_not_leak",
        "secret",
        "should_not_leak",
        "token",
        "transcript_should_not_leak",
    )
    return not any(item in rendered for item in forbidden)
