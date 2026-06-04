"""LLM terminal-tool loop developer demo scenario."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .fakes import (
    _DemoProductChatProvider,
    _demo_terminal_final_answer_response,
    _demo_terminal_tool_call_response,
)
from ...interfaces.http import HttpApiApp
from ...llm.provider import build_llm_tool_result_message
from ...platform.state.checkpoint_store import FileCheckpointStore
from ...platform.state.projector import RunProjector
from ...runtime.in_process import InProcessServer


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
        "memory_status": "active",
        "memory_query_status": "unavailable",
    }
