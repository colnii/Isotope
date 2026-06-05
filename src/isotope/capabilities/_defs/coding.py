from __future__ import annotations
from typing import Any
from .common import builtin_capability


def coding_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
    ]
