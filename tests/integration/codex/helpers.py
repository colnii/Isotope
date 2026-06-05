from __future__ import annotations

import argparse
import json
import shlex
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from isotope.features.supervisor.runner import (
    EXECUTABLE_ADVICE_TEXT,
    main as supervisor_main,
)

NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
NON_STALE_SECONDS = "999999999"
STATUS_REQUEST_TEXT: str = EXECUTABLE_ADVICE_TEXT["send_status"]
CONTINUE_REQUEST_TEXT: str = EXECUTABLE_ADVICE_TEXT["send_continue"]
EXISTING_WORKSPACE: str = str(Path(__file__).resolve().parents[2])


def _runner_args(codex_home: Path) -> argparse.Namespace:
    return argparse.Namespace(
        codex_home=str(codex_home),
        max_continue_count=0,
        max_run_minutes=0,
        prompt_cooldown=0,
        worker_codex_model=None,
        worker_codex_config=[],
        worker_profile="coding",
    )


def _codex_operation_context_result(executed: dict) -> dict:
    assert executed["kind"] == "call_capacity"
    assert executed["capacity_id"] == "supervisor.codex_operation"
    assert executed["operation"] == "request_context"
    action_result = executed["agent_loop"]["step_result"]["action_result"]
    return action_result["capability_run"]["operation_result"]["context_result"]


def _supervisor_send_command(name: str, text: str) -> str:
    return shlex.join(["isotope-supervisor", "send", "--name", name, "--text", text])


def _tmux_send_calls(
    text: str,
    *,
    buffer_name: str = "isotope-supervisor-managed-001",
    target: str = "isotope-lane-a",
) -> list[list[str]]:
    return [
        ["tmux", "set-buffer", "-b", buffer_name, "--", text],
        ["tmux", "paste-buffer", "-d", "-b", buffer_name, "-t", target],
        ["tmux", "send-keys", "-t", target, "C-m"],
    ]


def _event(timestamp: str, type_: str, payload: dict[str, object]) -> dict[str, object]:
    return {"timestamp": timestamp, "type": type_, "payload": payload}


def _user_message(timestamp: str, text: str) -> dict[str, object]:
    return _event(
        timestamp,
        "response_item",
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    )


def _assistant_message(timestamp: str, text: str) -> dict[str, object]:
    return _event(
        timestamp,
        "response_item",
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        },
    )


# ---------------------------------------------------------------------------
# Test fixture helpers — shared across test files
# ---------------------------------------------------------------------------

def _add_supervisor_goal(
    capsys,
    *,
    codex_home: Path,
    workspace: Path,
    goal: str,
    target_name: str,
) -> dict[str, object]:
    exit_code = supervisor_main(
        [
            "goal",
            "add",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            goal,
            "--target-name",
            target_name,
            "--json",
        ]
    )
    assert exit_code == 0
    return json.loads(capsys.readouterr().out)["goal"]


def _append_supervisor_goal_status(
    codex_home: Path,
    *,
    goal_id: str,
    status: str,
    target_name: str,
    summary: str,
    next_step: str,
) -> None:
    goals_path = codex_home / "supervisor" / "goals.jsonl"
    with goals_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event": "supervisor_goal_status",
                    "goal_id": goal_id,
                    "status": status,
                    "target_name": target_name,
                    "summary": summary,
                    "next": next_step,
                    "created_at": NOW.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def _write_session(
    codex_home: Path,
    relative_path: str,
    *,
    session_id: str,
    cwd: str,
    events: list[dict[str, object]],
    meta: dict[str, object] | None = None,
) -> Path:
    path = codex_home / "sessions" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "timestamp": "2026-05-16T11:45:00Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": cwd,
                "cli_version": "0.130.0",
                "model_provider": "openai",
                **(meta or {}),
            },
        },
        *events,
    ]
    path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )
    return path


def _write_session_index(
    codex_home: Path,
    *,
    session_id: str,
    thread_name: str,
    updated_at: str = "2026-05-16T11:59:20Z",
) -> None:
    path = codex_home / "session_index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "id": session_id,
        "thread_name": thread_name,
        "updated_at": updated_at,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def _write_state_threads(codex_home: Path, *, session_id: str, title: str) -> None:
    path = codex_home / "state_5.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "create table threads (id text primary key, title text, updated_at integer)"
        )
        connection.execute(
            "insert into threads (id, title, updated_at) values (?, ?, ?)",
            (session_id, title, 1778324108),
        )
        connection.commit()
    finally:
        connection.close()


def _write_managed_tmux_record(
    codex_home: Path,
    *,
    workspace: Path,
    append: bool = False,
    name: str = "lane-a",
    record_id: str = "managed-001",
    tmux_session: str = "isotope-lane-a",
) -> None:
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with registry_path.open(mode, encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "record_id": record_id,
                    "name": name,
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "new-session", "-d", "-s", tmux_session],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(
                        codex_home / "supervisor" / "logs" / f"{record_id}.log"
                    ),
                    "status": "launched",
                    "backend": "tmux",
                    "tmux_session": tmux_session,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _record_cleanup_lifecycle_execution(
    codex_home: Path,
    *,
    lifecycle_decision: str,
    reason: str = "",
) -> None:
    from isotope.features.supervisor.state.worker_lifecycle import (
        record_worker_lifecycle_decision,
    )

    record_worker_lifecycle_decision(
        codex_home=codex_home,
        worker_id="test-worker",
        decision=lifecycle_decision,
        reason=reason,
    )
