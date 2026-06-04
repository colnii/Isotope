"""Worker lifecycle execution route helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


WORKER_LIFECYCLE_EXECUTE_PATH = "/worker-lifecycle/execute"


class WorkerLifecycleExecuteError(ValueError):
    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class WorkerLifecycleExecuteServer(Protocol):
    codex_home: Path
    limit: int
    stale_after_seconds: int
    active_within_seconds: int
    lifecycle_run: Any

    def dashboard_payload(self) -> dict[str, Any]: ...


def run_worker_lifecycle_execute(
    server: WorkerLifecycleExecuteServer,
    request: dict[str, Any],
) -> dict[str, Any]:
    requested_command = _required_string(
        request.get("execute_command"),
        "execute_command",
    )
    dashboard_payload = server.dashboard_payload()
    execution = dashboard_payload.get("worker_lifecycle_execution")
    if not isinstance(execution, dict):
        raise WorkerLifecycleExecuteError(
            "worker lifecycle execution is unavailable",
            code="worker_lifecycle_execute_unavailable",
            status_code=400,
        )
    current_command = _optional_string(execution.get("execute_command"))
    if current_command is None:
        raise WorkerLifecycleExecuteError(
            "worker lifecycle execution command is unavailable",
            code="worker_lifecycle_execute_unavailable",
            status_code=400,
        )
    if requested_command != current_command:
        raise WorkerLifecycleExecuteError(
            "worker lifecycle execution command is stale; refresh dashboard",
            code="worker_lifecycle_execute_stale",
            status_code=409,
        )

    command = _worker_lifecycle_execute_argv(server, execution)
    completed = server.lifecycle_run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )
    process = {
        "returncode": completed.returncode,
        "stderr": completed.stderr,
    }
    result_payload = _json_object(completed.stdout)
    if completed.returncode != 0:
        raise WorkerLifecycleExecuteError(
            completed.stderr.strip() or "worker lifecycle execution failed",
            code="worker_lifecycle_execute_failed",
            status_code=502,
        )
    return {
        "status": "ok",
        "execute_command": current_command,
        "command": command,
        "process": process,
        "execution": result_payload,
        "dashboard": server.dashboard_payload(),
    }


def _worker_lifecycle_execute_argv(
    server: WorkerLifecycleExecuteServer,
    execution: dict[str, Any],
) -> list[str]:
    hint = _optional_string(execution.get("execute_hint"))
    if hint not in {"--lifecycle-cleanup-execute", "--merge-dispatch-execute"}:
        raise WorkerLifecycleExecuteError(
            "worker lifecycle execution hint is unsupported",
            code="worker_lifecycle_execute_unavailable",
            status_code=400,
        )
    return [
        "isotope-supervisor",
        "loop",
        "--codex-home",
        str(server.codex_home),
        "--limit",
        str(server.limit),
        "--stale-after",
        str(server.stale_after_seconds),
        "--active-within",
        str(server.active_within_seconds),
        "--iterations",
        "1",
        "--json",
        hint,
    ]


def _json_object(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"raw_stdout": raw}
    return payload if isinstance(payload, dict) else {"raw_stdout": raw}


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerLifecycleExecuteError(
            f"{field} must not be empty",
            code="worker_lifecycle_execute_invalid_request",
            status_code=400,
        )
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
