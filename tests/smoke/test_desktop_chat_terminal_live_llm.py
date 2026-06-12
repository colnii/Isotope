from __future__ import annotations

import json
import os

import pytest

from isotope.features.supervisor.desktop_chat import stream_desktop_chat_events
from isotope.llm.provider import resolve_llm_chat_provider


_LIVE_ENV = "ISOTOPE_RUN_LIVE_LLM_TERMINAL_CAPACITY_CRUD"


@pytest.mark.skipif(
    os.environ.get(_LIVE_ENV) != "1" or resolve_llm_chat_provider().status != "configured",
    reason=(
        "live terminal capacity CRUD smoke is opt-in and requires "
        "ISOTOPE_LLM_PROVIDER/ISOTOPE_LLM_MODEL provider configuration"
    ),
)
def test_live_llm_desktop_chat_terminal_capacity_crud_under_tmp(tmp_path):
    resolution = resolve_llm_chat_provider()
    if resolution.provider is None:
        pytest.skip(f"live LLM provider unavailable: {resolution.reason_code}")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "tmp").mkdir()
    target = workspace / "tmp" / "isotope-terminal-crud.txt"
    proof = workspace / "tmp" / "isotope-terminal-crud-proof.json"

    question = (
        "Use the terminal.exec capability exactly once. Do not answer directly first. "
        "Run a terminal command in the current workspace that operates only under tmp/. "
        "The command must create tmp/isotope-terminal-crud.txt with content 'created', "
        "read it, update it to 'created-updated', delete tmp/isotope-terminal-crud.txt, "
        "then write tmp/isotope-terminal-crud-proof.json containing JSON with "
        "created/read/updated/deleted all true and final_content 'created-updated'. "
        "After the capability result, answer briefly."
    )

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path / "state",
            cwd=workspace,
            question=question,
            provider=resolution.provider,
            max_tokens=512,
            chat_timeout_seconds=45,
            terminal_approval_mode="yolo",
            terminal_allowed_commands=[],
        )
    )

    terminal_results = [
        event
        for event in events
        if event.event == "capacity_result" and event.payload.get("capacity_id") == "terminal.exec"
    ]
    assert terminal_results, [event.event for event in events]
    assert terminal_results[-1].payload["status"] == "ok"
    assert target.exists() is False
    proof_payload = json.loads(proof.read_text(encoding="utf-8"))
    assert proof_payload == {
        "created": True,
        "read": True,
        "updated": True,
        "deleted": True,
        "final_content": "created-updated",
    }
