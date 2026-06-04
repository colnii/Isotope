"""Trace output formatting for developer demo scenarios."""

from __future__ import annotations

from typing import Any


def _format_trace(result: dict[str, Any]) -> str:
    scenario = result.get("scenario", "v0.1")
    if scenario == "agent-loop-planner-validated-runner":
        return _format_agent_loop_planner_validated_runner_trace(result)
    if scenario == "agent-loop-planner-io-validator":
        return _format_agent_loop_planner_io_validator_trace(result)
    if scenario == "agent-loop-planner-restart-pause":
        return _format_agent_loop_planner_restart_pause_trace(result)
    if scenario == "agent-loop-tick-policy-trace":
        return _format_agent_loop_tick_policy_trace(result)
    if scenario == "agent-loop-tick-driver-trace":
        return _format_agent_loop_tick_driver_trace(result)
    if scenario == "supervisor-capacity-handoff-trace":
        return _format_supervisor_capacity_handoff_trace(result)
    if scenario == "agent-loop-planner-matrix":
        return _format_agent_loop_planner_matrix_trace(result)
    if scenario == "agent-loop-planner-friction":
        return _format_agent_loop_planner_friction_trace(result)
    if scenario == "agent-loop-friction":
        return _format_agent_loop_friction_trace(result)
    if scenario == "external-snapshot-review":
        return _format_external_snapshot_review_trace(result)
    if scenario == "artifact-review":
        return _format_artifact_review_trace(result)
    if scenario == "approval-tool-runner":
        return _format_approval_tool_runner_trace(result)
    if scenario == "terminal-exec":
        return _format_terminal_exec_trace(result)
    if scenario == "model-tool-bridge":
        return _format_model_tool_bridge_trace(result)
    if scenario == "llm-provider-route":
        return _format_llm_provider_route_trace(result)
    if scenario == "llm-tool-result-loop":
        return _format_llm_tool_result_loop_trace(result)
    if scenario == "llm-product-chat-app-entry":
        return _format_llm_product_chat_app_entry_trace(result)
    if scenario == "llm-terminal-tool-loop":
        return _format_llm_terminal_tool_loop_trace(result)
    if scenario == "workbench":
        return _format_workbench_trace(result)
    if scenario == "workbench-ask":
        return _format_workbench_ask_trace(result)
    if scenario == "project-workspace":
        return _format_project_workspace_trace(result)
    if scenario == "v0.2":
        return _format_v0_2_trace(result)
    return _format_v0_1_trace(result)


def _format_v0_1_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "submit input through in-process server",
        f"policy approved action: {result['action_outcome']}",
        f"create artifact summary/ref: {_artifact_id(result.get('artifact_ref', {}))}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
    ]
    return _format_trace_steps("v0.1", steps)


def _format_v0_2_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session through HTTP facade: {result['session_id']}",
        f"create run through HTTP facade: {result['run_id']}",
        "submit input through HTTP facade",
        f"policy approved action: {_bool_text(result['http_api_ok'])}",
        f"create artifact summary/ref: event_count={result['event_count']}",
        f"controlled retrieval allowed: {_bool_text(result['artifact_content_policy_ok'])}",
        f"approval flow verified: {_bool_text(result['approval_ok'])}",
        f"replay verified: {_bool_text(result['http_api_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"HTTP full-content route remains: {result['http_full_content_route_status']}",
        f"memory query remains: {result['memory_query_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_approval_tool_runner_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "propose approval-gated tool action",
        f"policy requested approval: {_bool_text(result['approval_pending_before_resume'])}",
        f"bind shared_ro workspace: {_bool_text(result['workspace_binding_ok'])}",
        f"approval resolved as approved: {_bool_text(result['approval_ok'])}",
        f"action completed and artifact ref created: {_artifact_id(result['artifact_ref'])}",
        f"artifact handoff verified: {_bool_text(result['artifact_handoff_ok'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"HTTP full-content route remains: {result['http_full_content_route_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_artifact_review_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "create source action and policy decision: approved",
        f"create source artifact summary/ref: {_artifact_id(result['artifact_ref'])}",
        f"read source artifact metadata projection: {_bool_text(result['metadata_projection_ok'])}",
        f"policy approved controlled retrieval: {_bool_text(result['controlled_retrieval_ok'])}",
        "propose review action through action chain",
        f"create review artifact summary/ref: {_artifact_id(result['review_artifact_ref'])}",
        f"action completed: {_bool_text(result['review_action_chain_ok'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"HTTP full-content route remains: {result['http_full_content_route_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_external_snapshot_review_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "create native action/artifact before importing external observations",
        f"append deterministic snapshot.imported events: {result['external_observation_count']}",
        f"conflict diagnostics recorded: {result['conflict_diagnostics_count']}",
        f"native state preserved: {_bool_text(result['native_state_preserved'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"external ingestion HTTP route remains: {result['http_external_ingestion_route_status']}",
        f"provider status: {result['provider_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_friction_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "observe run context",
        "plan deterministic next action",
        f"source artifact summary/ref created: {_artifact_id(result['source_artifact_ref'])}",
        f"handoff worker result: {_bool_text(result['worker_handoff_ok'])}",
        f"policy-gated approval pause/resume verified: {_bool_text(result['approval_resume_ok'])}",
        f"app friction count: {result['app_friction_count']}",
        f"private append required: {_bool_text(result['private_append_required'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_friction_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        f"planner adapter status: {result['planner_adapter_status']}",
    ]
    steps.extend(
        f"planner selected symbolic step {decision['step']}: {decision['action']}"
        for decision in result["planner_decisions"]
    )
    steps.extend(
        [
            f"policy-gated approval pause/resume verified: {_bool_text(result['approval_resume_ok'])}",
            f"app friction count: {result['app_friction_count']}",
            f"private append required: {_bool_text(result['private_append_required'])}",
            f"replay verified: {_bool_text(result['replay_ok'])}",
            f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
            f"next development step: {result['next_development_step']}",
        ]
    )
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_matrix_trace(result: dict[str, Any]) -> str:
    fixtures = {fixture["fixture_id"]: fixture for fixture in result["fixtures"]}
    happy = fixtures["happy_path"]
    blocked = fixtures["rejected_out_of_contract_capability"]
    malformed = fixtures["malformed_symbolic_action"]
    steps = [
        f"happy_path session/run: {happy['session_id']} / {happy['run_id']}",
        f"fixture happy_path action/policy/artifact path: {happy['status']}",
        f"happy_path replay verified: {_bool_text(happy['replay_ok'])}",
        f"happy_path checkpoint verified: {_bool_text(happy['checkpoint_ok'])}",
        f"fixture rejected_out_of_contract_capability: {blocked['blocked_capability']}",
        "rejected_out_of_contract_capability classified as app_or_product_queued",
        f"fixture malformed_symbolic_action: {malformed['status']}",
        f"malformed_symbolic_action partial events appended: {_bool_text(malformed['partial_events_appended'])}",
        f"app friction count: {result['app_friction_count']}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_restart_pause_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "planner creates source artifact and worker handoff",
        "planner submits policy-gated action and pause at approval",
        f"approval pending before restart: {_bool_text(result['approval_pending_before_restart'])}",
        "restart server with the same event log and checkpoint store",
        "planner reads pending approval after restart",
        f"resume approval action after restart: {_bool_text(result['restart_resume_ok'])}",
        f"final artifact ref created: {_artifact_id(result['final_artifact_ref'])}",
        f"app friction count: {result['app_friction_count']}",
        f"private append required: {_bool_text(result['private_append_required'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_tick_policy_trace(result: dict[str, Any]) -> str:
    cases = {policy["case_id"]: policy for policy in result["tick_policies"]}
    steps = [
        (
            "ready_continue should_continue="
            f"{_bool_text(cases['ready_continue']['should_continue'])}"
        ),
        f"user_pause stop reason: {cases['user_pause']['must_stop_reason']}",
        f"budget_exhausted stop reason: {cases['budget_exhausted']['must_stop_reason']}",
        f"awaiting_approval stop reason: {cases['awaiting_approval']['must_stop_reason']}",
        f"completed stop reason: {cases['completed']['must_stop_reason']}",
        f"app friction count: {result['app_friction_count']}",
        f"model status: {result['model_status']}",
        f"scheduler status: {result['scheduler_status']}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_tick_driver_trace(result: dict[str, Any]) -> str:
    executed = result["executed_tick"]
    stopped = {tick["case_id"]: tick for tick in result["stopped_ticks"]}
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        f"before policy phase: {executed['before_policy']['phase']}",
        f"planner selected step: {executed['selected_step']}",
        f"action result status: {executed['step_status']}",
        f"artifact ref created: {_artifact_id(executed['artifact_ref'])}",
        f"after policy phase: {executed['after_policy']['phase']}",
        (
            "after policy ticks used: "
            f"{executed['after_policy']['tick_budget']['ticks_used']}"
        ),
        (
            "budget_exhausted stopped without events: "
            f"{_bool_text(stopped['budget_exhausted']['event_delta'] == 0)}"
        ),
        (
            "user_pause stopped without events: "
            f"{_bool_text(stopped['user_pause']['event_delta'] == 0)}"
        ),
        f"model status: {result['model_status']}",
        f"scheduler status: {result['scheduler_status']}",
        f"replay status: {result['replay_status']}",
        f"checkpoint status: {result['checkpoint_status']}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_supervisor_capacity_handoff_trace(result: dict[str, Any]) -> str:
    action = result["supervisor_action"]
    decision = result["capacity_decision"]
    planner = result["planner_output"]
    tick = result["tick_result"]
    persisted = result["persisted_run_policy"]
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        f"supervisor action: {action['kind']} {action['capacity_id']}",
        f"capacity decision: {decision['next_action']}",
        f"planner output summary: {planner['selected_step']}",
        f"tick result: {tick['tick_status']}",
        f"policy before phase: {tick['before_policy']['phase']}",
        f"policy after stop reason: {tick['after_policy']['must_stop_reason']}",
        f"artifact ref created: {_artifact_id(tick['artifact_ref'])}",
        f"persisted run policy phase: {persisted['phase']}",
        f"replay status: {result['replay_status']}",
        f"checkpoint status: {result['checkpoint_status']}",
        f"app friction count: {result['app_friction_count']}",
        f"model status: {result['model_status']}",
        f"scheduler status: {result['scheduler_status']}",
        f"next development step: {result['next_development_step']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_io_validator_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "policy capability list loaded for planner validation",
        f"accept valid planner output: {_bool_text(result['valid_output_accepted'])}",
    ]
    steps.extend(
        f"reject {fixture['fixture_id']}: {fixture['error_code']}"
        for fixture in result["fixtures"]
    )
    steps.extend(
        [
            f"partial events appended: {_bool_text(result['partial_events_appended'])}",
            "artifact full text request denied without grant",
            "replay state unchanged because validator does not execute actions",
            "checkpoint state unchanged because validator does not write checkpoints",
            f"app friction count: {result['app_friction_count']}",
            f"model status: {result['model_status']}",
            f"next development step: {result['next_development_step']}",
        ]
    )
    return _format_trace_steps(result["scenario"], steps)


def _format_agent_loop_planner_validated_runner_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        "policy capability list loaded before runner execution",
        f"validate planner output: {_bool_text(result['validator_gate_passed'])}",
    ]
    steps.extend(
        f"execute validated step {decision['step']}: {decision['action']}"
        for decision in result["planner_decisions"]
    )
    steps.extend(
        [
            f"valid plan executed: {_bool_text(result['valid_plan_executed'])}",
            f"block invalid planner output: {result['invalid_plan_error_code']}",
            (
                "invalid plan partial events appended: "
                f"{_bool_text(result['invalid_plan_partial_events_appended'])}"
            ),
            f"app friction count: {result['app_friction_count']}",
            f"private append required: {_bool_text(result['private_append_required'])}",
            f"replay verified: {_bool_text(result['replay_ok'])}",
            f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
            f"model status: {result['model_status']}",
            f"next development step: {result['next_development_step']}",
        ]
    )
    return _format_trace_steps(result["scenario"], steps)


def _format_terminal_exec_trace(result: dict[str, Any]) -> str:
    steps = [
        f"create session: {result['session_id']}",
        f"create run: {result['run_id']}",
        f"propose action terminal_exec argv-only command: {result['terminal_command']}",
        "policy grants terminal_exec with shell=false command profile",
        f"execute command and capture terminal_output artifact: {_artifact_id(result['terminal_output_artifact_ref'])}",
        f"terminal output verified internally: {_bool_text(result['terminal_output_verified'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"interactive shell remains: {result['interactive_shell_status']}",
        f"memory query remains: {result['memory_query_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_model_tool_bridge_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        f"读取 model-facing tool catalog: codex_task={_bool_text(result['catalog_contains_codex_task'])}",
        f"固定 model selected codex_task action: {result['model_tool_result_status']}",
        f"bridge 提交 pending approval: {_bool_text(result['approval_pending_before_execution'])}",
        "policy 让 Codex 保持暂停，直到 approval",
        f"approval resolved as approved: {_bool_text(result['approval_ok'])}",
        f"Codex CLI backend called after approval: {_bool_text(result['codex_started_after_approval'])}",
        f"记录 artifact: {_artifact_id(result['codex_artifact_ref'])}",
        f"replay 验证: {_bool_text(result['replay_ok'])}",
        f"checkpoint 验证: {_bool_text(result['checkpoint_ok'])}",
        f"real LLM 仍然是: {result['real_llm_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_llm_provider_route_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        "application sends user request through provider route",
        f"provider route exposes codex_task only: {result['provider_seen_tool_names']}",
        f"deterministic test provider selected codex_task: {result['route_result_status']}",
        f"policy returns pending approval: {_bool_text(result['approval_pending_before_execution'])}",
        f"action execution / Codex remains paused before approval: {_bool_text(not result['codex_started_before_approval'])}",
        "no artifact before approval",
        f"idempotency replay verified: {_bool_text(result['idempotency_replay_ok'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"network listener remains: {result['network_listener_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_llm_tool_result_loop_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        "application sends user request through provider route",
        f"provider route exposes codex_task only: {result['provider_seen_tool_names']}",
        f"deterministic test provider selected codex_task: {result['route_result_status']}",
        "policy returns pending approval before action execution",
        f"approval resolved as approved: {_bool_text(result['approval_ok'])}",
        f"Codex CLI backend called after approval: {_bool_text(result['codex_started_after_approval'])}",
        f"artifact ref recorded for model handoff: {_artifact_id(result['tool_result_artifact_ref'])}",
        f"tool result message prepared: {_bool_text(result['tool_result_message_ready'])}",
        f"first approval left run open: {result['first_run_status_after_approval']}",
        f"follow-up model choice submitted for approval: {result['followup_provider_tool_call_id']}",
        f"second approval completed run: {_bool_text(result['second_approval_ok'])}",
        "artifact ref only; no transcript or terminal stdout is included",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"two-step demo status: {result['multi_tool_loop_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_llm_product_chat_app_entry_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        "readiness_check blocked before product-chat route",
        f"blocked response without action side effects: {_bool_text(result['blocked_no_side_effects'])}",
        "no provider call, no Codex call, no artifact while blocked",
        "readiness_check ready after developer smoke gate",
        f"user message accepted by app entry: {_bool_text(result['user_message_entry_ok'])}",
        f"forwarded to product-chat route: {_bool_text(result['ready_forwarded_to_route'])}",
        "policy accepted final-answer write through existing action chain",
        f"final answer artifact recorded: {_bool_text(result['artifact_ref_present'])}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
        f"no real network listener: {result['network_listener_status']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_llm_terminal_tool_loop_trace(result: dict[str, Any]) -> str:
    steps = [
        f"创建 session: {result['session_id']}",
        f"创建 run: {result['run_id']}",
        f"provider sees terminal_exec only: {result['provider_seen_tool_names']}",
        f"deterministic test provider selected terminal_exec: {result['provider_tool_name']}",
        "policy validates terminal command allowlist before execution",
        f"terminal_exec runs through submit_action: {result['terminal_action_status']}",
        f"terminal output captured as artifact ref: {_artifact_id(result['tool_result_artifact_ref'])}",
        f"safe tool-result message prepared: {_bool_text(result['tool_result_message_ready'])}",
        "provider receives status / execution id / artifact ref only",
        f"final answer artifact recorded: {_bool_text(result['final_answer_artifact_ref_present'])}",
        f"codex_call_count remains 0: {result['codex_call_count']}",
        f"replay verified: {_bool_text(result['replay_ok'])}",
        f"checkpoint verified: {_bool_text(result['checkpoint_ok'])}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_workbench_trace(result: dict[str, Any]) -> str:
    steps = [
        "创建 project/task/file 摘要",
        "GET /workbench 读取无搜索条件的首页汇总",
        "POST /workbench 使用 query/types/limit 读取带搜索结果的首页汇总",
        (
            "counts: "
            f"projects={result['project_count']} "
            f"tasks={result['task_count']} "
            f"files={result['file_count']} "
            f"search_results={result['search_result_count']}"
        ),
        f"search result types: {', '.join(result['search_result_types'])}",
        f"updated_at present: {str(result['updated_at_present']).lower()}",
        f"content policy: {result['content_policy']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_workbench_ask_trace(result: dict[str, Any]) -> str:
    counts = result["context_counts"]
    steps = [
        "创建 project/task/file 工作台上下文",
        f"question: {result['question']}",
        f"answer: {result['answer']}",
        f"provider: {result['provider']}/{result['model']}",
        (
            "context: "
            f"projects={counts['projects']} "
            f"tasks={counts['tasks']} "
            f"files={counts['files']} "
            f"search_results={counts['search_results']}"
        ),
        f"content policy: {result['content_policy']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_project_workspace_trace(result: dict[str, Any]) -> str:
    counts = result["workbench_counts"]
    steps = [
        "POST /projects/workspace 创建并关联 project/task/file",
        (
            "project detail: "
            f"tasks={result['project_task_count']} "
            f"files={result['project_file_count']}"
        ),
        (
            "workbench: "
            f"projects={counts['projects']} "
            f"tasks={counts['tasks']} "
            f"files={counts['files']} "
            f"search_results={counts['search_results']}"
        ),
        f"search result types: {', '.join(result['search_result_types'])}",
        f"content policy: {result['content_policy']}",
    ]
    return _format_trace_steps(result["scenario"], steps)


def _format_trace_steps(scenario: str, steps: list[str]) -> str:
    lines = [f"scenario: {scenario}"]
    lines.extend(f"[{index}] {step}" for index, step in enumerate(steps, start=1))
    return "\n".join(lines)


def _artifact_id(ref: dict[str, Any]) -> str:
    artifact_id = ref.get("artifact_id")
    if isinstance(artifact_id, str) and artifact_id:
        return artifact_id
    return "available"


def _bool_text(value: Any) -> str:
    return str(bool(value)).lower()
