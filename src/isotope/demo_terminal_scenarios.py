"""Terminal execution developer demo scenario."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .platform.state.checkpoint_store import FileCheckpointStore
from .platform.state.projector import RunProjector
from .runtime.in_process import InProcessServer

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
