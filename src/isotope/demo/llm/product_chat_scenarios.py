"""LLM product-chat app-entry developer demo scenario."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .fakes import (
    _DemoProductChatProvider,
    _demo_product_chat_blocked_preflight,
    _demo_product_chat_ready_preflight,
)
from ..demo_terminal_scenarios import _DemoCompletedProcess, _RecordingProcessRunner
from ...features.chat.flow import submit_llm_product_chat_user_message_with_preflight
from ...integrations.codex import server as codex_server
from ...interfaces.http import create_llm_product_chat_http_app
from ...platform.state.checkpoint_store import FileCheckpointStore
from ...platform.state.projector import RunProjector


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
