"""Capability wrapper for Codex-assisted Isotope self-repair."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..features.supervisor.self_repair import launch_isotope_self_repair
from ..platform.schemas.input_contract import missing_required_input_keys


ISOTOPE_SELF_REPAIR_CAPABILITY = "isotope.self_repair"


def is_self_repair_capability(capability_id: str) -> bool:
    return capability_id == ISOTOPE_SELF_REPAIR_CAPABILITY


def validate_self_repair_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != ISOTOPE_SELF_REPAIR_CAPABILITY:
        return dict(inputs or {})
    input_mapping = inputs or {}
    for name in ("state_root", "cwd", "user_goal", "failure_summary"):
        if name in missing_inputs:
            continue
        if not isinstance(input_mapping.get(name), str):
            raise ValueError(f"{name} must be a string")
    for name in ("suggested_fix_summary", "target_name"):
        if name in input_mapping and not isinstance(input_mapping.get(name), str):
            raise ValueError(f"{name} must be a string")
    return dict(input_mapping)


def run_isotope_self_repair(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    required_inputs = ["state_root", "cwd", "user_goal", "failure_summary"]
    missing_inputs = missing_required_input_keys(inputs, required_inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_self_repair_inputs(
        capability_id=ISOTOPE_SELF_REPAIR_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    result = launch_isotope_self_repair(
        state_root=Path(input_mapping["state_root"]),
        cwd=Path(input_mapping["cwd"]),
        user_goal=input_mapping["user_goal"],
        failure_summary=input_mapping["failure_summary"],
        suggested_fix_summary=input_mapping.get("suggested_fix_summary", ""),
        target_name=input_mapping.get("target_name", "desktop-self-repair"),
    )
    return {
        "kind": "capability_run_result",
        "capability_id": ISOTOPE_SELF_REPAIR_CAPABILITY,
        "status": result.get("status", "launched"),
        "runner_kind": "codex_assisted_self_repair",
        "self_repair": result,
    }


__all__ = [
    "ISOTOPE_SELF_REPAIR_CAPABILITY",
    "is_self_repair_capability",
    "run_isotope_self_repair",
    "validate_self_repair_inputs",
]
