from __future__ import annotations
from typing import Any
from .common import builtin_capability


def supervisor_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
        capability_type(
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
