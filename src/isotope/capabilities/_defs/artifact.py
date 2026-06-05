from __future__ import annotations
from typing import Any
from .common import builtin_capability
from ..extensions import extension_capability_definitions


def artifact_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        builtin_capability(
        "approval.tool.runner",
        title="Approval Tool Runner",
        description="Exercise approval-gated tool execution through core boundaries.",
        tags=("approval", "tool", "runner"),
        ),
        builtin_capability(
        "artifact.review",
        title="Artifact Review",
        description="Review artifact summaries through ResourceRef and content-policy boundaries.",
        tags=("artifact", "review"),
        ),
        *extension_capability_definitions(capability_type),
        capability_type(
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
        capability_type(
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
        builtin_capability(
        "external.snapshot.review",
        title="External Snapshot Review",
        description="Review imported snapshot observations without overriding native state.",
        tags=("external", "snapshot", "review"),
        ),
    ]
