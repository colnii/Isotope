from __future__ import annotations
from typing import Any
from .common import builtin_capability


def workspace_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
    ]
