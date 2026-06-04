"""LLM tool-result loop developer demo scenario."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .fakes import (
    _DemoToolCallProvider,
    _demo_final_answer_response,
    _demo_tool_call_response,
)
from ..demo_terminal_scenarios import _DemoCompletedProcess, _RecordingProcessRunner
from ...integrations.codex import server as codex_server
from ...interfaces.http import create_llm_provider_http_app
from ...llm.provider import build_llm_tool_result_message, submit_llm_tool_result_followup
from ...platform.state.checkpoint_store import FileCheckpointStore
from ...platform.state.projector import RunProjector


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
        "memory_status": "active",
        "memory_query_status": "unavailable",
    }
