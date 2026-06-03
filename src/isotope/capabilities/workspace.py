"""Workspace capability proposals for native coding.

The first isolated writable workspace slice is proposal-only. It fixes the
path-safety and low-sensitive contract for a future materialized workspace, but
does not create directories, copy files, mutate repositories, or append events.
"""

from __future__ import annotations

from pathlib import PurePosixPath, Path
import re
from typing import Any, Mapping


WORKSPACE_ISOLATED_RW_CAPABILITY = "workspace.isolated_rw"
WORKSPACE_LEASE_CREATE_CAPABILITY = "workspace.lease_create"
WORKSPACE_CAPABILITIES = {
    WORKSPACE_ISOLATED_RW_CAPABILITY,
    WORKSPACE_LEASE_CREATE_CAPABILITY,
}

_ARRAY_INPUTS = ("allowed_paths", "forbidden_paths")
_NEXT_REQUIRED_CAPABILITIES = [
    "workspace.lease_create",
    "workspace.materialize",
    "workspace.changed_files",
    "workspace.release",
]
_WORKSPACE_ID_RE = re.compile(r"[^a-z0-9]+")


def is_workspace_capability(capability_id: str) -> bool:
    return capability_id in WORKSPACE_CAPABILITIES


def validate_workspace_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if not is_workspace_capability(capability_id):
        return dict(inputs or {})
    if capability_id == WORKSPACE_LEASE_CREATE_CAPABILITY:
        return _validate_lease_create_inputs(inputs=inputs, missing_inputs=missing_inputs)
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "workspace_name"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    for name in _ARRAY_INPUTS:
        input_mapping[name] = _safe_relative_paths(input_mapping.get(name, []), name)
    return input_mapping


def run_workspace_isolated_rw(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    missing_inputs = _missing_required(inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_workspace_inputs(
        capability_id=WORKSPACE_ISOLATED_RW_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    workspace_id = _workspace_id(input_mapping["workspace_name"])
    cwd = Path(input_mapping["cwd"]).expanduser()
    return {
        "kind": "capability_run_result",
        "capability_id": WORKSPACE_ISOLATED_RW_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_proposal",
        "workspace_proposal": {
            "workspace_id": workspace_id,
            "mode": "isolated_rw",
            "execution_mode": "proposal_only",
            "cwd_status": "exists" if cwd.exists() else "missing",
            "root_ref": f"workspace://{workspace_id}/isolated_rw",
            "allowed_paths": list(input_mapping["allowed_paths"]),
            "forbidden_paths": list(input_mapping["forbidden_paths"]),
            "path_policy": {
                "relative_paths_only": True,
                "parent_traversal_allowed": False,
                "absolute_paths_allowed": False,
            },
            "next_required_capabilities": list(_NEXT_REQUIRED_CAPABILITIES),
        },
    }


def run_workspace_lease_create(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    missing_inputs = _missing_lease_create_required(inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_lease_create_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = {
        "workspace_id": input_mapping["workspace_id"],
        "run_id": input_mapping["run_id"],
        "mode": input_mapping["mode"],
        "lease_status": "created",
        "bound_to": {"agent_id": input_mapping["agent_id"]},
        "granted_by": {"decision_id": input_mapping["decision_id"]},
        "created_by": {
            "proposal_id": input_mapping["proposal_id"],
            "execution_id": input_mapping["execution_id"],
        },
        "provenance": {
            "decision_id": input_mapping["decision_id"],
            "proposal_id": input_mapping["proposal_id"],
            "execution_id": input_mapping["execution_id"],
            "grant_basis": {"workspace": {"mode": input_mapping["mode"]}},
            "path_policy": {
                "relative_paths_only": True,
                "parent_traversal_allowed": False,
                "absolute_paths_allowed": False,
            },
        },
    }
    return {
        "kind": "capability_run_result",
        "capability_id": WORKSPACE_LEASE_CREATE_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_proposal",
        "append_required": True,
        "lease_event": {
            "event_type": "workspace.lease_created",
            "run_id": input_mapping["run_id"],
            "payload": payload,
        },
    }


def _missing_required(inputs: Mapping[str, Any] | None) -> list[str]:
    input_mapping = inputs or {}
    return [
        name
        for name in ("root", "cwd", "workspace_name")
        if name not in input_mapping or input_mapping.get(name) in (None, "")
    ]


def _missing_lease_create_required(inputs: Mapping[str, Any] | None) -> list[str]:
    input_mapping = inputs or {}
    return [
        name
        for name in (
            "root",
            "run_id",
            "workspace_id",
            "agent_id",
            "decision_id",
            "proposal_id",
            "execution_id",
        )
        if name not in input_mapping or input_mapping.get(name) in (None, "")
    ]


def _validate_lease_create_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    for name in (
        "root",
        "run_id",
        "workspace_id",
        "agent_id",
        "decision_id",
        "proposal_id",
        "execution_id",
    ):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    mode = input_mapping.get("mode", "isolated_rw")
    if mode != "isolated_rw":
        raise ValueError("mode must be isolated_rw")
    input_mapping["mode"] = mode
    return input_mapping


def _safe_relative_paths(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of relative paths")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be a non-empty relative path")
        candidate = item.strip().replace("\\", "/")
        path = PurePosixPath(candidate)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{field_name}[{index}] must stay inside the workspace")
        if candidate in {".", ""}:
            raise ValueError(f"{field_name}[{index}] must name a workspace-relative path")
        result.append(candidate)
    return result


def _workspace_id(value: str) -> str:
    normalized = _WORKSPACE_ID_RE.sub("_", value.strip().lower()).strip("_")
    if not normalized:
        raise ValueError("workspace_name must contain a stable identifier")
    return f"workspace_{normalized}"


__all__ = [
    "WORKSPACE_CAPABILITIES",
    "WORKSPACE_ISOLATED_RW_CAPABILITY",
    "WORKSPACE_LEASE_CREATE_CAPABILITY",
    "is_workspace_capability",
    "run_workspace_isolated_rw",
    "run_workspace_lease_create",
    "validate_workspace_inputs",
]
