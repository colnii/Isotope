from __future__ import annotations
from typing import Any
from .common import builtin_capability


def core_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
    ]
