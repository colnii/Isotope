"""Minimal tool protocol shapes for the current kernel slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolInvocation:
    """Execution-time tool call description, not a public SDK protocol."""

    tool_name: str
    input_payload: dict[str, Any]
    execution_id: str
    proposal_id: str
    decision_id: str
    grants_snapshot: dict[str, Any]
    provenance: dict[str, Any]
    budget: dict[str, Any] | None = None
    workspace_binding: dict[str, Any] | None = None
    requested_capabilities: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _non_empty_string("tool_name", self.tool_name)
        _dict_field("input_payload", self.input_payload)
        _non_empty_string("execution_id", self.execution_id)
        _non_empty_string("proposal_id", self.proposal_id)
        _non_empty_string("decision_id", self.decision_id)
        _dict_field("grants_snapshot", self.grants_snapshot)
        _validate_provenance(self.provenance)
        if self.provenance["execution_id"] != self.execution_id:
            raise ValueError("provenance.execution_id must match execution_id")
        if self.provenance["proposal_id"] != self.proposal_id:
            raise ValueError("provenance.proposal_id must match proposal_id")
        if self.provenance["decision_id"] != self.decision_id:
            raise ValueError("provenance.decision_id must match decision_id")
        if self.budget is not None:
            _validate_budget(self.budget)
        if self.workspace_binding is not None:
            _validate_workspace_binding(self.workspace_binding)
        if self.requested_capabilities is not None:
            _validate_requested_capabilities_within_grants(
                self.requested_capabilities,
                self.grants_snapshot,
            )


@dataclass(frozen=True)
class ToolResult:
    """Controlled successful tool output summary."""

    result_summary: str
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_empty_string("result_summary", self.result_summary)
        _validate_provenance(self.provenance)
        if not isinstance(self.artifact_refs, list):
            raise ValueError("artifact_refs must be a list")
        for index, ref in enumerate(self.artifact_refs):
            _validate_artifact_ref(ref, f"artifact_refs[{index}]")
        if not isinstance(self.diagnostics, list):
            raise ValueError("diagnostics must be a list")
        for index, diagnostic in enumerate(self.diagnostics):
            if not isinstance(diagnostic, dict):
                raise ValueError(f"diagnostics[{index}] must be a dict")


@dataclass(frozen=True)
class ToolError:
    """Controlled tool failure summary."""

    error_reason_code: str
    message: str
    partial_artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _reason_code(self.error_reason_code)
        _non_empty_string("message", self.message)
        _validate_provenance(self.provenance)
        if not isinstance(self.partial_artifact_refs, list):
            raise ValueError("partial_artifact_refs must be a list")
        for index, ref in enumerate(self.partial_artifact_refs):
            _validate_artifact_ref(ref, f"partial_artifact_refs[{index}]")


def _non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _dict_field(field_name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return value


def _validate_provenance(provenance: Any) -> None:
    _dict_field("provenance", provenance)
    for field_name in ("execution_id", "proposal_id", "decision_id"):
        _non_empty_string(f"provenance.{field_name}", provenance.get(field_name))


def _validate_budget(budget: dict[str, Any]) -> None:
    _dict_field("budget", budget)
    if "seconds" in budget:
        seconds = budget["seconds"]
        if not isinstance(seconds, int) or seconds < 0:
            raise ValueError("budget.seconds must be a non-negative integer")


def _validate_workspace_binding(binding: dict[str, Any]) -> None:
    _dict_field("workspace_binding", binding)
    _non_empty_string("workspace_binding.workspace_id", binding.get("workspace_id"))
    _non_empty_string("workspace_binding.mode", binding.get("mode"))
    lease_status = binding.get("lease_status")
    if lease_status is not None:
        _non_empty_string("workspace_binding.lease_status", lease_status)


def _validate_requested_capabilities_within_grants(
    requested: dict[str, Any],
    grants: dict[str, Any],
) -> None:
    _dict_field("requested_capabilities", requested)
    requested_tools = requested.get("tools", [])
    granted_tools = grants.get("tools", [])
    if requested_tools is not None:
        if not isinstance(requested_tools, list) or not isinstance(granted_tools, list):
            raise ValueError("requested capabilities outside grants")
        if not set(requested_tools).issubset(set(granted_tools)):
            raise ValueError("requested capabilities outside grants")

    requested_workspace = requested.get("workspace")
    if requested_workspace is not None:
        if not isinstance(requested_workspace, dict):
            raise ValueError("requested capabilities outside grants")
        granted_workspace = grants.get("workspace", {})
        if not isinstance(granted_workspace, dict):
            raise ValueError("requested capabilities outside grants")
        if requested_workspace.get("mode") != granted_workspace.get("mode"):
            raise ValueError("requested capabilities outside grants")

    requested_budget = requested.get("budget")
    if requested_budget is not None:
        if not isinstance(requested_budget, dict):
            raise ValueError("requested capabilities outside grants")
        granted_budget = grants.get("budget", {})
        if not isinstance(granted_budget, dict):
            raise ValueError("requested capabilities outside grants")
        for key, value in requested_budget.items():
            granted_value = granted_budget.get(key)
            if (
                isinstance(value, (int, float))
                and isinstance(granted_value, (int, float))
                and value <= granted_value
            ):
                continue
            if value != granted_value:
                raise ValueError("requested capabilities outside grants")


def _validate_artifact_ref(ref: Any, label: str) -> None:
    if not isinstance(ref, dict):
        raise ValueError(f"{label} must be a structured ResourceRef dict")
    for field_name in ("ref_type", "scope", "run_id", "artifact_id"):
        _non_empty_string(f"{label}.{field_name}", ref.get(field_name))
    if ref["ref_type"] != "artifact":
        raise ValueError(f"{label} must be an artifact ResourceRef")


def _reason_code(value: str) -> None:
    _non_empty_string("error_reason_code", value)
    if value != value.lower() or not value.replace("_", "").isalnum():
        raise ValueError("error_reason_code must be a stable identifier")


__all__ = ["ToolError", "ToolInvocation", "ToolResult"]
