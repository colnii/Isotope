from __future__ import annotations

from .models import CapabilityScenario


_SCENARIOS: tuple[CapabilityScenario, ...] = (
    CapabilityScenario(
        "approval_tool_runner_demo",
        ("approval.tool.runner",),
        "Exercise the approval tool runner demo and summarize whether approval was requested.",
        "empty_state",
    ),
    CapabilityScenario(
        "artifact_changed_files_summary",
        ("artifact.changed_files",),
        "Summarize changed files for the prepared workspace artifact run.",
        "workspace_with_diff",
    ),
    CapabilityScenario(
        "artifact_diff_result_summary",
        ("artifact.diff_result",),
        "Create a diff result artifact for the prepared workspace change.",
        "workspace_with_diff",
        combination_only=True,
    ),
    CapabilityScenario(
        "artifact_review_demo",
        ("artifact.review",),
        "Review the prepared artifact summary and report whether it is safe to show.",
        "artifact_seeded",
    ),
    CapabilityScenario(
        "code_apply_patch_fixture",
        ("code.apply_patch",),
        "Apply the provided safe patch to the fixture file.",
        "workspace_with_code",
    ),
    CapabilityScenario(
        "code_ast_edit_fixture",
        ("code.ast_edit",),
        (
            "Use code.ast_edit on src/app.py. Select the "
            "function_definition containing def answer and replace that node "
            "with a valid function returning 'AST_EDITED'."
        ),
        "workspace_with_code",
        required_input_fragments=("function_definition", "def answer"),
    ),
    CapabilityScenario(
        "code_read_fixture",
        ("code.read",),
        "Read src/app.py and tell me whether the fixture marker is present.",
        "workspace_with_code",
    ),
    CapabilityScenario(
        "file_read_fixture",
        ("file.read",),
        (
            "Use file.read with scope=workspace and path=src/app.py, then tell me "
            "whether the fixture marker is present."
        ),
        "workspace_with_code",
    ),
    CapabilityScenario(
        "code_search_fixture",
        ("code.search",),
        "Find the literal marker ISOTOPE_DEV_EVAL_MARKER in the workspace source tree.",
        "workspace_with_code",
        required_input_fragments=("ISOTOPE_DEV_EVAL_MARKER",),
    ),
    CapabilityScenario(
        "coding_apply_reviewed_diff_fixture",
        ("coding_task.apply_reviewed_diff",),
        "Apply the reviewed diff to the prepared isolated workspace.",
        "workspace_with_diff",
        combination_only=True,
    ),
    CapabilityScenario(
        "coding_execute_fixture",
        ("coding_task.execute",),
        "Run the prepared native coding execution fixture and summarize the verification result.",
        "workspace_with_diff",
        combination_only=True,
    ),
    CapabilityScenario(
        "coding_plan_fixture",
        ("coding_task.plan",),
        "Plan a tiny code change for the fixture application.",
        "workspace_with_code",
    ),
    CapabilityScenario(
        "coding_run_fixture",
        ("coding_task.run",),
        "Run the native coding task for the fixture application.",
        "workspace_with_code",
        allowed_result_statuses=("blocked", "error"),
        combination_only=True,
    ),
    CapabilityScenario(
        "external_snapshot_review_demo",
        ("external.snapshot.review",),
        "Review the prepared external snapshot summary.",
        "artifact_seeded",
    ),
    CapabilityScenario(
        "isotope_self_repair_fixture",
        ("isotope.self_repair",),
        "Diagnose the prepared capacity failure and propose a self repair.",
        "empty_state",
        allowed_result_statuses=("ok", "blocked"),
    ),
    CapabilityScenario(
        "mcp_servers_list_fixture",
        ("mcp.servers.list",),
        "List configured MCP servers.",
        "mcp_configured",
    ),
    CapabilityScenario(
        "mcp_tool_call_fixture",
        ("mcp.tool.call",),
        "Call the configured MCP echo tool.",
        "mcp_configured",
        combination_only=True,
    ),
    CapabilityScenario(
        "mcp_tools_search_fixture",
        ("mcp.tools.search",),
        "Search tools on the configured MCP server.",
        "mcp_configured",
    ),
    CapabilityScenario(
        "memory_promotion_preview_fixture",
        ("memory.promotion.preview",),
        "Preview memory promotion for the prepared candidate.",
        "memory_seeded",
    ),
    CapabilityScenario(
        "memory_query_fixture",
        ("memory.query",),
        "Query the prepared run memory for the fixture marker.",
        "memory_seeded",
    ),
    CapabilityScenario(
        "memory_recall_fixture",
        ("memory.recall",),
        "Recall memory about the fixture marker.",
        "memory_seeded",
    ),
    CapabilityScenario(
        "research_promote_fixture",
        ("research.promote",),
        "Promote the prepared research report into memory.",
        "artifact_seeded",
        combination_only=True,
    ),
    CapabilityScenario(
        "research_recall_fixture",
        ("research.recall",),
        (
            "Use existing stored research reports to recall what we already "
            "learned about RAG_RECALL_EVAL_MARKER. Do not run a new web search."
        ),
        "research_recall_seeded",
        required_input_fragments=("RAG_RECALL_EVAL_MARKER",),
    ),
    CapabilityScenario(
        "research_search_fixture",
        ("research.search",),
        "Research the current public docs for pytest markers.",
        "provider_config_gated",
        allowed_result_statuses=("ok", "blocked"),
    ),
    CapabilityScenario(
        "screen_observe_fixture",
        ("screen.observe",),
        "Observe the configured screen target.",
        "screen_config_gated",
        allowed_result_statuses=("ok", "blocked"),
        configuration_gated=True,
    ),
    CapabilityScenario(
        "screen_control_approval_fixture",
        ("screen.control",),
        (
            "Request one approval-gated screen click on the configured Notepad target. "
            "Use execution_mode=execute and do not approve or execute the input."
        ),
        "screen_config_gated",
        required_gates=(
            "required_capacity_called",
            "result_status_allowed",
            "screen_control_approval_guard",
            "low_sensitive_report",
        ),
        allowed_result_statuses=("pending_user_approval",),
        configuration_gated=True,
    ),
    CapabilityScenario(
        "screen_report_fixture",
        ("screen.report",),
        "Summarize the prepared screen observation report.",
        "artifact_seeded",
    ),
    CapabilityScenario(
        "skills_describe_fixture",
        ("skills.describe",),
        "Describe the prepared built-in skill.",
        "empty_state",
    ),
    CapabilityScenario(
        "skills_search_fixture",
        ("skills.search",),
        "Search available skills for research.",
        "empty_state",
    ),
    CapabilityScenario(
        "supervisor_codex_operation_fixture",
        ("supervisor.codex_operation",),
        "Inspect the prepared Codex operation state without launching a new worker.",
        "empty_state",
        allowed_result_statuses=("ok", "blocked"),
    ),
    CapabilityScenario(
        "supervisor_goal_plan_fixture",
        ("supervisor.goal_plan",),
        "Plan three Supervisor goals for improving the fixture eval.",
        "empty_state",
    ),
    CapabilityScenario(
        "supervisor_integration_review_fixture",
        ("supervisor.integration_review",),
        "Review the prepared integration state.",
        "empty_state",
    ),
    CapabilityScenario(
        "supervisor_project_status_fixture",
        ("supervisor.project_status",),
        "Summarize current Supervisor project status.",
        "empty_state",
    ),
    CapabilityScenario(
        "supervisor_request_context_fixture",
        ("supervisor.request_context",),
        "Find context about capacity observations in the fixture repo.",
        "workspace_with_code",
    ),
    CapabilityScenario(
        "supervisor_worker_review_fixture",
        ("supervisor.worker_review",),
        "Review the prepared worker state.",
        "empty_state",
    ),
    CapabilityScenario(
        "test_run_fixture",
        ("test.run",),
        "Run the prepared printf validation command.",
        "workspace_with_code",
    ),
    CapabilityScenario(
        "vcs_diff_fixture",
        ("vcs.diff",),
        "Summarize the prepared git diff.",
        "workspace_with_diff",
    ),
    CapabilityScenario(
        "vcs_status_fixture",
        ("vcs.status",),
        "Show the prepared git status.",
        "workspace_with_diff",
    ),
    CapabilityScenario(
        "workspace_changed_files_fixture",
        ("workspace.changed_files",),
        "List changed files in the prepared isolated workspace.",
        "workspace_with_diff",
    ),
    CapabilityScenario(
        "workspace_isolated_rw_fixture",
        ("workspace.isolated_rw",),
        "Create an isolated writable workspace proposal for the fixture.",
        "workspace_with_code",
    ),
    CapabilityScenario(
        "workspace_lease_create_fixture",
        ("workspace.lease_create",),
        "Create a workspace lease for the prepared isolated workspace.",
        "workspace_with_diff",
        combination_only=True,
    ),
    CapabilityScenario(
        "workspace_materialize_fixture",
        ("workspace.materialize",),
        "Materialize the prepared workspace fixture.",
        "workspace_with_code",
    ),
    CapabilityScenario(
        "workspace_release_fixture",
        ("workspace.release",),
        "Release the prepared materialized workspace.",
        "workspace_with_diff",
        combination_only=True,
    ),
)


def scenario_catalog() -> list[CapabilityScenario]:
    return list(_SCENARIOS)
