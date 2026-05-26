"""Screen-specific deterministic capability runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..features.screen.artifacts import report_screen_artifacts
from ..platform.schemas.input_contract import missing_required_input_keys


SCREEN_REPORT_CAPABILITY = "screen.report"


def is_screen_readonly_capability(capability_id: str) -> bool:
    return capability_id == SCREEN_REPORT_CAPABILITY


def validate_screen_readonly_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != SCREEN_REPORT_CAPABILITY:
        return dict(inputs or {})
    return _validate_screen_report_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )


def run_screen_report(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "run_id"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_screen_report_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = report_screen_artifacts(
        Path(input_mapping["root"]).expanduser(),
        run_id=input_mapping["run_id"],
    )
    return {
        "kind": "capability_run_result",
        "capability_id": SCREEN_REPORT_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "screen_report": payload,
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_screen_report_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in ("root", "run_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    return dict(input_mapping)
