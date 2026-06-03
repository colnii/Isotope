"""Low-sensitive capability catalog metadata.

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
                _builtin_capability(
                    "external.snapshot.review",
                    title="External Snapshot Review",
                    description="Review imported snapshot observations without overriding native state.",
                    tags=("external", "snapshot", "review"),
                ),
                Capability(
                    capability_id="coding_task.preview",
                    title="Native Coding Task Preview",
                    description=(
                        "Preview a native coding task contract and report the "
                        "missing execution substrate without delegating to Codex."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "native",
                        "coding",
                        "preview",
                        "workspace",
                        "policy",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "goal"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "description": "Runtime root for future coding artifacts.",
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Workspace directory to preview.",
                            },
                            "goal": {
                                "type": "string",
                                "description": "Native coding task goal.",
                            },
                            "allowed_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Relative paths that future coding work may touch.",
                                "default": [],
                            },
                            "forbidden_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Relative paths that future coding work must not touch.",
                                "default": [],
                            },
                            "verification_commands": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Allowlist candidates for future test.run execution.",
                                "default": [],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "preview",
                            "native_coding_requirements",
                            "blocked_capabilities",
                        ],
                    },
                    safety_boundaries=(
                        "no_codex_delegation",
                        "preview_only_no_workspace_write",
                        "no_patch_apply",
                        "no_test_execution",
                        "no_vcs_mutation",
                        "low_sensitive_summary_only",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="workspace.isolated_rw",
                    title="Isolated Writable Workspace",
                    description=(
                        "Build a low-sensitive proposal for a future isolated "
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
                                "description": "Runtime root for future workspace leases.",
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Source workspace directory to isolate.",
                            },
                            "workspace_name": {
                                "type": "string",
                                "description": "Stable human-readable workspace name.",
                            },
                            "allowed_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative paths allowed for future writes.",
                                "default": [],
                            },
                            "forbidden_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Workspace-relative paths forbidden for future writes.",
                                "default": [],
                            },
                        },
                    },
                    output_contract={
                        "type": "object",
                        "fields": [
                            "status",
                            "runner_kind",
                            "workspace_proposal",
                            "path_policy",
                            "next_required_capabilities",
                        ],
                    },
                    safety_boundaries=(
                        "proposal_only_no_filesystem_write",
                        "path_traversal_rejected",
                        "relative_paths_only",
                        "no_workspace_materialization",
                        "no_git_worktree_creation",
                        "low_sensitive_summary_only",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="workspace.lease_create",
                    title="Workspace Lease Create",
                    description=(
                        "Build a workspace.lease_created event candidate for a "
                        "future isolated writable workspace without appending it."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "workspace",
                        "lease",
                        "isolated",
                        "native-coding",
                        "event-candidate",
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
                                "description": "Runtime root for the future event append.",
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
                                "description": "Future workspace lease mode.",
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
                        "event_candidate_only",
                        "no_event_append",
                        "no_filesystem_write",
                        "no_workspace_materialization",
                        "low_sensitive_summary_only",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="code.read",
                    title="Code Read",
                    description=(
                        "Read a bounded excerpt and low-sensitive metadata from "
                        "one workspace-relative code file."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "code",
                        "read",
                        "native-coding",
                        "workspace",
                        "readonly",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "path"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "description": "Runtime root for future read artifacts.",
                            },
                            "cwd": {
                                "type": "string",
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
                        "bounded_excerpts_only",
                        "no_filesystem_write",
                        "no_command_execution",
                        "low_sensitive_summary_only",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="code.search",
                    title="Code Search",
                    description=(
                        "Search workspace-relative code files with bounded "
                        "line excerpts and stable code refs."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "code",
                        "search",
                        "native-coding",
                        "workspace",
                        "readonly",
                    ),
                    input_contract={
                        "type": "object",
                        "required": ["root", "cwd", "query"],
                        "properties": {
                            "root": {
                                "type": "string",
                                "description": "Runtime root for future search artifacts.",
                            },
                            "cwd": {
                                "type": "string",
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
                        "bounded_excerpts_only",
                        "no_filesystem_write",
                        "no_command_execution",
                        "low_sensitive_summary_only",
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
                                "description": "Runtime root containing memory/*.json.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Low-sensitive memory search query.",
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
                        "summary_refs_provenance_only",
                        "controlled_expand_materialized_budgeted",
                        "no_source_artifact_full_content_read",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="memory.promotion.preview",
                    title="Memory Promotion Preview",
                    description=(
                        "Build a low-sensitive write_memory proposal preview from "
                        "structured artifact or external observation metadata."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("memory", "promotion", "proposal", "preview"),
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
                        "proposal_preview_only",
                        "no_memory_write",
                        "no_canonical_event_append",
                        "structured_source_required",
                        "no_raw_content",
                        "summary_refs_provenance_only",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="screen.report",
                    title="Screen Report",
                    description=(
                        "Summarize existing screen run records through the shared "
                        "low-sensitive observe/control plan report boundary."
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
                        "screen_artifact_read_only",
                        "low_sensitive_summary_only",
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
                        "Run the existing research flow with an explicitly gated "
                        "research provider and return a low-sensitive result summary."
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
                                "description": "Runtime root used to persist research artifacts.",
                            },
                            "query": {
                                "type": "string",
                                "description": "Research query.",
                            },
                            "provider": {
                                "type": "string",
                                "enum": ["fake", "codex", "tavily"],
                                "description": "Capability-safe research provider.",
                                "default": "fake",
                            },
                            "provider_gate": {
                                "type": "string",
                                "enum": ["codex_research", "tavily_research"],
                                "description": (
                                    "Explicit gate required before a non-fake "
                                    "provider can enter the capability path."
                                ),
                            },
                            "allow_network": {
                                "type": "boolean",
                                "description": (
                                    "Allow Tavily network execution after the "
                                    "provider gate is satisfied."
                                ),
                                "default": False,
                            },
                            "tavily_max_results": {
                                "type": "integer",
                                "description": "Maximum Tavily search results.",
                                "default": 5,
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
                        "explicit_provider_gate",
                        "tavily_network_requires_allow_network",
                        "writes_research_artifacts",
                        "low_sensitive_summary_only",
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
                        "reuses_research_memory_promotion_payload",
                        "reuses_memory_promotion_boundary",
                        "research_report_artifact_only",
                        "proposal_only_no_memory_write",
                        "no_raw_transcript_read",
                        "no_proposal_payload_content_return",
                        "low_sensitive_summary_only",
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
                                ],
                                "description": "Supervisor operation to dispatch.",
                            },
                            "state_root": {
                                "type": "string",
                                "description": "Supervisor state root directory.",
                            },
                            "cwd": {
                                "type": "string",
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
                        "low_sensitive_summary_only",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="supervisor.integration_review",
                    title="Supervisor Integration Review",
                    description=(
                        "Run existing integration-review collection in lightweight "
                        "read-only mode for Supervisor merge readiness decisions."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "supervisor",
                        "integration-review",
                        "integration",
                        "review",
                        "merge",
                        "read_only",
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
                                "description": "Include unfinished workers in the read-only review.",
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
                        "workspace_read_only",
                        "managed_registry_read_only",
                        "git_read_only",
                        "lightweight_integration_review",
                        "no_merge_push_or_cleanup",
                        "low_sensitive_summary_only",
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
                        "workspace_read_only",
                        "writes_existing_supervisor_context_store",
                        "low_sensitive_summary_only",
                    ),
                    default_enabled=True,
                    network_required=False,
                ),
                Capability(
                    capability_id="supervisor.worker_review",
                    title="Supervisor Worker Review",
                    description=(
                        "Run existing worker-review collection in lightweight "
                        "read-only mode for Supervisor worker decisions."
                    ),
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=(
                        "supervisor",
                        "worker",
                        "worker-review",
                        "review",
                        "read_only",
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
                        "workspace_read_only",
                        "managed_registry_read_only",
                        "lightweight_worker_review",
                        "no_merge_or_cleanup",
                        "low_sensitive_summary_only",
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
        safety_boundaries=("low_sensitive_manifest_only", "no_execution"),
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
