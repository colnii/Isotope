"""Local Linux implementation of the terminal backend protocol."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from isotope.capabilities.tools.terminal import (
    cap_terminal_output,
    terminal_grant_from,
    terminal_grant_policy_violation,
    validate_argv,
)

from .backend_types import (
    TerminalBackendOutputArtifact,
    TerminalBackendRequest,
    TerminalBackendResult,
)


class LinuxSystemTerminalRunner:
    """Run approved argv requests on the local Linux system terminal."""

    def __init__(self, execution_root: Path):
        self.execution_root = Path(execution_root).resolve()

    def run(self, request: TerminalBackendRequest) -> TerminalBackendResult:
        if not isinstance(request, TerminalBackendRequest):
            raise TypeError("LinuxSystemTerminalRunner.run requires a TerminalBackendRequest")
        if request.command_request.get("kind") != "exec_argv":
            raise ValueError("linux system terminal runner only supports exec_argv")
        command = validate_argv(request.command_request.get("argv"))
        terminal_grant = terminal_grant_from(request.grants)
        _ensure_linux_system_terminal_grant(command, terminal_grant)
        timeout_seconds = _timeout_seconds(request.budget)
        max_output_bytes = _max_output_bytes(terminal_grant)

        cwd = self._prepare_cwd()
        started_at = _utc_now()
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                env=_sanitized_env(),
                text=True,
                capture_output=True,
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, truncated = cap_terminal_output(
                _timeout_text(exc.stdout),
                _timeout_text(exc.stderr),
                max_output_bytes=max_output_bytes,
            )
            return _system_runner_result(
                request=request,
                command=command,
                cwd=cwd,
                status="timeout",
                reason_code="terminal_system_runner_timeout",
                stdout=stdout,
                stderr=stderr,
                truncated=truncated,
                max_output_bytes=max_output_bytes,
                exit_code=None,
                timed_out=True,
                timeout_seconds=timeout_seconds,
                retryable=True,
                started_at=started_at,
                finished_at=_utc_now(),
            )

        stdout, stderr, truncated = cap_terminal_output(
            completed.stdout,
            completed.stderr,
            max_output_bytes=max_output_bytes,
        )
        status = "completed" if completed.returncode == 0 else "failed"
        reason_code = (
            "terminal_system_runner_completed"
            if completed.returncode == 0
            else "terminal_system_runner_exit_nonzero"
        )
        return _system_runner_result(
            request=request,
            command=command,
            cwd=cwd,
            status=status,
            reason_code=reason_code,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
            max_output_bytes=max_output_bytes,
            exit_code=completed.returncode,
            timed_out=False,
            timeout_seconds=timeout_seconds,
            retryable=False,
            started_at=started_at,
            finished_at=_utc_now(),
        )

    def _prepare_cwd(self) -> Path:
        self.execution_root.mkdir(parents=True, exist_ok=True)
        return self.execution_root



def _system_runner_result(
    *,
    request: TerminalBackendRequest,
    command: list[str],
    cwd: Path,
    status: str,
    reason_code: str,
    stdout: str,
    stderr: str,
    truncated: bool,
    max_output_bytes: int,
    exit_code: int | None,
    timed_out: bool,
    timeout_seconds: int,
    retryable: bool,
    started_at: str,
    finished_at: str,
) -> TerminalBackendResult:
    summary_status = "failed" if status == "timeout" else status
    return TerminalBackendResult(
        backend_session_id=f"linux_system_terminal_{request.execution_id}",
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        summary=f"linux system terminal {summary_status}: {command[0]}",
        output_artifacts=[
            TerminalBackendOutputArtifact(
                artifact_type="terminal_backend_transcript",
                summary="linux system terminal transcript captured",
                content=json.dumps(
                    {
                        "argv": command,
                        "cwd": str(cwd),
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "truncated": truncated,
                        "max_output_bytes": max_output_bytes,
                        "shell": False,
                        "timed_out": timed_out,
                        "timeout_seconds": timeout_seconds,
                    },
                    sort_keys=True,
                ),
            )
        ],
        exit_code=exit_code,
        reason_code=reason_code,
        retryable=retryable,
        resource_usage={},
    )


def _ensure_linux_system_terminal_grant(command: list[str], terminal_grant: dict[str, Any]) -> None:
    violation = terminal_grant_policy_violation(command, terminal_grant)
    if violation is None:
        return
    if violation["reason_code"] in {"terminal_command_not_allowed", "terminal_shell_not_granted"}:
        raise PermissionError(violation["message"])
    raise ValueError(violation["message"])


def _timeout_seconds(budget: dict[str, Any]) -> int:
    value = budget.get("seconds")
    if not isinstance(value, int) or value < 0:
        raise ValueError("linux system terminal runner requires budget.seconds")
    return value


def _max_output_bytes(terminal_grant: dict[str, Any]) -> int:
    value = terminal_grant.get("max_output_bytes", 4096)
    if not isinstance(value, int) or value <= 0:
        raise ValueError("linux system terminal runner requires positive max_output_bytes")
    return value


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _sanitized_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
