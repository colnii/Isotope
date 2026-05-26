"""Model tool bridge and provider route developer demo scenarios."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .fakes import (
    ACTION_EXECUTION_EVENTS as _ACTION_EXECUTION_EVENTS,
    _DemoToolCallProvider,
    _demo_tool_call_response,
)
from ..demo_terminal_scenarios import _DemoCompletedProcess, _RecordingProcessRunner
from ...integrations.codex import server as codex_server
from ...interfaces.http import create_codex_cli_http_app, create_llm_provider_http_app
from ...llm.tool_bridge import submit_model_tool_call
from ...platform.state.checkpoint_store import FileCheckpointStore
from ...platform.state.projector import RunProjector


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
