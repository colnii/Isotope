"""Public capability catalog metadata.

This module is intentionally a catalog, not a capability runner. It exposes
stable metadata for app shells without constructing providers or executing work.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
import os
import re
from typing import Any


_CAPABILITY_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
_SHELVES = frozenset(
    {"product_candidate", "prototype", "diagnostic", "experimental"}
)


def _as_tuple(value: tuple[str, ...] | list[str] | None, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} entries must be non-empty strings")
        result.append(item)
    return tuple(result)


def _validate_capability_id(capability_id: str) -> str:
    if not isinstance(capability_id, str) or not _CAPABILITY_ID_RE.fullmatch(capability_id):
        raise ValueError("capability_id must be a stable dotted identifier")
    return capability_id


def _validate_shelf(shelf: str) -> str:
    if shelf not in _SHELVES:
        raise ValueError(f"unknown capability shelf: {shelf}")
    return shelf


@dataclass(frozen=True)
class Capability:
    capability_id: str
    title: str
    description: str
    maturity: str
    shelf: str
    domain_tags: tuple[str, ...]
    input_contract: Mapping[str, Any]
    output_contract: Mapping[str, Any]
    safety_boundaries: tuple[str, ...]
    default_enabled: bool = True
    required_env: tuple[str, ...] = ()
    network_required: bool = False
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", _validate_capability_id(self.capability_id))
        object.__setattr__(self, "shelf", _validate_shelf(self.shelf))
        for field_name in ("title", "description", "maturity"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.default_enabled, bool):
            raise ValueError("default_enabled must be bool")
        if not isinstance(self.network_required, bool):
            raise ValueError("network_required must be bool")
        for field_name in ("provider", "model"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        if not isinstance(self.input_contract, Mapping):
            raise ValueError("input_contract must be a mapping")
        if not isinstance(self.output_contract, Mapping):
            raise ValueError("output_contract must be a mapping")
        object.__setattr__(
            self,
            "input_contract",
            copy.deepcopy(dict(self.input_contract)),
        )
        object.__setattr__(
            self,
            "output_contract",
            copy.deepcopy(dict(self.output_contract)),
        )
        object.__setattr__(
            self,
            "domain_tags",
            _as_tuple(self.domain_tags, field_name="domain_tags"),
        )
        object.__setattr__(
            self,
            "safety_boundaries",
            _as_tuple(self.safety_boundaries, field_name="safety_boundaries"),
        )
        object.__setattr__(
            self,
            "required_env",
            _as_tuple(self.required_env, field_name="required_env"),
        )

    def to_manifest_dict(self) -> dict[str, Any]:
        manifest = {
            "capability_id": self.capability_id,
            "title": self.title,
            "description": self.description,
            "maturity": self.maturity,
            "shelf": self.shelf,
            "domain_tags": list(self.domain_tags),
            "input_contract": copy.deepcopy(dict(self.input_contract)),
            "output_contract": copy.deepcopy(dict(self.output_contract)),
            "safety_boundaries": list(self.safety_boundaries),
            "default_enabled": self.default_enabled,
            "required_env": list(self.required_env),
            "network_required": self.network_required,
        }
        if self.provider is not None:
            manifest["provider"] = self.provider
        if self.model is not None:
            manifest["model"] = self.model
        return manifest


class CapabilityCatalog:
    def __init__(self, *, capabilities: list[Capability] | tuple[Capability, ...] | None = None):
        self._capabilities: dict[str, Capability] = {}
        if capabilities is None:
            capabilities = ()
        if not isinstance(capabilities, (list, tuple)):
            raise ValueError("capabilities must be a list or tuple")
        for capability in capabilities:
            if not isinstance(capability, Capability):
                raise ValueError("capabilities must contain Capability objects")
            if capability.capability_id in self._capabilities:
                raise ValueError(f"duplicate capability_id: {capability.capability_id}")
            self._capabilities[capability.capability_id] = capability

    @classmethod
    def default(cls) -> "CapabilityCatalog":
        from .extensions import extension_capability_definitions

        return cls(
            capabilities=[
                _builtin_capability(
                    "approval.tool.runner",
                    title="Approval Tool Runner",
                    description="Exercise approval-gated tool execution through core boundaries.",
                    tags=("approval", "tool", "runner"),
                ),
                _builtin_capability(
                    "artifact.review",
                    title="Artifact Review",
                    description="Review artifact summaries through ResourceRef and content-policy boundaries.",
                    tags=("artifact", "review"),
                ),
                *extension_capability_definitions(Capability),
                Capability(
                    capability_id="artifact.diff_result",
                    title="Artifact Diff Result",
                    description=(
                        "Capture a materialized workspace diff result as a "
                        "structured artifact without exposing raw file content."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "artifact",
                        "diff",
                        "summary",
                        "native-coding",
                        "workspace",
                    ),
                    input_contract={
                        "type": "object",
                        "required": [
                            "root",
                            "cwd",
                            "workspace_id",
                            "run_id",
                            "execution_id",
                        ],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime state root containing artifact storage.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Source workspace directory to compare against.",
                            },
                            "workspace_id": {
                                "type": "string",
                                "description": "Materialized workspace id.",
                            },
                            "run_id": {
                                "type": "string",
                                "description": "Run id for the artifact ResourceRef.",
                            },
                            "execution_id": {
                                "type": "string",
                                "description": "Execution id recorded in artifact provenance.",
                            },
                            "include_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative files or directories to summarize.",
                                "default": ["."],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "artifact",
                            "artifact_ref",
                            "artifact_type",
                        ],
                    },
                    safety_boundaries=(
                        "artifact_store_write",
                        "diff_result_projection",
                        "structured_resource_ref",
                        "raw_file_content_excluded",
                        "state_event_append_handoff",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="artifact.changed_files",
                    title="Artifact Changed Files",
                    description=(
                        "Capture materialized workspace changed-file metadata "
                        "as a structured artifact."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "artifact",
                        "changed-files",
                        "native-coding",
                        "workspace",
                        "summary",
                    ),
                    input_contract={
                        "type": "object",
                        "required": [
                            "root",
                            "cwd",
                            "workspace_id",
                            "run_id",
                            "execution_id",
                        ],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime state root containing artifact storage.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Source workspace directory to compare against.",
                            },
                            "workspace_id": {
                                "type": "string",
                                "description": "Materialized workspace id.",
                            },
                            "run_id": {
                                "type": "string",
                                "description": "Run id for the artifact ResourceRef.",
                            },
                            "execution_id": {
                                "type": "string",
                                "description": "Execution id recorded in artifact provenance.",
                            },
                            "include_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative files or directories to summarize.",
                                "default": ["."],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "artifact",
                            "artifact_ref",
                            "artifact_type",
                        ],
                    },
                    safety_boundaries=(
                        "artifact_store_write",
                        "diff_result_projection",
                        "structured_resource_ref",
                        "raw_file_content_excluded",
                        "state_event_append_handoff",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                _builtin_capability(
                    "external.snapshot.review",
                    title="External Snapshot Review",
                    description="Review imported snapshot observations without overriding native state.",
                    tags=("external", "snapshot", "review"),
                ),
                Capability(
                    capability_id="coding_task.plan",
                    title="Native Coding Task Plan",
                    description=(
                        "Prepare a native coding task for isolated workspace "
                        "execution and reviewed apply handoff."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "native",
                        "coding",
                        "plan",
                        "workspace",
                        "policy",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "goal"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for coding artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Workspace directory to plan against.",
                            },
                            "goal": {
                                "type": "string",
                                "description": "Native coding task goal.",
                            },
                            "allowed_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Relative paths that coding work may touch.",
                                "default": [],
                            },
                            "forbidden_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Relative paths that coding work must not touch.",
                                "default": [],
                            },
                            "verification_commands": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Allowlist candidates for test.run execution.",
                                "default": [],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "plan",
                            "execution_requirements",
                            "next_capabilities",
                        ],
                    },
                    safety_boundaries=(
                        "isolated_workspace_execution_path",
                        "reviewed_apply_handoff",
                        "allowlisted_verification_commands",
                        "artifact_backed_diff",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="coding_task.execute",
                    title="Native Coding Task Execute",
                    description=(
                        "Run a limited native coding loop in an isolated "
                        "workspace without delegating implementation to Codex."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "native",
                        "coding",
                        "execute",
                        "workspace",
                        "artifact",
                        "test",
                    ),
                    input_contract={
                        "type": "object",
                        "required": [
                            "root",
                            "cwd",
                            "workspace_id",
                            "goal",
                            "patch",
                            "argv",
                            "run_id",
                            "execution_id",
                        ],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime state root.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Source workspace directory.",
                            },
                            "workspace_id": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Isolated workspace id to materialize.",
                            },
                            "goal": {
                                "type": "string",
                                "description": "Native coding task goal.",
                            },
                            "patch": {
                                "type": "string",
                                "description": "Workspace-relative unified diff to apply.",
                            },
                            "argv": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Verification command argv.",
                            },
                            "run_id": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Run id for artifact ResourceRefs.",
                            },
                            "execution_id": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Execution id recorded in artifact provenance.",
                            },
                            "include_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative files or directories to copy and summarize.",
                                "default": ["."],
                            },
                            "forbidden_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative files or directories excluded from copy.",
                                "default": [],
                            },
                            "allowed_commands": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Allowed verification command names.",
                                "default": [],
                            },
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Verification timeout in seconds.",
                                "default": 30,
                            },
                            "max_output_bytes": {
                                "type": "integer",
                                "description": "Maximum captured verification output bytes.",
                                "default": 4096,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "coding_execution",
                            "artifact_refs",
                            "verification",
                        ],
                    },
                    safety_boundaries=(
                        "no_codex_delegation",
                        "limited_step_count",
                        "isolated_workspace_write_only",
                        "workspace_relative_patch_only",
                        "argv_allowlist_only",
                        "writes_only_artifact_store",
                        "source_workspace_not_modified",
                        "no_event_append",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="coding_task.run",
                    title="Native Coding Task Run",
                    description=(
                        "Run a native coding task through the existing agent "
                        "loop, scoped code context capabilities, isolated "
                        "execution, and artifact evidence."
                    ),
                    maturity="v0.3",
                    shelf="product_candidate",
                    domain_tags=(
                        "native",
                        "coding",
                        "agent-loop",
                        "workspace",
                        "artifact",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["goal"],
                        "properties": {
                            "goal": {
                                "type": "string",
                                "description": "Natural-language coding goal.",
                            },
                            "include_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": ["."],
                            },
                            "forbidden_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                            "verification_intent": {"type": "string"},
                            "max_steps": {"type": "integer", "default": 6},
                            "timeout_seconds": {"type": "integer", "default": 120},
                            "root": {"type": "string", "x-system-input": True},
                            "cwd": {"type": "string", "x-system-input": True},
                            "run_id": {"type": "string", "x-system-input": True},
                            "execution_id": {
                                "type": "string",
                                "x-system-input": True,
                            },
                            "workspace_id": {
                                "type": "string",
                                "x-system-input": True,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "workspace_id",
                            "changed_files",
                            "verification",
                            "artifact_refs",
                            "next_action",
                        ],
                    },
                    safety_boundaries=(
                        "uses_existing_agent_loop",
                        "agent_loop_orchestrated",
                        "isolated_workspace_write_only",
                        "source_workspace_write_requires_explicit_apply",
                        "does_not_replace_coding_task_execute",
                        "public_result_projection",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="coding_task.apply_reviewed_diff",
                    title="Apply Reviewed Native Coding Diff",
                    description=(
                        "Apply reviewed native-coding workspace changes back "
                        "to the source workspace after source digest checks."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "native",
                        "coding",
                        "apply",
                        "workspace",
                        "review",
                    ),
                    input_contract={
                        "type": "object",
                        "required": [
                            "root",
                            "cwd",
                            "workspace_id",
                            "expected_source_digests",
                        ],
                        "properties": {
                            "root": {"type": "string", "x-system-input": True},
                            "cwd": {"type": "string", "x-system-input": True},
                            "workspace_id": {
                                "type": "string",
                                "x-system-input": True,
                            },
                            "review_handle_id": {
                                "type": "string",
                                "description": (
                                    "Reviewed native coding apply handle returned "
                                    "by coding_task.run or coding_task.execute."
                                ),
                            },
                            "expected_source_digests": {
                                "type": "object",
                                "x-system-input": True,
                                "description": (
                                    "Map of workspace-relative paths to source "
                                    "sha256 digests captured during review."
                                ),
                            },
                            "expected_changed_files": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "include_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": ["."],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "workspace_id",
                            "changed_files",
                            "applied_files",
                            "blocked_reason",
                            "source_workspace_write",
                        ],
                    },
                    safety_boundaries=(
                        "source_workspace_write_requires_explicit_apply",
                        "source_digest_conflict_guard",
                        "workspace_escape_rejected",
                        "relative_paths_only",
                        "deletion_not_supported",
                        "public_result_projection",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="workspace.isolated_rw",
                    title="Isolated Writable Workspace",
                    description=(
                        "Build a public proposal for an isolated "
                        "writable workspace without creating files or directories."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "workspace",
                        "isolated",
                        "writable",
                        "native-coding",
                        "path-safety",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "workspace_name"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for workspace leases.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Source workspace directory to isolate.",
                            },
                            "workspace_name": {
                                "type": "string",
                                "description": "Stable human-readable workspace name.",
                            },
                            "allowed_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative paths allowed for writes.",
                                "default": [],
                            },
                            "forbidden_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative paths forbidden for writes.",
                                "default": [],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "workspace_action",
                            "path_policy",
                            "next_required_capabilities",
                        ],
                    },
                    safety_boundaries=(
                        "workspace_action_handoff",
                        "path_traversal_rejected",
                        "relative_paths_only",
                        "workspace_materialize_action_path",
                        "git_worktree_creation_action_path",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="workspace.lease_create",
                    title="Workspace Lease Create",
                    description=(
                        "Build a workspace.lease_created event append handoff "
                        "for an isolated writable workspace."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "workspace",
                        "lease",
                        "isolated",
                        "native-coding",
                        "event-handoff",
                    ),
                    input_contract={
                        "type": "object",
                        "required": [
                            "root",
                            "run_id",
                            "workspace_id",
                            "agent_id",
                            "decision_id",
                            "proposal_id",
                            "execution_id",
                        ],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for the event append.",
                            },
                            "run_id": {
                                "type": "string",
                                "description": "Run id that will own the workspace lease.",
                            },
                            "workspace_id": {
                                "type": "string",
                                "description": "Stable workspace id for the lease.",
                            },
                            "agent_id": {
                                "type": "string",
                                "description": "Agent id that the lease is bound to.",
                            },
                            "decision_id": {
                                "type": "string",
                                "description": "Decision id granting the lease.",
                            },
                            "proposal_id": {
                                "type": "string",
                                "description": "Workspace proposal id used to create the lease.",
                            },
                            "execution_id": {
                                "type": "string",
                                "description": "Execution id producing the event candidate.",
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["isolated_rw"],
                                "description": "Workspace lease mode.",
                                "default": "isolated_rw",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "lease_event",
                            "append_required",
                        ],
                    },
                    safety_boundaries=(
                        "lease_event_append_handoff",
                        "state_event_append_action_path",
                        "workspace_materialize_action_path",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="workspace.materialize",
                    title="Workspace Materialize",
                    description=(
                        "Materialize an isolated writable workspace under the "
                        "runtime state root and hand off state-event metadata."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "workspace",
                        "materialize",
                        "isolated",
                        "writable",
                        "native-coding",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "workspace_id"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime state root that will contain materialized workspaces.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Source workspace directory to copy from.",
                            },
                            "workspace_id": {
                                "type": "string",
                                "description": "Stable workspace id for the materialized copy.",
                            },
                            "include_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative files or directories to copy.",
                                "default": ["."],
                            },
                            "forbidden_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative files or directories to exclude.",
                                "default": [],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "materialized_workspace",
                            "workspace_root",
                            "root_ref",
                        ],
                    },
                    safety_boundaries=(
                        "state_root_workspace_write",
                        "workspace_escape_rejected",
                        "relative_paths_only",
                        "state_event_append_handoff",
                        "workspace_file_copy_operation",
                        "vcs_state_preserved",
                        "source_workspace_not_modified",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="workspace.changed_files",
                    title="Workspace Changed Files",
                    description=(
                        "Compare a materialized isolated workspace against its "
                        "source workspace and return changed-file summaries."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "workspace",
                        "changed-files",
                        "diff",
                        "native-coding",
                        "inspection",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "workspace_id"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime state root containing workspaces.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Source workspace directory to compare against.",
                            },
                            "workspace_id": {
                                "type": "string",
                                "description": "Materialized workspace id.",
                            },
                            "include_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative files or directories to compare.",
                                "default": ["."],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "changed_files",
                            "changed_file_count",
                        ],
                    },
                    safety_boundaries=(
                        "diff_result_projection",
                        "relative_paths_only",
                        "workspace_diff_projection",
                        "artifact_write_action_handoff",
                        "state_event_append_handoff",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="workspace.release",
                    title="Workspace Release",
                    description=(
                        "Release a materialized isolated workspace by deleting "
                        "only root/workspaces/<workspace_id>."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "workspace",
                        "release",
                        "cleanup",
                        "native-coding",
                        "isolated",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "workspace_id"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime state root containing workspaces.",
                            },
                            "workspace_id": {
                                "type": "string",
                                "description": "Materialized workspace id to remove.",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "released_workspace",
                            "removed_path",
                        ],
                    },
                    safety_boundaries=(
                        "deletes_only_materialized_workspace",
                        "workspace_id_path_guard",
                        "source_workspace_preserved",
                        "state_event_append_handoff",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="code.read",
                    title="Code Read",
                    description=(
                        "Read a limited excerpt and public metadata from "
                        "one workspace-relative code file."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "code",
                        "read",
                        "native-coding",
                        "workspace",
                        "inspection",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "path"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for read artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Workspace directory that bounds the read.",
                            },
                            "path": {
                                "type": "string",
                                "description": "Workspace-relative file path to inspect.",
                            },
                            "max_excerpt_chars": {
                                "type": "integer",
                                "description": "Maximum returned excerpt characters.",
                                "default": 2000,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "code_read",
                            "code_ref",
                            "excerpt",
                        ],
                    },
                    safety_boundaries=(
                        "relative_paths_only",
                        "workspace_escape_rejected",
                        "limited_excerpts_only",
                        "workspace_code_projection",
                        "code_excerpt_projection",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="code.search",
                    title="Code Search",
                    description=(
                        "Search workspace-relative code files with limited "
                        "line excerpts and stable code refs."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "code",
                        "search",
                        "native-coding",
                        "workspace",
                        "inspection",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "query"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for search artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Workspace directory that bounds the search.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Literal text query to find.",
                            },
                            "include_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative files or directories to search.",
                                "default": ["."],
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum returned matches.",
                                "default": 20,
                            },
                            "max_excerpt_chars": {
                                "type": "integer",
                                "description": "Maximum characters per returned line excerpt.",
                                "default": 2000,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "code_search",
                            "matches",
                            "code_refs",
                        ],
                    },
                    safety_boundaries=(
                        "relative_paths_only",
                        "workspace_escape_rejected",
                        "limited_excerpts_only",
                        "workspace_code_projection",
                        "code_excerpt_projection",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="code.apply_patch",
                    title="Code Apply Patch",
                    description=(
                        "Apply a workspace-relative unified diff with hunk "
                        "context validation and changed-file reporting."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "code",
                        "patch",
                        "edit",
                        "native-coding",
                        "workspace",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "patch"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for patch artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Materialized workspace directory to patch.",
                            },
                            "patch": {
                                "type": "string",
                                "description": "Unified diff to apply inside cwd.",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "patch_result",
                            "changed_files",
                        ],
                    },
                    safety_boundaries=(
                        "unified_diff_only",
                        "workspace_escape_rejected",
                        "workspace_relative_patch_only",
                        "context_mismatch_fails_without_write",
                        "no_command_execution",
                        "diff_result_projection",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="test.run",
                    title="Test Run",
                    description=(
                        "Run an argv-only allowlisted validation command inside "
                        "a materialized workspace."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "test",
                        "validation",
                        "terminal",
                        "native-coding",
                        "workspace",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "argv"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for test artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Materialized workspace directory for the command.",
                            },
                            "argv": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Shell-free argv command to run.",
                            },
                            "allowed_commands": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Command-name allowlist.",
                                "default": ["echo", "printf", "pwd", "true", "false", "sleep"],
                            },
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Maximum command runtime.",
                                "default": 30,
                            },
                            "max_output_bytes": {
                                "type": "integer",
                                "description": "Combined stdout/stderr excerpt budget.",
                                "default": 4096,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "test_result",
                            "stdout_excerpt",
                            "stderr_excerpt",
                        ],
                    },
                    safety_boundaries=(
                        "argv_allowlist_only",
                        "shell_false",
                        "limited_stdout_stderr_excerpts",
                        "no_artifact_write",
                        "no_event_append",
                        "workspace_cwd_required",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="vcs.status",
                    title="VCS Status",
                    description=(
                        "Project git branch and porcelain status through fixed "
                        "git subcommands."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "vcs",
                        "git",
                        "status",
                        "native-coding",
                        "state-projection",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for status artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Git workspace directory to inspect.",
                            },
                            "max_stat_chars": {
                                "type": "integer",
                                "description": "Reserved stat excerpt budget.",
                                "default": 4000,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "vcs_status",
                            "changed_files",
                        ],
                    },
                    safety_boundaries=(
                        "fixed_git_subcommands_only",
                        "git_status_projection",
                        "no_vcs_mutation",
                        "no_artifact_write",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="vcs.diff",
                    title="VCS Diff",
                    description=(
                        "Project git diff stat and changed-file names through "
                        "fixed git subcommands."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "vcs",
                        "git",
                        "diff",
                        "native-coding",
                        "diff-projection",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root for diff artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Git workspace directory to inspect.",
                            },
                            "max_stat_chars": {
                                "type": "integer",
                                "description": "Maximum returned diff stat characters.",
                                "default": 4000,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "vcs_diff",
                            "changed_files",
                            "stat_excerpt",
                        ],
                    },
                    safety_boundaries=(
                        "fixed_git_subcommands_only",
                        "git_diff_projection",
                        "diff_result_projection",
                        "no_vcs_mutation",
                        "no_artifact_write",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="memory.query",
                    title="Memory Query",
                    description=(
                        "Query local memory through the existing summary / refs / "
                        "provenance boundary."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("memory", "query", "recall", "provenance"),
                    input_contract={
                        "type": "object",
                        "required": ["root", "query", "run_id"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root containing memory/*.json.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Public memory search query.",
                            },
                            "run_id": {
                                "type": "string",
                                "description": "Run id for caller audit and provenance filtering.",
                            },
                            "scope": {
                                "type": "string",
                                "enum": ["thread", "run", "session"],
                                "description": "Optional memory scope filter.",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum records to preview.",
                                "default": 20,
                            },
                            "controlled_expand": {
                                "type": "boolean",
                                "description": (
                                    "Materialize matched memory record content within "
                                    "expand_budget."
                                ),
                                "default": False,
                            },
                            "expand_budget": {
                                "type": "integer",
                                "description": (
                                    "Positive materialization budget when "
                                    "controlled_expand is true."
                                ),
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "content_policy",
                            "results",
                            "controlled_expand",
                        ],
                    },
                    safety_boundaries=(
                        "memory_query_grant_gated",
                        "caller_context_audited",
                        "memory_record_refs_expandable",
                        "controlled_expand_materialized_budgeted",
                        "no_source_artifact_full_content_read",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="memory.recall",
                    title="Memory Recall",
                    description=(
                        "Search local state-root memory previews without requiring "
                        "the model to know an internal agent-loop run id."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("memory", "recall", "query", "preview", "provenance"),
                    input_contract={
                        "type": "object",
                        "required": ["root", "query"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root containing memory/*.json.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Public memory search query.",
                            },
                            "scope": {
                                "type": "string",
                                "enum": ["thread", "run", "session"],
                                "description": "Optional memory scope filter.",
                            },
                            "run_id": {
                                "type": "string",
                                "description": (
                                    "Optional provenance run id filter when the "
                                    "user names a run."
                                ),
                            },
                            "session_id": {
                                "type": "string",
                                "description": (
                                    "Optional provenance session id filter when "
                                    "the user names a session."
                                ),
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum records to preview.",
                                "default": 20,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "content_policy",
                            "summary",
                            "results",
                        ],
                    },
                    safety_boundaries=(
                        "memory_public_metadata",
                        "source_refs_metadata",
                        "no_memory_record_content",
                        "no_source_artifact_full_content_read",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="memory.promotion.preview",
                    title="Memory Promotion Handoff",
                    description=(
                        "Build a public write_memory action handoff from "
                        "structured artifact or external observation metadata."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("memory", "promotion", "write-memory", "handoff"),
                    input_contract={
                        "type": "object",
                        "required": [
                            "run_id",
                            "agent_id",
                            "thread_id",
                            "candidate",
                        ],
                        "properties": {
                            "run_id": {
                                "type": "string",
                                "description": "Run id for the proposed write_memory action.",
                            },
                            "agent_id": {
                                "type": "string",
                                "description": "Agent id proposing memory promotion.",
                            },
                            "thread_id": {
                                "type": "string",
                                "description": "Thread id for the proposed action.",
                            },
                            "candidate": {
                                "type": "object",
                                "description": (
                                    "Structured artifact or accepted external "
                                    "observation promotion candidate."
                                ),
                            },
                            "scope": {
                                "type": "string",
                                "enum": ["thread", "run", "session"],
                                "description": "Memory scope for the proposal.",
                                "default": "run",
                            },
                            "quality": {
                                "type": "string",
                                "description": "Candidate quality label.",
                                "default": "candidate",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "action_type",
                            "scope",
                            "summary",
                            "source_refs",
                            "provenance",
                            "quality",
                        ],
                    },
                    safety_boundaries=(
                        "write_memory_action_payload",
                        "write_memory_action_handoff",
                        "canonical_event_append_via_memory_action",
                        "structured_source_required",
                        "source_ref_metadata_projection",
                        "memory_promotion_projection",
                        "memory_record_refs_expandable",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="screen.observe",
                    title="Screen Observe",
                    description=(
                        "Run a policy-gated local screen observation and return "
                        "the shared screen report."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "screen",
                        "observe",
                        "screenshot",
                        "metadata",
                        "gui",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["target_selector"],
                        "properties": {
                            "target_selector": {
                                "type": "object",
                                "description": (
                                    "Window selector with kind=window and selector "
                                    "keys such as app, title_contains, or window_id."
                                ),
                            },
                            "target_allowlist": {
                                "type": "object",
                                "description": (
                                    "Optional allowed_apps / allowed_title_contains "
                                    "policy override for this observe call."
                                ),
                            },
                            "capture": {
                                "type": "array",
                                "description": (
                                    "Capture kinds, limited to metadata and screenshot."
                                ),
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["non_intrusive"],
                                "description": "Observation mode.",
                            },
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": (
                                    "Optional runtime root. Agent loop calls use "
                                    "their capability root when this is omitted."
                                ),
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "screen_observe",
                            "screen_report",
                        ],
                    },
                    safety_boundaries=(
                        "policy_gated_screen_observe",
                        "local_backend_only",
                        "screen_report_artifact",
                        "no_screenshot_content_in_events",
                        "screenshot_content_for_model_observation",
                        "no_input_execution",
                        "target_allowlist_supported",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="screen.report",
                    title="Screen Report",
                    description=(
                        "Summarize existing screen run records through the shared "
                        "public observe/control plan report boundary."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "screen",
                        "report",
                        "observe",
                        "control-plan",
                        "gui",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "run_id"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root containing runs/*/artifacts.",
                            },
                            "run_id": {
                                "type": "string",
                                "description": "Run id whose screen artifacts should be summarized.",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "run_id",
                            "summary",
                            "artifacts",
                        ],
                    },
                    safety_boundaries=(
                        "screen_artifact_projection",
                        "public_result_metadata",
                        "no_screenshot_content",
                        "no_input_execution",
                        "no_window_mutation",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="research.search",
                    title="Research Search",
                    description=(
                        "Run the existing research flow through the runtime provider "
                        "policy and return a public result summary."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "research",
                        "search",
                        "web",
                        "provenance",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "query"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root used to persist research artifacts.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Research query.",
                            },
                            "provider": {
                                "type": "string",
                                "enum": ["codex", "tavily"],
                                "x-system-input": True,
                                "description": "Internal research provider policy.",
                            },
                            "allow_network": {
                                "type": "boolean",
                                "x-system-input": True,
                                "description": "Internal network execution gate.",
                            },
                            "tavily_max_results": {
                                "type": "integer",
                                "minimum": 1,
                                "x-system-input": True,
                                "description": "Internal Tavily result budget.",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "query",
                            "provider",
                            "evidence_status",
                            "source_count",
                            "artifact_refs",
                            "artifacts",
                        ],
                    },
                    safety_boundaries=(
                        "reuses_research_flow",
                        "runtime_provider_policy",
                        "network_access_controlled_by_provider_policy",
                        "writes_research_artifacts",
                        "public_result_metadata",
                        "no_raw_transcript_return",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="research.promote",
                    title="Research Promote",
                    description=(
                        "Build a write_memory proposal summary from an existing "
                        "research.report record using the memory promotion boundary."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "research",
                        "promote",
                        "memory",
                        "proposal",
                        "provenance",
                    ),
                    input_contract={
                        "type": "object",
                        "required": [
                            "root",
                            "run_id",
                            "artifact_id",
                            "agent_id",
                            "thread_id",
                        ],
                        "properties": {
                            "root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Runtime root containing research artifacts.",
                            },
                            "run_id": {
                                "type": "string",
                                "description": "Run id for the research.report artifact.",
                            },
                            "artifact_id": {
                                "type": "string",
                                "description": "Artifact id for the research.report artifact.",
                            },
                            "agent_id": {
                                "type": "string",
                                "description": "Agent id recorded on the write_memory proposal.",
                            },
                            "thread_id": {
                                "type": "string",
                                "description": "Thread id recorded on the write_memory proposal.",
                            },
                            "scope": {
                                "type": "string",
                                "enum": ["thread", "run", "session"],
                                "description": "Memory promotion scope.",
                                "default": "run",
                            },
                            "quality": {
                                "type": "string",
                                "description": "Memory candidate quality label.",
                                "default": "candidate",
                            },
                            "proposal_id": {
                                "type": "string",
                                "description": "Optional stable proposal id.",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "artifact_type",
                            "artifact_ref",
                            "proposal_id",
                            "action_type",
                            "scope",
                            "quality",
                            "summary",
                            "source_refs",
                            "requested_capabilities",
                            "quality_gate_status",
                            "quality_gate_reasons",
                            "memory_write",
                        ],
                    },
                    safety_boundaries=(
                        "reuses_research_memory_promotion_action",
                        "reuses_memory_promotion_boundary",
                        "research_report_artifact_only",
                        "write_memory_action_handoff",
                        "research_promotion_projection",
                        "write_memory_public_result_metadata",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="supervisor.codex_operation",
                    title="Supervisor Operation",
                    description=(
                        "Unified Supervisor operation capacity. "
                        "Operations are selected by enum and dispatched through "
                        "existing managed Supervisor boundaries."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "supervisor",
                        "operation",
                        "worker",
                        "agent-loop",
                        "capacity",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["operation", "state_root"],
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": [
                                    "request_context",
                                    "worker_review",
                                    "integration_review",
                                    "launch_worker",
                                    "resume_worker",
                                    "adopt_resume_by_description",
                                ],
                                "description": "Supervisor operation to dispatch.",
                            },
                            "state_root": {
                                "type": "string",
                                "description": "Supervisor state root directory.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Workspace directory for context or worker launch.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Context query for request_context.",
                            },
                            "target_name": {
                                "type": "string",
                                "description": "Managed worker target name for launch_worker.",
                            },
                            "worker_goal": {
                                "type": "string",
                                "description": "Worker goal for launch_worker.",
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Managed worker session id for resume_worker.",
                            },
                            "description": {
                                "type": "string",
                                "description": (
                                    "Natural-language description used by "
                                    "adopt_resume_by_description to match a local Codex session."
                                ),
                            },
                            "prompt": {
                                "type": "string",
                                "description": "Prompt sent to the managed resume worker.",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "operation",
                            "operation_result",
                            "runner_kind",
                        ],
                    },
                    safety_boundaries=(
                        "single_supervisor_operation_capacity",
                        "no_arbitrary_worker_command",
                        "reuses_existing_supervisor_boundaries",
                        "agent_loop_call_capability_compatible",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="supervisor.project_status",
                    title="Supervisor Project Status",
                    description=(
                        "Read the current public Supervisor desktop "
                        "state projection for project status, blockers, "
                        "approvals, workers, and artifacts."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "supervisor",
                        "project-status",
                        "desktop-chat",
                        "snapshot",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["state_root"],
                        "properties": {
                            "state_root": {
                                "type": "string",
                                "description": "Supervisor state root directory.",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": ["status", "project_state"],
                    },
                    safety_boundaries=(
                        "public_state_projection",
                        "desktop_snapshot_projection",
                        "no_raw_transcript_return",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="isotope.self_repair",
                    title="Isotope Self Repair",
                    description=(
                        "Launch a Codex-assisted Supervisor worker in an "
                        "isolated worktree to repair an Isotope capability gap. "
                        "Isotope orchestrates context, isolation, and result "
                        "projection; Codex performs non-trivial code changes."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "isotope",
                        "self-repair",
                        "desktop-chat",
                        "codex-assisted",
                        "capability-gap",
                    ),
                    input_contract={
                        "type": "object",
                        "required": [
                            "state_root",
                            "cwd",
                            "user_goal",
                            "failure_summary",
                        ],
                        "properties": {
                            "state_root": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Supervisor state root directory.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Isotope repository workspace to repair.",
                            },
                            "user_goal": {
                                "type": "string",
                                "description": "Original user goal that exposed the gap.",
                            },
                            "failure_summary": {
                                "type": "string",
                                "description": "Current Isotope capability gap or failure.",
                            },
                            "suggested_fix_summary": {
                                "type": "string",
                                "description": "Optional repair direction for Codex.",
                            },
                            "gap_id": {
                                "type": "string",
                                "description": "Optional recorded capability gap id to include as repair context.",
                            },
                            "target_name": {
                                "type": "string",
                                "description": "Optional managed worker name.",
                                "default": "desktop-self-repair",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": ["status", "runner_kind", "self_repair"],
                    },
                    safety_boundaries=(
                        "codex_worker_required_for_non_trivial_changes",
                        "isolated_worktree_required",
                        "no_auto_merge",
                        "no_dependency_skill_or_mcp_install_without_approval",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="supervisor.integration_review",
                    title="Supervisor Integration Review",
                    description=(
                        "Run existing integration-review collection for Supervisor "
                        "merge readiness decisions and execution handoff."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "supervisor",
                        "integration-review",
                        "integration",
                        "review",
                        "merge",
                        "state_projection",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["state_root"],
                        "properties": {
                            "state_root": {
                                "type": "string",
                                "description": "Supervisor state root containing the managed worker registry.",
                            },
                            "base_ref": {
                                "type": "string",
                                "description": "Base branch or ref used for integration checks.",
                                "default": "main",
                            },
                            "include_unfinished": {
                                "type": "boolean",
                                "description": "Include unfinished workers in the integration review.",
                                "default": False,
                            },
                            "include_missing_worktrees": {
                                "type": "boolean",
                                "description": "Include missing worktrees in the review output.",
                                "default": False,
                            },
                            "run_test_gate": {
                                "type": "boolean",
                                "description": "Run worker pytest gate during review.",
                                "default": False,
                            },
                            "run_candidate_validation": {
                                "type": "boolean",
                                "description": "Run lint/test validation for ready candidates.",
                                "default": False,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "summary",
                            "groups",
                            "workers",
                            "stale_missing_worktrees",
                            "safety",
                        ],
                    },
                    safety_boundaries=(
                        "workspace_state_projection",
                        "managed_registry_projection",
                        "git_integration_evidence",
                        "merge_dispatch_handoff",
                        "worker_lifecycle_cleanup_handoff",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="supervisor.goal_plan",
                    title="Supervisor Goal Plan",
                    description=(
                        "Plan Supervisor dashboard goals through the existing goal "
                        "planner boundary."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "supervisor",
                        "goal",
                        "goal-plan",
                        "dashboard",
                        "planning",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["state_root", "cwd", "goal"],
                        "properties": {
                            "state_root": {
                                "type": "string",
                                "description": "Supervisor state root used for goal queue writes.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Workspace directory whose docs seed goal planning.",
                            },
                            "goal": {
                                "type": "string",
                                "description": "User goal to decompose into Supervisor goals.",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum planned goal candidates.",
                                "default": 3,
                            },
                            "research_context": {
                                "type": "string",
                                "description": (
                                    "Optional low-sensitive research summary "
                                    "from prior conversation capabilities."
                                ),
                            },
                            "write": {
                                "type": "boolean",
                                "description": "Write planned candidates into the goal queue.",
                                "default": False,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "mode",
                            "root",
                            "user_goal",
                            "planning_trigger",
                            "candidates",
                            "written_goals",
                            "plan_summary",
                            "phases",
                            "parallel_recommendations",
                            "stop_conditions",
                            "acceptance_conditions",
                        ],
                    },
                    safety_boundaries=(
                        "reuses_goal_planner",
                        "write_requires_explicit_flag",
                        "goal_write_only_when_requested",
                        "planning_result_fields",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="supervisor.request_context",
                    title="Supervisor Request Context",
                    description=(
                        "Retrieve ranked project context through the existing "
                        "Supervisor request_project_context path."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("supervisor", "request_context", "context", "search"),
                    input_contract={
                        "type": "object",
                        "required": ["state_root", "cwd", "query"],
                        "properties": {
                            "state_root": {
                                "type": "string",
                                "description": "Supervisor state root used for context result storage.",
                            },
                            "cwd": {
                                "type": "string",
                                "x-system-input": True,
                                "description": "Workspace directory to search.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Project context query.",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum ranked context items to return.",
                                "default": 5,
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "result_id",
                            "backend",
                            "item_count",
                            "items",
                        ],
                    },
                    safety_boundaries=(
                        "workspace_context_projection",
                        "writes_existing_supervisor_context_store",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="supervisor.worker_review",
                    title="Supervisor Worker Review",
                    description=(
                        "Run existing worker-review collection for Supervisor worker "
                        "decisions and lifecycle handoff."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "supervisor",
                        "worker",
                        "worker-review",
                        "review",
                        "state_projection",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["state_root"],
                        "properties": {
                            "state_root": {
                                "type": "string",
                                "description": "Supervisor state root containing the managed worker registry.",
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "summary",
                            "decision_summary",
                            "automation_candidates",
                            "workers",
                            "safety",
                        ],
                    },
                    safety_boundaries=(
                        "workspace_state_projection",
                        "managed_registry_projection",
                        "worker_decision_handoff",
                        "worker_lifecycle_cleanup_handoff",
                        "public_result_metadata",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
            ]
        )

    def list_capabilities(
        self,
        *,
        shelf: str | None = None,
        include_diagnostics: bool = False,
        include_experimental: bool = False,
    ) -> list[dict[str, Any]]:
        for field_name, value in (
            ("include_diagnostics", include_diagnostics),
            ("include_experimental", include_experimental),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{field_name} must be bool")
        if shelf is not None:
            _validate_shelf(shelf)
        visible = []
        for capability in self._capabilities.values():
            if shelf is not None and capability.shelf != shelf:
                continue
            if capability.shelf == "diagnostic" and not include_diagnostics and shelf != "diagnostic":
                continue
            if capability.shelf == "experimental" and not include_experimental:
                continue
            if capability.shelf not in {"product_candidate", "prototype", "diagnostic", "experimental"}:
                continue
            visible.append(capability.to_manifest_dict())
        return sorted(visible, key=lambda entry: entry["capability_id"])

    def get_manifest(
        self,
        *,
        env: Mapping[str, str] | None = None,
        include_diagnostics: bool = False,
        include_experimental: bool = False,
    ) -> dict[str, Any]:
        capabilities = []
        for entry in self.list_capabilities(
            include_diagnostics=include_diagnostics,
            include_experimental=include_experimental,
        ):
            entry = dict(entry)
            entry["readiness"] = self.get_capability_status(
                entry["capability_id"], env=env
            )
            capabilities.append(entry)
        return {"kind": "capability_manifest", "capabilities": capabilities}

    def get_capability_status(
        self, capability_id: str, *, env: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        capability_id = _validate_capability_id(capability_id)
        try:
            capability = self._capabilities[capability_id]
        except KeyError as exc:
            raise KeyError(capability_id) from exc
        env_mapping = os.environ if env is None else env
        if not isinstance(env_mapping, Mapping):
            raise ValueError("env must be a mapping")
        missing_env = [
            name for name in capability.required_env if not env_mapping.get(name)
        ]
        ready = capability.default_enabled and not missing_env
        if not capability.default_enabled:
            status = "disabled"
        elif missing_env:
            status = "missing_configuration"
        else:
            status = "ready"
        result = {
            "capability_id": capability.capability_id,
            "default_enabled": capability.default_enabled,
            "ready": ready,
            "status": status,
            "missing_env": missing_env,
            "network_required": capability.network_required,
            "provider": capability.provider,
            "model": capability.model,
        }
        return result


def _builtin_capability(
    capability_id: str, *, title: str, description: str, tags: tuple[str, ...]
) -> Capability:
    return Capability(
        capability_id=capability_id,
        title=title,
        description=description,
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=tags,
        input_contract={"type": "object"},
        output_contract={"type": "object"},
        safety_boundaries=("public_metadata_manifest_only", "no_execution"),
        default_enabled=True,
    )


def default_catalog() -> CapabilityCatalog:
    return CapabilityCatalog.default()


def list_capabilities(**kwargs: Any) -> list[dict[str, Any]]:
    return default_catalog().list_capabilities(**kwargs)


def get_manifest(**kwargs: Any) -> dict[str, Any]:
    return default_catalog().get_manifest(**kwargs)


def get_capability_status(capability_id: str, **kwargs: Any) -> dict[str, Any]:
    return default_catalog().get_capability_status(capability_id, **kwargs)
