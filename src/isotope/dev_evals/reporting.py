from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .gates import (
    evaluate_required_input_fragments,
    evaluate_required_capacity_called,
    evaluate_result_status,
    low_sensitive_report_passed,
)
from .models import CapabilityScenario


SENSITIVE_KEYS = {
    "api_key",
    "messages",
    "raw_prompt",
    "raw_response",
    "secret",
    "token",
    "transcript",
}


def sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]"
            if str(key).lower() in SENSITIVE_KEYS
            else sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    return value


def build_case_report(
    scenario: CapabilityScenario,
    *,
    steps: list[dict[str, Any]],
    final_answer: str | None = None,
    reviewer_prompt_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sanitized_steps = sanitize_value(steps)
    hard_gates = [
        evaluate_required_capacity_called(scenario, sanitized_steps),
        evaluate_result_status(scenario, sanitized_steps),
    ]
    if scenario.required_input_fragments:
        hard_gates.append(evaluate_required_input_fragments(scenario, sanitized_steps))
    hard_gates.append(
        {
            "gate": "low_sensitive_report",
            "passed": low_sensitive_report_passed(sanitized_steps),
            "details": {},
        }
    )
    hard_gate_passed = all(gate["passed"] for gate in hard_gates)
    input_gate_passed = all(
        gate["passed"]
        for gate in hard_gates
        if gate["gate"] == "required_input_fragments"
    )
    return {
        "case_id": scenario.case_id,
        "capability_under_test": list(scenario.capability_ids),
        "status": "passed" if hard_gate_passed else "failed",
        "hard_gate_passed": hard_gate_passed,
        "hard_gates": hard_gates,
        "steps": sanitized_steps,
        "scores": {
            "capacity_choice": 4 if hard_gates[0]["passed"] else 1,
            "input_quality": 4 if input_gate_passed else 1,
            "result_grounding": 4 if hard_gate_passed else 1,
            "self_review_quality": 0,
        },
        "final_answer": final_answer or "",
        "reviewer_prompt_ref": reviewer_prompt_ref,
        "regression_risks": [] if hard_gate_passed else ["hard_gate_failed"],
        "recommendation": "No immediate fix required."
        if hard_gate_passed
        else "Review failed hard gates before continuing.",
    }


def build_case_execution_failure_report(
    scenario: CapabilityScenario,
    *,
    reason_code: str,
    message: str,
) -> dict[str, Any]:
    hard_gates = [
        {
            "gate": "case_execution_completed",
            "passed": False,
            "details": {
                "reason_code": reason_code,
                "message": message,
            },
        }
    ]
    return {
        "case_id": scenario.case_id,
        "capability_under_test": list(scenario.capability_ids),
        "status": "failed",
        "hard_gate_passed": False,
        "hard_gates": hard_gates,
        "steps": [],
        "scores": {
            "capacity_choice": 0,
            "input_quality": 0,
            "result_grounding": 0,
            "self_review_quality": 0,
        },
        "final_answer": "",
        "reviewer_prompt_ref": None,
        "reviewer_status": "not_generated",
        "failure": {
            "reason_code": reason_code,
            "message": message,
        },
        "regression_risks": [reason_code],
        "recommendation": "Resolve the live eval failure before claiming this gate passed.",
    }


def build_suite_report(
    *,
    suite: str,
    cases: list[dict[str, Any]],
    execution_mode: str | None = None,
) -> dict[str, Any]:
    hard_gate_passed = all(case.get("hard_gate_passed") is True for case in cases)
    report = {
        "kind": "supervisor_capacity_dev_eval_report",
        "suite": suite,
        "status": "passed" if hard_gate_passed else "failed",
        "hard_gate_passed": hard_gate_passed,
        "cases": cases,
    }
    if execution_mode:
        report["execution_mode"] = execution_mode
        report["gate_scope"] = (
            "live" if execution_mode == "live" else "deterministic_fallback"
        )
    return report
