"""Developer demo entrypoint for the Isotope application slices."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .demo_format import _format_plain_text, _format_trace
from .demo_common import _deferred_status, _latest_action_status
from .demo_agent_loop_scenarios import (
    _run_agent_loop_friction_spike,
    _run_agent_loop_planner_adapter_spike,
)
from .demo_agent_loop_matrix_scenarios import (
    _run_agent_loop_planner_matrix_spike,
    _run_agent_loop_planner_restart_pause_spike,
)
from .demo_agent_loop_validation_scenarios import (
    _run_agent_loop_planner_io_validator_spike,
    _run_agent_loop_planner_validated_runner_spike,
)
from .demo_review_scenarios import (
    _run_approval_tool_runner_spike,
    _run_external_snapshot_review_spike,
)
from .demo_workspace_scenarios import (
    _run_project_workspace_append_demo,
    _run_project_workspace_demo,
    _run_workbench_ask_demo,
    _run_workbench_demo,
)
from .integrations.codex import server as codex_server
from .platform.state.checkpoint_store import FileCheckpointStore
from .interfaces.http import (
    HttpApiApp,
    create_codex_cli_http_app,
    create_http_app,
    create_llm_product_chat_http_app,
    create_llm_provider_http_app,
)
from .features.chat.flow import submit_llm_product_chat_user_message_with_preflight
from .llm.provider import (
    LLMFinalAnswerResponse,
    LLMToolCall,
    LLMToolCallResponse,
    build_llm_tool_result_message,
    submit_llm_tool_result_followup,
)
from .llm.tool_bridge import submit_model_tool_call
from .platform.state.projector import RunProjector
from .runtime.in_process import InProcessServer


_ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


def run_demo(root_path: Path | str | None = None, scenario: str = "v0.1") -> dict[str, Any]:
    """Run a deterministic developer demo and return summary metadata."""

    if root_path is None:
        with tempfile.TemporaryDirectory(prefix="isotope-demo-") as temp_root:
            return _run_scenario(Path(temp_root), scenario=scenario)
    return _run_scenario(Path(root_path), scenario=scenario)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an Isotope developer demo.")
    parser.add_argument(
        "--scenario",
        choices=(
            "v0.1",
            "v0.2",
            "approval-tool-runner",
            "artifact-review",
            "external-snapshot-review",
            "agent-loop-friction",
            "agent-loop-planner-friction",
            "agent-loop-planner-matrix",
            "agent-loop-planner-restart-pause",
            "agent-loop-planner-io-validator",
            "agent-loop-planner-validated-runner",
            "terminal-exec",
            "model-tool-bridge",
            "llm-provider-route",
            "llm-tool-result-loop",
            "llm-product-chat-app-entry",
            "llm-terminal-tool-loop",
            "workbench",
            "workbench-ask",
            "project-workspace",
            "project-workspace-append",
        ),
        default="v0.1",
        help="demo scenario to run",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--trace", action="store_true", help="print human-readable execution trace")
    args = parser.parse_args(argv)

    result = run_demo(scenario=args.scenario)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif args.trace:
        print(_format_trace(result))
    else:
        print(_format_plain_text(result))
    return 0


def _run_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root)
    api = InProcessServer(root, checkpoint_store=checkpoint_store)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="demo deterministic artifact path")
    run_id = run["run_id"]
    api.submit_input(run_id, "hello")

    events = api.get_events(run_id)
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(run_id, api.event_store, checkpoint_store)
    artifacts = api.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1]

    artifact_ref = artifact.ref.to_dict()
    checkpoint_artifact_ref = (
        checkpoint_state.artifacts[0]["ref"] if checkpoint_state.artifacts else {}
    )
    replay_ok = asdict(replay_state) == asdict(api.get_run_state(run_id))
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)

    return {
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "action_outcome": _latest_action_status(replay_state.actions),
        "artifact_ref": artifact_ref,
        "artifact_summary": artifact.summary,
        "event_count": len(events),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_run_status": replay_state.status,
        "checkpoint_run_status": checkpoint_state.status,
        "checkpoint_artifact_ref": checkpoint_artifact_ref,
        "memory_status": "boundary_only",
    }


def _run_scenario(root: Path, *, scenario: str) -> dict[str, Any]:
    if scenario == "v0.1":
        return _run_demo(root)
    if scenario == "v0.2":
        return _run_v0_2_demo(root)
    if scenario == "approval-tool-runner":
        return _run_approval_tool_runner_spike(root)
    if scenario == "artifact-review":
        return _run_artifact_review_spike(root)
    if scenario == "external-snapshot-review":
        return _run_external_snapshot_review_spike(root)
    if scenario == "agent-loop-friction":
        return _run_agent_loop_friction_spike(root)
    if scenario == "agent-loop-planner-friction":
        return _run_agent_loop_planner_adapter_spike(root)
    if scenario == "agent-loop-planner-matrix":
        return _run_agent_loop_planner_matrix_spike(root)
    if scenario == "agent-loop-planner-restart-pause":
        return _run_agent_loop_planner_restart_pause_spike(root)
    if scenario == "agent-loop-planner-io-validator":
        return _run_agent_loop_planner_io_validator_spike(root)
    if scenario == "agent-loop-planner-validated-runner":
        return _run_agent_loop_planner_validated_runner_spike(root)
    if scenario == "terminal-exec":
        return _run_terminal_exec_demo(root)
    if scenario == "model-tool-bridge":
        return _run_model_tool_bridge_demo(root)
    if scenario == "llm-provider-route":
        return _run_llm_provider_route_demo(root)
    if scenario == "llm-tool-result-loop":
        return _run_llm_tool_result_loop_demo(root)
    if scenario == "llm-product-chat-app-entry":
        return _run_llm_product_chat_app_entry_demo(root)
    if scenario == "llm-terminal-tool-loop":
        return _run_llm_terminal_tool_loop_demo(root)
    if scenario == "workbench":
        return _run_workbench_demo(root)
    if scenario == "workbench-ask":
        return _run_workbench_ask_demo(root)
    if scenario == "project-workspace":
        return _run_project_workspace_demo(root)
    if scenario == "project-workspace-append":
        return _run_project_workspace_append_demo(root)
    raise ValueError(f"unsupported scenario: {scenario}")


def _run_v0_2_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)

    session_response = app.request("POST", "/sessions", {})
    session_id = session_response.body["session_id"]  # type: ignore[index]
    run_response = app.request(
        "POST",
        f"/sessions/{session_id}/runs",
        {"goal": "demo v0.2 HTTP facade path"},
    )
    run_id = run_response.body["run_id"]  # type: ignore[index]
    input_response = app.request("POST", f"/runs/{run_id}/input", {"text": "hello"})
    state_response = app.request("GET", f"/runs/{run_id}")
    events_response = app.request("GET", f"/runs/{run_id}/events")
    artifact_ref = input_response.body["artifact_ref"]  # type: ignore[index]
    artifact_id = artifact_ref["artifact_id"]
    artifact_summary_response = app.request("GET", f"/artifacts/{artifact_id}/summary")

    checkpoint_store = FileCheckpointStore(root)
    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )

    http_full_content_response = app.request("GET", f"/artifacts/{artifact_id}/content")
    artifact_policy_ok = _artifact_content_policy_ok(app, artifact_ref)
    approval_ok = _approval_flow_ok(root, app)
    http_api_ok = (
        session_response.status_code == 201
        and run_response.status_code == 201
        and input_response.status_code == 200
        and state_response.status_code == 200
        and events_response.status_code == 200
        and artifact_summary_response.status_code == 200
        and replay_state.status == "completed"
    )

    return {
        "scenario": "v0.2",
        "session_id": session_id,
        "run_id": run_id,
        "run_status": replay_state.status,
        "http_api_ok": http_api_ok,
        "approval_ok": approval_ok,
        "artifact_content_policy_ok": artifact_policy_ok,
        "checkpoint_ok": asdict(checkpoint_state) == asdict(replay_state),
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(events_response.body),  # type: ignore[arg-type]
        "http_full_content_route_status": _deferred_status(http_full_content_response),
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "memory_storage_status": "not_enabled",
    }


def _artifact_content_policy_ok(app: Any, artifact_ref: dict[str, Any]) -> bool:
    ref = app.server.artifact_store.list_artifacts(artifact_ref["run_id"])[-1].ref
    summary = app.server.retrieval.get_artifact_summary(
        ref,
        {"artifact": {"read": "summary"}},
    )
    content = app.server.retrieval.get_artifact_content(
        ref,
        grants={"artifact": {"read": "full"}},
        caller_context={"caller": "demo"},
        purpose="developer_demo",
    )
    return (
        "content" not in summary
        and summary["ref"] == ref.to_dict()
        and content["status"] == "ok"
        and content["view"] == "full"
        and isinstance(content.get("content"), str)
    )


def _approval_flow_ok(root: Path, app: Any) -> bool:
    session = app.server.create_session()
    approval_run = app.server.create_run(session["session_id"], goal="demo approval path")
    approval_run_id = approval_run["run_id"]
    pending = app.server.submit_tool_request(
        approval_run_id,
        tool="write_artifact_tool",
        text="approved artifact",
        requires_approval=True,
    )
    pending_approvals = app.server.get_pending_approvals(approval_run_id)
    approval_id = pending_approvals[0]["approval_id"] if pending_approvals else ""
    if pending["status"] != "pending_user_approval" or not approval_id:
        return False

    response = app.request(
        "POST",
        f"/runs/{approval_run_id}/approvals/{approval_id}/resolve",
        {
            "resolution": "approved",
            "reason": "demo approval",
            "resolver": "demo",
        },
    )
    if response.status_code != 200:
        return False
    event_types = [event.event_type for event in app.server.get_events(approval_run_id)]
    approved_state = app.server.get_run_state(approval_run_id)
    checkpoint_store = FileCheckpointStore(root / "approval-checkpoints")
    RunProjector().save_checkpoint(approval_run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        approval_run_id,
        app.server.event_store,
        checkpoint_store,
    )
    return (
        "approval.requested" in event_types
        and "approval.resolved" in event_types
        and event_types.index("approval.resolved") < event_types.index("action.started")
        and approved_state.status == "completed"
        and asdict(checkpoint_state) == asdict(approved_state)
    )


def _run_artifact_review_spike(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)

    session_response = app.request("POST", "/sessions", {})
    session_id = session_response.body["session_id"]  # type: ignore[index]
    run_response = app.request(
        "POST",
        f"/sessions/{session_id}/runs",
        {"goal": "artifact review flow spike"},
    )
    run_id = run_response.body["run_id"]  # type: ignore[index]

    source_setup = app.server.create_source_artifact(
        run_id,
        summary="source artifact summary",
        content="source artifact durable content",
    )
    source_artifact_ref = source_setup["artifact_ref"]
    source_record = app.server.get_artifact_record(source_artifact_ref)

    source_summary = app.server.retrieval.get_artifact_summary(
        source_artifact_ref,
        {"artifact": {"read": "summary"}},
    )
    controlled_retrieval = app.server.retrieval.get_artifact_content(
        source_artifact_ref,
        grants={"artifact": {"read": "full"}},
        caller_context={
            "caller": "artifact_review_demo",
            "run_id": run_id,
            "source_artifact_id": source_record["artifact_id"],
        },
        purpose="artifact_review_flow",
    )
    summary_only_ok = "content" not in source_summary and source_summary["ref"] == source_artifact_ref.to_dict()
    controlled_retrieval_ok = (
        controlled_retrieval.get("status") == "ok"
        and controlled_retrieval.get("view") == "full"
        and isinstance(controlled_retrieval.get("content"), str)
    )

    review_result = app.server.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "review artifact durable content: accepted source artifact",
        },
    )
    review_artifact_ref = review_result["artifact_ref"].to_dict()
    review_artifact = app.server.artifact_store.list_artifacts(run_id)[-1]

    state_response = app.request("GET", f"/runs/{run_id}")
    events_response = app.request("GET", f"/runs/{run_id}/events")
    source_summary_response = app.request(
        "GET",
        f"/artifacts/{source_record['artifact_id']}/summary",
    )
    review_summary_response = app.request(
        "GET",
        f"/artifacts/{review_artifact.artifact_id}/summary",
    )
    http_full_content_response = app.request(
        "GET",
        f"/artifacts/{source_record['artifact_id']}/content",
    )

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint_store = FileCheckpointStore(root / "artifact-review-checkpoints")
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    replay_artifacts = list(replay_state.artifacts)
    checkpoint_artifacts = list(checkpoint_state.artifacts)
    replay_artifact_refs = [artifact["ref"] for artifact in replay_artifacts]
    checkpoint_artifact_refs = [artifact["ref"] for artifact in checkpoint_artifacts]
    replay_artifact_summaries = [artifact["summary"] for artifact in replay_artifacts]
    checkpoint_artifact_summaries = [artifact["summary"] for artifact in checkpoint_artifacts]
    review_artifact_state = next(
        artifact for artifact in replay_artifacts if artifact["ref"] == review_artifact_ref
    )
    review_decision = {
        "status": "accepted",
        "source_ref": source_artifact_ref.to_dict(),
        "basis_summary": source_summary["summary"],
        "review_artifact_ref": review_artifact_ref,
        "provenance": {
            "source_ref": source_artifact_ref.to_dict(),
            "source_basis_event_id": source_record["basis_event_id"],
            "review_artifact_ref": review_artifact_ref,
            "review_execution_id": review_result["execution_id"],
        },
    }
    review_action_chain_ok = (
        event_types.count("action.proposed") >= 1
        and event_types.count("action.decided") >= 1
        and event_types.count("action.started") >= 1
        and event_types.count("action.completed") >= 1
        and event_types.count("artifact.created") >= 2
        and review_artifact_ref in replay_artifact_refs
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    content_policy_ok = (
        summary_only_ok
        and controlled_retrieval_ok
        and _deferred_status(http_full_content_response) == "not_enabled"
    )
    http_api_ok = (
        session_response.status_code == 201
        and run_response.status_code == 201
        and state_response.status_code == 200
        and events_response.status_code == 200
        and source_summary_response.status_code == 200
        and review_summary_response.status_code == 200
    )

    return {
        "scenario": "artifact-review",
        "session_id": session_id,
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "http_api_ok": http_api_ok,
        "review_ok": (
            review_action_chain_ok
            and content_policy_ok
            and replay_ok
            and checkpoint_ok
            and replay_state.status == "completed"
        ),
        "artifact_ref": source_artifact_ref.to_dict(),
        "review_artifact_ref": review_artifact_ref,
        "source_summary": source_summary,
        "source_artifact_record": source_record,
        "source_setup": {
            "status": source_setup["status"],
            "proposal_id": source_setup["proposal_id"],
            "decision_id": source_setup["decision_id"],
            "execution_id": source_setup["execution_id"],
            "artifact_ref": source_setup["artifact_ref"].to_dict(),
            "artifact_summary": source_setup["artifact_summary"],
            "artifact_type": source_setup["artifact_type"],
            "provenance": dict(source_setup["provenance"]),
        },
        "review_summary": review_artifact.summary,
        "review_decision": review_decision,
        "review_artifact_provenance": dict(review_artifact_state["provenance"]),
        "review_action_chain_ok": review_action_chain_ok,
        "summary_only_ok": summary_only_ok,
        "content_policy_ok": content_policy_ok,
        "controlled_retrieval_ok": controlled_retrieval_ok,
        "controlled_retrieval_view": controlled_retrieval.get("view"),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "replay_artifacts": replay_artifacts,
        "checkpoint_artifacts": checkpoint_artifacts,
        "replay_artifact_refs": replay_artifact_refs,
        "checkpoint_artifact_refs": checkpoint_artifact_refs,
        "replay_artifact_summaries": replay_artifact_summaries,
        "checkpoint_artifact_summaries": checkpoint_artifact_summaries,
        "event_count": len(event_types),
        "event_types": event_types,
        "http_full_content_route_status": _deferred_status(http_full_content_response),
        "filesystem_mutation_status": "not_used",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "semantic_retrieval_status": "not_used",
        "ranking_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }

def _run_terminal_exec_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "terminal-exec-checkpoints")
    api = InProcessServer(root, checkpoint_store=checkpoint_store)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="controlled terminal execution demo")
    run_id = run["run_id"]
    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "terminal_exec",
            "argv": ["printf", "terminal-demo-output"],
        },
    )

    artifacts = api.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1]
    artifact_ref = artifact.ref.to_dict()
    terminal_output = json.loads(api.artifact_store.get_content(artifact.ref))
    events = api.get_events(run_id)
    event_types = [event.event_type for event in events]
    replay_state = RunProjector().rebuild(run_id, api.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(run_id, api.event_store, checkpoint_store)
    final_state = api.get_run_state(run_id)
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    terminal_output_verified = (
        terminal_output.get("argv") == ["printf", "terminal-demo-output"]
        and terminal_output.get("exit_code") == 0
        and terminal_output.get("stdout") == "terminal-demo-output"
        and terminal_output.get("stderr") == ""
        and terminal_output.get("shell") is False
    )
    terminal_exec_ok = (
        result["status"] == "completed"
        and artifact.artifact_type == "terminal_output"
        and "action.started" in event_types
        and "artifact.created" in event_types
        and "action.completed" in event_types
        and replay_state.status == "completed"
        and terminal_output_verified
        and replay_ok
        and checkpoint_ok
    )

    return {
        "scenario": "terminal-exec",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "terminal_exec_ok": terminal_exec_ok,
        "terminal_command": "printf",
        "terminal_output_artifact_ref": artifact_ref,
        "terminal_artifact_summary": artifact.summary,
        "terminal_artifact_type": artifact.artifact_type,
        "terminal_output_verified": terminal_output_verified,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "interactive_shell_status": "not_used",
        "network_listener_status": "not_used",
        "model_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


class _DemoCompletedProcess:
    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _RecordingProcessRunner:
    def __init__(self, result: _DemoCompletedProcess) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> _DemoCompletedProcess:
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return self.result


class _DemoToolCallProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, responses: list[LLMToolCallResponse] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses) if responses is not None else [_demo_tool_call_response()]

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "max_tokens": max_tokens,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return _demo_tool_call_response()


class _DemoProductChatProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(
        self,
        responses: list[LLMToolCallResponse | LLMFinalAnswerResponse] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses) if responses is not None else [
            _demo_final_answer_response()
        ]

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse | LLMFinalAnswerResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "max_tokens": max_tokens,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return _demo_final_answer_response()


def _demo_tool_call_response(
    call_id: str = "call_demo_provider_route",
    prompt: str = "LLM_PROVIDER_DEMO_PROMPT_SHOULD_NOT_LEAK",
    summary: str = "provider-selected Codex demo",
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider=_DemoToolCallProvider.provider,
        model=_DemoToolCallProvider.model,
        finish_reason="tool_calls",
        usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={
                "prompt": prompt,
                "summary": summary,
            },
        ),
    )


def _demo_terminal_tool_call_response() -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="tool_calls",
        usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        tool_call=LLMToolCall(
            call_id="call_demo_terminal_tool",
            tool_name="terminal_exec",
            arguments={
                "argv": ["printf", "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK"],
                "summary": "provider-selected terminal command",
            },
        ),
    )


def _demo_final_answer_response() -> LLMFinalAnswerResponse:
    return LLMFinalAnswerResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="stop",
        usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        content="APP_ENTRY_DEMO_FINAL_ANSWER_SHOULD_NOT_LEAK",
    )


def _demo_terminal_final_answer_response() -> LLMFinalAnswerResponse:
    return LLMFinalAnswerResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="stop",
        usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        content="TERMINAL_TOOL_LOOP_FINAL_ANSWER_SHOULD_NOT_LEAK",
    )


def _demo_product_chat_ready_preflight() -> dict[str, Any]:
    return {
        "ready": True,
        "gate": "passed",
        "category": "ready",
        "status": "completed",
        "reason_code": "llm_product_chat_live_smoke_completed",
        "summary": "product-chat smoke completed direct answer, approval pause, and resume final answer",
        "next_step": "use this as a dev-only preflight before product-chat app entry",
    }


def _demo_product_chat_blocked_preflight() -> dict[str, Any]:
    return {
        "ready": False,
        "gate": "blocked",
        "category": "missing_configuration",
        "status": "missing_configuration",
        "reason_code": "llm_provider_not_configured",
        "summary": "LLM provider is not configured",
        "next_step": "configure provider credentials before product-chat app entry",
    }


def _run_model_tool_bridge_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "model-tool-bridge-checkpoints")
    runner = _RecordingProcessRunner(
        _DemoCompletedProcess(
            stdout='{"event":"task_complete","message":"MODEL_BRIDGE_OUTPUT_SHOULD_NOT_LEAK"}\n'
        )
    )
    app = create_codex_cli_http_app(
        root,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(root / "model-tool-workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=23,
            max_output_bytes=4096,
        ),
        checkpoint_store=checkpoint_store,
        process_runner=runner,
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="model tool bridge demo")
    run_id = run["run_id"]
    catalog = app.server.get_model_tool_catalog()
    catalog_tool_names = [
        tool["name"]
        for tool in catalog.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]

    pending = submit_model_tool_call(
        app,
        run_id,
        {
            "tool_name": "codex_task",
            "arguments": {
                "prompt": "MODEL_BRIDGE_PROMPT_SHOULD_NOT_LEAK",
                "summary": "model-selected Codex demo",
            },
        },
    )
    pending_event_types = [event.event_type for event in app.server.get_events(run_id)]
    approval_id = pending["approval_id"]
    approval_pending_before_execution = (
        pending["status"] == "pending_user_approval"
        and "approval.requested" in pending_event_types
        and not _ACTION_EXECUTION_EVENTS.intersection(pending_event_types)
        and runner.calls == []
    )

    resolve_response = app.request(
        "POST",
        f"/runs/{run_id}/approvals/{approval_id}/resolve",
        {
            "resolution": "approved",
            "reason": "model tool bridge demo",
            "resolver": "developer_demo",
        },
    )
    final_state = app.server.get_run_state(run_id)
    events = app.server.get_events(run_id)
    event_types = [event.event_type for event in events]
    artifacts = app.server.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1]
    transcript = json.loads(app.server.artifact_store.get_content(artifact.ref))

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    approval_ok = (
        resolve_response.status_code == 200
        and "approval.resolved" in event_types
        and event_types.index("approval.requested") < event_types.index("approval.resolved")
    )
    codex_started_after_approval = (
        len(runner.calls) == 1
        and "action.started" in event_types
        and event_types.index("approval.resolved") < event_types.index("action.started")
        and runner.calls[0]["kwargs"].get("shell") is False
    )
    codex_output_verified = (
        transcript.get("stdout")
        == '{"event":"task_complete","message":"MODEL_BRIDGE_OUTPUT_SHOULD_NOT_LEAK"}\n'
        and transcript.get("exit_code") == 0
        and transcript.get("shell") is False
    )
    model_tool_bridge_ok = (
        "codex_task" in catalog_tool_names
        and pending["tool_name"] == "codex_task"
        and approval_pending_before_execution
        and approval_ok
        and codex_started_after_approval
        and artifact.artifact_type == "codex_task_transcript"
        and codex_output_verified
        and replay_ok
        and checkpoint_ok
        and replay_state.status == "completed"
    )

    return {
        "scenario": "model-tool-bridge",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "model_tool_bridge_ok": model_tool_bridge_ok,
        "model_tool_name": "codex_task",
        "model_tool_result_status": pending["status"],
        "catalog_contains_codex_task": "codex_task" in catalog_tool_names,
        "catalog_tool_names": catalog_tool_names,
        "approval_pending_before_execution": approval_pending_before_execution,
        "approval_ok": approval_ok,
        "codex_started_after_approval": codex_started_after_approval,
        "codex_call_count": len(runner.calls),
        "codex_artifact_ref": artifact.ref.to_dict(),
        "codex_artifact_summary": artifact.summary,
        "codex_artifact_type": artifact.artifact_type,
        "codex_output_verified": codex_output_verified,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "model_status": "deterministic_decision_only",
        "real_llm_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _run_llm_provider_route_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "llm-provider-route-checkpoints")
    provider = _DemoToolCallProvider()
    runner = _RecordingProcessRunner(
        _DemoCompletedProcess(
            stdout='{"event":"task_complete","message":"LLM_PROVIDER_DEMO_OUTPUT_SHOULD_NOT_LEAK"}\n'
        )
    )
    app = create_llm_provider_http_app(
        root,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(root / "llm-provider-workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=23,
            max_output_bytes=4096,
        ),
        checkpoint_store=checkpoint_store,
        provider=provider,
        process_runner=runner,
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="llm provider route demo")
    run_id = run["run_id"]
    route = f"/runs/{run_id}/llm/tool-calls"
    request_body = {
        "messages": [
            {"role": "system", "content": "Select exactly one provided Isotope tool."},
            {
                "role": "user",
                "content": "Turn this request into a controlled Codex task. "
                "LLM_PROVIDER_DEMO_MESSAGE_SHOULD_NOT_LEAK",
            },
        ],
        "max_tokens": 96,
        "idempotency_key": "llm-provider-route-demo",
    }

    first_response = app.request("POST", route, request_body)
    second_response = app.request("POST", route, request_body)
    route_body = first_response.body if isinstance(first_response.body, dict) else {}
    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    provider_tools = [
        tool["name"]
        for call in provider.calls[:1]
        for tool in call.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    action_execution_started = bool(_ACTION_EXECUTION_EVENTS.intersection(event_types))
    approval_pending_before_execution = (
        first_response.status_code == 202
        and route_body.get("status") == "pending_user_approval"
        and "approval.requested" in event_types
        and not action_execution_started
        and runner.calls == []
    )
    idempotency_replay_ok = (
        second_response.status_code == first_response.status_code
        and second_response.body == first_response.body
        and len(provider.calls) == 1
        and event_types.count("approval.requested") == 1
    )
    provider_route_ok = (
        "codex_task" in provider_tools
        and route_body.get("tool_name") == "codex_task"
        and approval_pending_before_execution
        and idempotency_replay_ok
        and replay_ok
        and checkpoint_ok
    )

    return {
        "scenario": "llm-provider-route",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "provider_route_ok": provider_route_ok,
        "provider_name": provider.provider,
        "provider_model": provider.model,
        "provider_tool_name": route_body.get("tool_name"),
        "provider_call_count": len(provider.calls),
        "provider_seen_tool_names": provider_tools,
        "route_status_code": first_response.status_code,
        "route_result_status": route_body.get("status"),
        "provider_tool_call_id": route_body.get("provider_tool_call_id"),
        "approval_pending_before_execution": approval_pending_before_execution,
        "codex_started_before_approval": len(runner.calls) > 0,
        "codex_call_count": len(runner.calls),
        "idempotency_replay_ok": idempotency_replay_ok,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "real_llm_status": "fake_provider",
        "provider_status": "fake_tool_call",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _run_llm_tool_result_loop_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "llm-tool-result-loop-checkpoints")
    provider = _DemoToolCallProvider(
        [
            _demo_tool_call_response(),
            _demo_tool_call_response(
                "call_demo_followup_route",
                "LLM_TOOL_RESULT_FOLLOWUP_PROMPT_SHOULD_NOT_LEAK",
                "provider-selected follow-up Codex demo",
            ),
        ]
    )
    runner = _RecordingProcessRunner(
        _DemoCompletedProcess(
            stdout='{"event":"task_complete","message":"LLM_TOOL_RESULT_DEMO_OUTPUT_SHOULD_NOT_LEAK"}\n'
        )
    )
    app = create_llm_provider_http_app(
        root,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(root / "llm-tool-result-workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=23,
            max_output_bytes=4096,
        ),
        checkpoint_store=checkpoint_store,
        provider=provider,
        process_runner=runner,
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="llm tool result loop demo")
    run_id = run["run_id"]
    route = f"/runs/{run_id}/llm/tool-calls"
    request_body = {
        "messages": [
            {"role": "system", "content": "Select exactly one provided Isotope tool."},
            {
                "role": "user",
                "content": "Turn this request into a controlled Codex task. "
                "LLM_TOOL_RESULT_DEMO_MESSAGE_SHOULD_NOT_LEAK",
            },
        ],
        "max_tokens": 96,
        "idempotency_key": "llm-tool-result-loop-demo",
        "complete_run": False,
    }

    route_response = app.request("POST", route, request_body)
    route_body = route_response.body if isinstance(route_response.body, dict) else {}
    approval_id = route_body.get("approval_id")
    if isinstance(approval_id, str) and approval_id:
        approval_response = app.request(
            "POST",
            f"/runs/{run_id}/approvals/{approval_id}/resolve",
            {
                "resolution": "approved",
                "reason": "approve provider-selected Codex task for tool result demo",
                "resolver": "reviewer",
            },
        )
    else:
        approval_response = app.request("POST", f"/runs/{run_id}/approvals/missing/resolve", {})
    approval_body = approval_response.body if isinstance(approval_response.body, dict) else {}
    tool_result_message = build_llm_tool_result_message(route_body, approval_body)
    tool_result_content = json.loads(tool_result_message["content"])
    event_types_before_followup = [event.event_type for event in app.server.get_events(run_id)]
    first_run_status_after_approval = ""
    if isinstance(approval_body.get("run_state"), dict):
        first_run_status_after_approval = str(approval_body["run_state"].get("status", ""))
    followup = submit_llm_tool_result_followup(
        app,
        run_id,
        provider,
        request_body["messages"],
        route_body,
        approval_body,
        max_tokens=96,
    )
    event_types_after_followup = [event.event_type for event in app.server.get_events(run_id)]
    followup_action_submitted = event_types_after_followup != event_types_before_followup
    followup_tool_result = followup.get("tool_result") if isinstance(followup.get("tool_result"), dict) else {}
    followup_approval_id = followup_tool_result.get("approval_id")
    if isinstance(followup_approval_id, str) and followup_approval_id:
        second_approval_response = app.request(
            "POST",
            f"/runs/{run_id}/approvals/{followup_approval_id}/resolve",
            {
                "resolution": "approved",
                "reason": "approve follow-up provider-selected Codex task",
                "resolver": "reviewer",
            },
        )
    else:
        second_approval_response = app.request(
            "POST",
            f"/runs/{run_id}/approvals/missing-followup/resolve",
            {},
        )
    second_approval_body = (
        second_approval_response.body if isinstance(second_approval_response.body, dict) else {}
    )

    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    artifacts = app.server.artifact_store.list_artifacts(run_id)
    artifact = artifacts[-1] if artifacts else None
    transcripts = [
        json.loads(app.server.artifact_store.get_content(stored_artifact.ref))
        for stored_artifact in artifacts
    ]
    provider_tools = [
        tool["name"]
        for call in provider.calls[:1]
        for tool in call.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]

    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    approval_ok = (
        approval_response.status_code == 200
        and approval_body.get("tool_execution_status") == "completed"
        and first_run_status_after_approval == "running"
        and "approval.resolved" in event_types_before_followup
        and "run.completed" not in event_types_before_followup
    )
    codex_started_after_approval = (
        len(runner.calls) >= 1
        and "approval.resolved" in event_types_before_followup
        and "action.started" in event_types_before_followup
        and event_types_before_followup.index("approval.resolved")
        < event_types_before_followup.index("action.started")
    )
    artifact_ref = tool_result_content.get("artifact_ref")
    tool_result_message_ready = (
        tool_result_message.get("role") == "tool"
        and tool_result_message.get("tool_call_id") == route_body.get("provider_tool_call_id")
        and tool_result_message.get("name") == route_body.get("tool_name")
        and tool_result_content.get("status") == "completed"
        and artifact_ref == approval_body.get("artifact_ref")
        and "LLM_TOOL_RESULT_DEMO_OUTPUT_SHOULD_NOT_LEAK" not in repr(tool_result_message)
    )
    codex_output_verified = (
        len(transcripts) == 2
        and all(
            transcript.get("stdout")
            == '{"event":"task_complete","message":"LLM_TOOL_RESULT_DEMO_OUTPUT_SHOULD_NOT_LEAK"}\n'
            and transcript.get("exit_code") == 0
            for transcript in transcripts
        )
    )
    second_approval_ok = (
        second_approval_response.status_code == 200
        and second_approval_body.get("status") == "completed"
        and second_approval_body.get("tool_execution_status") == "completed"
        and isinstance(second_approval_body.get("artifact_ref"), dict)
    )
    second_codex_started_after_approval = (
        len(runner.calls) == 2
        and event_types_after_followup.count("action.started") == 1
        and event_types.count("action.started") == 2
        and event_types.count("approval.resolved") == 2
    )
    followup_submission_ok = (
        followup.get("status") == "pending_user_approval"
        and followup.get("provider_tool_call_id") == "call_demo_followup_route"
        and followup.get("tool_name") == "codex_task"
        and followup.get("submission_status") == "pending_user_approval"
        and followup.get("tool_result_status") == "completed"
        and followup.get("tool_result_artifact_ref") == artifact_ref
        and len(provider.calls) == 2
        and followup_action_submitted
        and event_types_after_followup.count("approval.requested") == 2
        and event_types_after_followup.count("action.started") == 1
        and "run.completed" not in event_types_after_followup
        and "LLM_TOOL_RESULT_FOLLOWUP_PROMPT_SHOULD_NOT_LEAK" not in repr(followup)
    )
    tool_result_loop_ok = (
        "codex_task" in provider_tools
        and route_body.get("tool_name") == "codex_task"
        and route_body.get("status") == "pending_user_approval"
        and approval_ok
        and codex_started_after_approval
        and codex_output_verified
        and tool_result_message_ready
        and followup_submission_ok
        and second_approval_ok
        and second_codex_started_after_approval
        and replay_ok
        and checkpoint_ok
        and replay_state.status == "completed"
        and event_types.count("run.completed") == 1
    )

    return {
        "scenario": "llm-tool-result-loop",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "tool_result_loop_ok": tool_result_loop_ok,
        "provider_name": provider.provider,
        "provider_model": provider.model,
        "provider_tool_name": route_body.get("tool_name"),
        "provider_call_count": len(provider.calls),
        "provider_seen_tool_names": provider_tools,
        "route_status_code": route_response.status_code,
        "route_result_status": route_body.get("status"),
        "provider_tool_call_id": route_body.get("provider_tool_call_id"),
        "approval_pending_before_execution": route_body.get("status") == "pending_user_approval",
        "approval_ok": approval_ok,
        "codex_started_after_approval": codex_started_after_approval,
        "codex_call_count": len(runner.calls),
        "codex_artifact_type": artifact.artifact_type if artifact is not None else "",
        "codex_output_verified": codex_output_verified,
        "tool_result_message_ready": tool_result_message_ready,
        "tool_result_message_role": tool_result_message.get("role"),
        "tool_result_message_tool_call_id": tool_result_message.get("tool_call_id"),
        "tool_result_content_status": tool_result_content.get("status"),
        "tool_result_artifact_ref": artifact_ref,
        "tool_result_artifact_ref_present": isinstance(artifact_ref, dict),
        "followup_provider_call_count": len(provider.calls),
        "followup_result_status": followup.get("status"),
        "followup_provider_tool_call_id": followup.get("provider_tool_call_id"),
        "followup_tool_name": followup.get("tool_name"),
        "followup_submission_status": followup.get("submission_status"),
        "followup_action_submitted": followup_action_submitted,
        "first_run_status_after_approval": first_run_status_after_approval,
        "second_approval_ok": second_approval_ok,
        "second_codex_started_after_approval": second_codex_started_after_approval,
        "tool_result_loop_status": "two_tool_actions_completed",
        "multi_tool_loop_status": "two_step_demo_only",
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "real_llm_status": "fake_provider",
        "provider_status": "fake_tool_call",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _run_llm_product_chat_app_entry_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "llm-product-chat-app-entry-checkpoints")
    provider = _DemoProductChatProvider()
    runner = _RecordingProcessRunner(
        _DemoCompletedProcess(
            stdout='{"event":"task_complete","message":"APP_ENTRY_DEMO_STDOUT_SHOULD_NOT_LEAK"}\n'
        )
    )
    app = create_llm_product_chat_http_app(
        root,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(root / "llm-product-chat-app-entry-workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=23,
            max_output_bytes=4096,
        ),
        checkpoint_store=checkpoint_store,
        provider=provider,
        process_runner=runner,
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="llm product chat app entry demo")
    run_id = run["run_id"]
    before_blocked_events = [event.event_type for event in app.server.get_events(run_id)]

    blocked_response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=_demo_product_chat_blocked_preflight(),
        system_message="Use the product-chat app entry.",
        user_message="APP_ENTRY_DEMO_BLOCKED_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=64,
    )
    after_blocked_events = [event.event_type for event in app.server.get_events(run_id)]
    blocked_body = blocked_response.body if isinstance(blocked_response.body, dict) else {}
    blocked_no_side_effects = (
        blocked_response.status_code == 412
        and blocked_body.get("status") == "blocked_by_preflight"
        and provider.calls == []
        and runner.calls == []
        and after_blocked_events == before_blocked_events
    )

    ready_preflight = _demo_product_chat_ready_preflight()
    ready_response = submit_llm_product_chat_user_message_with_preflight(
        app,
        run_id,
        preflight=ready_preflight,
        system_message="Use the product-chat app entry.",
        user_message="APP_ENTRY_DEMO_READY_MESSAGE_SHOULD_NOT_LEAK",
        max_tokens=72,
    )
    ready_body = ready_response.body if isinstance(ready_response.body, dict) else {}

    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    provider_tools = [
        tool["name"]
        for call in provider.calls[:1]
        for tool in call.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]
    ready_forwarded_to_route = (
        ready_response.status_code == 200
        and ready_body.get("status") == "completed"
        and ready_body.get("provider_status") == "final_answer"
        and len(provider.calls) == 1
        and provider.calls[0].get("max_tokens") == 72
        and "codex_task" in provider_tools
        and runner.calls == []
        and "artifact.created" in event_types
        and "run.completed" in event_types
    )
    app_entry_preflight_ok = (
        blocked_no_side_effects
        and ready_preflight.get("ready") is True
        and ready_forwarded_to_route
        and replay_ok
        and checkpoint_ok
    )
    user_message_entry_ok = (
        ready_forwarded_to_route
        and len(provider.calls) == 1
        and provider.calls[0].get("messages")
        == [
            {"role": "system", "content": "Use the product-chat app entry."},
            {"role": "user", "content": "APP_ENTRY_DEMO_READY_MESSAGE_SHOULD_NOT_LEAK"},
        ]
    )

    return {
        "scenario": "llm-product-chat-app-entry",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "app_entry_preflight_ok": app_entry_preflight_ok,
        "user_message_entry_ok": user_message_entry_ok,
        "blocked_status_code": blocked_response.status_code,
        "blocked_result_status": blocked_body.get("status"),
        "blocked_no_side_effects": blocked_no_side_effects,
        "blocked_preflight_category": blocked_body.get("preflight", {}).get("category"),
        "ready_preflight_ready": ready_preflight.get("ready") is True,
        "ready_status_code": ready_response.status_code,
        "ready_result_status": ready_body.get("status"),
        "ready_provider_status": ready_body.get("provider_status"),
        "ready_forwarded_to_route": ready_forwarded_to_route,
        "assistant_message_present": isinstance(ready_body.get("assistant_message"), dict),
        "artifact_ref_present": isinstance(ready_body.get("artifact_ref"), dict),
        "provider_name": provider.provider,
        "provider_model": provider.model,
        "provider_seen_tool_names": provider_tools,
        "provider_call_count": len(provider.calls),
        "codex_call_count": len(runner.calls),
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "real_llm_status": "fake_provider",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _run_llm_terminal_tool_loop_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FileCheckpointStore(root / "llm-terminal-tool-loop-checkpoints")
    server = InProcessServer(root, checkpoint_store=checkpoint_store)
    provider = _DemoProductChatProvider(
        [_demo_terminal_tool_call_response(), _demo_terminal_final_answer_response()]
    )
    app = HttpApiApp(
        root,
        server=server,
        enable_llm_product_chat_route=True,
        llm_tool_call_provider=provider,
        llm_tool_names=("terminal_exec",),
    )

    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="llm terminal tool loop demo")
    run_id = run["run_id"]
    route = f"/runs/{run_id}/llm/chat-turns"
    messages = [
        {"role": "system", "content": "Use the terminal tool when needed."},
        {
            "role": "user",
            "content": "Run the safe terminal check. TERMINAL_TOOL_LOOP_MESSAGE_SHOULD_NOT_LEAK",
        },
    ]

    first_response = app.request(
        "POST",
        route,
        {
            "messages": messages,
            "max_tokens": 96,
            "complete_run": False,
        },
    )
    first_body = first_response.body if isinstance(first_response.body, dict) else {}
    tool_result_message = build_llm_tool_result_message(first_body, first_body)
    tool_result_content = json.loads(tool_result_message["content"])
    first_artifacts = app.server.artifact_store.list_artifacts(run_id)
    terminal_artifact = first_artifacts[-1] if first_artifacts else None
    terminal_content = (
        json.loads(app.server.artifact_store.get_content(terminal_artifact.ref))
        if terminal_artifact is not None
        else {}
    )

    second_response = app.request(
        "POST",
        route,
        {
            "messages": messages,
            "llm_result": first_body,
            "tool_execution_result": first_body,
            "max_tokens": 96,
        },
    )
    second_body = second_response.body if isinstance(second_response.body, dict) else {}
    final_state = app.server.get_run_state(run_id)
    event_types = [event.event_type for event in app.server.get_events(run_id)]
    replay_state = RunProjector().rebuild(run_id, app.server.event_store)
    checkpoint = RunProjector().save_checkpoint(run_id, app.server.event_store, checkpoint_store)
    checkpoint_state = RunProjector().rebuild_with_checkpoint(
        run_id,
        app.server.event_store,
        checkpoint_store,
    )
    replay_ok = asdict(replay_state) == asdict(final_state)
    checkpoint_ok = asdict(checkpoint_state) == asdict(replay_state)
    provider_tools = [
        tool["name"]
        for call in provider.calls[:1]
        for tool in call.get("tools", [])
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]
    artifact_ref = tool_result_content.get("artifact_ref")
    terminal_output_verified = (
        terminal_content.get("stdout") == "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK"
        and terminal_content.get("shell") is False
        and terminal_content.get("exit_code") == 0
    )
    tool_result_message_ready = (
        tool_result_message.get("role") == "tool"
        and tool_result_message.get("tool_call_id") == first_body.get("provider_tool_call_id")
        and tool_result_message.get("name") == "terminal_exec"
        and tool_result_content.get("status") == "completed"
        and isinstance(artifact_ref, dict)
        and "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK" not in repr(tool_result_message)
    )
    terminal_tool_loop_ok = (
        first_response.status_code == 200
        and first_body.get("status") == "running"
        and first_body.get("tool_name") == "terminal_exec"
        and first_body.get("tool_execution_status") == "completed"
        and second_response.status_code == 200
        and second_body.get("status") == "completed"
        and second_body.get("provider_status") == "final_answer"
        and provider_tools == ["terminal_exec"]
        and len(provider.calls) == 2
        and terminal_output_verified
        and tool_result_message_ready
        and event_types.count("approval.requested") == 0
        and event_types.count("action.started") == 2
        and event_types.count("run.completed") == 1
        and replay_ok
        and checkpoint_ok
    )

    return {
        "scenario": "llm-terminal-tool-loop",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": replay_state.status,
        "transport": "in_process",
        "terminal_tool_loop_ok": terminal_tool_loop_ok,
        "provider_name": provider.provider,
        "provider_model": provider.model,
        "provider_tool_name": first_body.get("tool_name"),
        "provider_seen_tool_names": provider_tools,
        "provider_call_count": len(provider.calls),
        "terminal_command": "printf",
        "terminal_action_status": first_body.get("tool_execution_status"),
        "terminal_output_verified": terminal_output_verified,
        "tool_result_message_ready": tool_result_message_ready,
        "tool_result_message_role": tool_result_message.get("role"),
        "tool_result_message_tool_call_id": tool_result_message.get("tool_call_id"),
        "tool_result_content_status": tool_result_content.get("status"),
        "tool_result_artifact_ref": artifact_ref,
        "tool_result_artifact_ref_present": isinstance(artifact_ref, dict),
        "final_answer_status": second_body.get("status"),
        "final_answer_artifact_ref_present": isinstance(second_body.get("artifact_ref"), dict),
        "codex_call_count": 0,
        "replay_ok": replay_ok,
        "checkpoint_ok": checkpoint_ok,
        "checkpoint_basis_event_id": checkpoint["basis_event_id"],
        "event_count": len(event_types),
        "event_types": event_types,
        "real_llm_status": "fake_provider",
        "provider_status": "fake_tool_call",
        "network_listener_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
    }


def _latest_approval_id(events: list[Any]) -> str:
    for event in reversed(events):
        if event.event_type == "approval.requested":
            approval_id = event.payload.get("approval_id")
            if isinstance(approval_id, str):
                return approval_id
    return ""




if __name__ == "__main__":
    raise SystemExit(main())
