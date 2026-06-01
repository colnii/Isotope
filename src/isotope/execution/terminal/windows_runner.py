"""Local Windows implementation of the terminal backend protocol."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from isotope.capabilities.tools.terminal import cap_terminal_output, terminal_grant_from, validate_argv

from .backend_types import (
    TerminalBackendOutputArtifact,
    TerminalBackendRequest,
    TerminalBackendResult,
)


WINDOWS_PROFILE_BACKED_COMMANDS = {"npm", "pnpm", "yarn", "npx"}
WINDOWS_REJECTED_SCRIPT_EXTENSIONS = {".cmd", ".bat"}
ExecutableResolver = Callable[[str], str | None]
WindowsProcessRunner = Callable[..., "WindowsTerminalProcessResult"]
WindowsCleanupProcessTree = Callable[[int | None], dict[str, Any]]


@dataclass(frozen=True)
class WindowsTerminalProcessResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    process_id: int | None = None
    start_error: str | None = None

    def __post_init__(self) -> None:
        if self.exit_code is not None and not isinstance(self.exit_code, int):
            raise ValueError("exit_code must be an int or None")
        if not isinstance(self.stdout, str):
            raise ValueError("stdout must be a string")
        if not isinstance(self.stderr, str):
            raise ValueError("stderr must be a string")
        if not isinstance(self.timed_out, bool):
            raise ValueError("timed_out must be a bool")
        if self.process_id is not None and not isinstance(self.process_id, int):
            raise ValueError("process_id must be an int or None")
        if self.start_error is not None and not isinstance(self.start_error, str):
            raise ValueError("start_error must be a string or None")


class WindowsSystemTerminalRunner:
    """Run approved argv requests on the local Windows system terminal."""

    def __init__(
        self,
        execution_root: Path,
        *,
        executable_resolver: ExecutableResolver | None = None,
        process_runner: WindowsProcessRunner | None = None,
        cleanup_process_tree: WindowsCleanupProcessTree | None = None,
    ) -> None:
        self.execution_root = Path(execution_root).resolve()
        self.executable_resolver = executable_resolver or shutil.which
        self.process_runner = process_runner or _subprocess_process_runner
        self.cleanup_process_tree = cleanup_process_tree or _default_process_tree_cleanup

    def run(self, request: TerminalBackendRequest) -> TerminalBackendResult:
        if not isinstance(request, TerminalBackendRequest):
            raise TypeError("WindowsSystemTerminalRunner.run requires a TerminalBackendRequest")
        if request.command_request.get("kind") != "exec_argv":
            raise ValueError("windows system terminal runner only supports exec_argv")
        command = validate_argv(request.command_request.get("argv"))
        terminal_grant = terminal_grant_from(request.grants)
        _ensure_windows_system_terminal_grant(command, terminal_grant)
        timeout_seconds = _timeout_seconds(request.budget)
        max_output_bytes = _max_output_bytes(terminal_grant)

        cwd = self._prepare_cwd()
        started_at = _utc_now()
        resolved_executable = self.executable_resolver(command[0])
        if not resolved_executable:
            return _system_runner_result(
                request=request,
                command=command,
                resolved_executable=None,
                cwd=cwd,
                status="failed",
                reason_code="terminal_windows_runner_start_failed",
                stdout="",
                stderr=f"executable not found: {command[0]}",
                truncated=False,
                max_output_bytes=max_output_bytes,
                exit_code=None,
                timed_out=False,
                timeout_seconds=timeout_seconds,
                process_tree_cleanup=_no_process_tree_cleanup(),
                retryable=False,
                started_at=started_at,
                finished_at=_utc_now(),
            )
        _ensure_windows_executable_allowed(command[0], resolved_executable)

        result = self.process_runner(
            argv=[resolved_executable, *command[1:]],
            cwd=str(cwd),
            timeout_seconds=timeout_seconds,
        )
        stdout, stderr, truncated = cap_terminal_output(
            result.stdout,
            result.stderr,
            max_output_bytes=max_output_bytes,
        )
        process_tree_cleanup = _no_process_tree_cleanup()
        if result.timed_out:
            process_tree_cleanup = self.cleanup_process_tree(result.process_id)

        status, reason_code, retryable = _result_status(result)
        return _system_runner_result(
            request=request,
            command=command,
            resolved_executable=resolved_executable,
            cwd=cwd,
            status=status,
            reason_code=reason_code,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
            max_output_bytes=max_output_bytes,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            timeout_seconds=timeout_seconds,
            process_tree_cleanup=process_tree_cleanup,
            retryable=retryable,
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
    resolved_executable: str | None,
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
    process_tree_cleanup: dict[str, Any],
    retryable: bool,
    started_at: str,
    finished_at: str,
) -> TerminalBackendResult:
    summary_status = "failed" if status == "timeout" else status
    return TerminalBackendResult(
        backend_session_id=f"windows_system_terminal_{request.execution_id}",
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        summary=f"windows system terminal {summary_status}: {command[0]}",
        output_artifacts=[
            TerminalBackendOutputArtifact(
                artifact_type="terminal_backend_transcript",
                summary="windows system terminal transcript captured",
                content=json.dumps(
                    {
                        "argv": command,
                        "resolved_executable": resolved_executable,
                        "cwd": str(cwd),
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "truncated": truncated,
                        "max_output_bytes": max_output_bytes,
                        "shell": False,
                        "timed_out": timed_out,
                        "timeout_seconds": timeout_seconds,
                        "platform": "windows",
                        "process_tree_cleanup": dict(process_tree_cleanup),
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


def _ensure_windows_system_terminal_grant(command: list[str], terminal_grant: dict[str, Any]) -> None:
    if terminal_grant.get("shell") is not False:
        raise ValueError("windows system terminal runner requires shell=False")
    if terminal_grant.get("argv_policy") != "allowlist":
        raise ValueError("windows system terminal runner requires argv allowlist policy")
    allowed = terminal_grant.get("allowed_commands", [])
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise ValueError("windows system terminal runner allowed_commands grant is malformed")
    if command[0] not in set(allowed):
        raise PermissionError("windows system terminal command is not allowed by grants")
    if command[0].lower() in WINDOWS_PROFILE_BACKED_COMMANDS:
        raise PermissionError("windows package manager commands are profile-backed, not arbitrary exec_argv")


def _ensure_windows_executable_allowed(command_name: str, resolved_executable: str) -> None:
    suffix = Path(resolved_executable).suffix.lower()
    if suffix in WINDOWS_REJECTED_SCRIPT_EXTENSIONS:
        raise PermissionError(f"windows system terminal runner rejects {suffix} executables")
    if suffix != ".exe":
        raise PermissionError(
            f"windows system terminal runner only allows .exe executables for {command_name}"
        )


def _result_status(result: WindowsTerminalProcessResult) -> tuple[str, str, bool]:
    if result.timed_out:
        return "timeout", "terminal_windows_runner_timeout", True
    if result.start_error:
        return "failed", "terminal_windows_runner_start_failed", False
    if result.exit_code == 0:
        return "completed", "terminal_windows_runner_completed", False
    return "failed", "terminal_windows_runner_exit_nonzero", False


def _timeout_seconds(budget: dict[str, Any]) -> int:
    value = budget.get("seconds")
    if not isinstance(value, int) or value < 0:
        raise ValueError("windows system terminal runner requires budget.seconds")
    return value


def _max_output_bytes(terminal_grant: dict[str, Any]) -> int:
    value = terminal_grant.get("max_output_bytes", 4096)
    if not isinstance(value, int) or value <= 0:
        raise ValueError("windows system terminal runner requires positive max_output_bytes")
    return value


def _subprocess_process_runner(
    *,
    argv: list[str],
    cwd: str,
    timeout_seconds: int,
) -> WindowsTerminalProcessResult:
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=_sanitized_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return WindowsTerminalProcessResult(
            exit_code=None,
            stdout=_timeout_text(exc.stdout),
            stderr=_timeout_text(exc.stderr),
            timed_out=True,
            process_id=process.pid,
        )
    except OSError as exc:
        return WindowsTerminalProcessResult(
            exit_code=None,
            stdout="",
            stderr=str(exc),
            timed_out=False,
            start_error=str(exc),
        )
    return WindowsTerminalProcessResult(
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
    )


def _default_process_tree_cleanup(process_id: int | None) -> dict[str, Any]:
    if process_id is None:
        return _no_process_tree_cleanup()
    if os.name != "nt":
        return {"attempted": False, "succeeded": None, "method": "taskkill", "process_id": process_id}
    completed = subprocess.run(
        ["taskkill", "/PID", str(process_id), "/T", "/F"],
        text=True,
        capture_output=True,
        shell=False,
        check=False,
    )
    return {
        "attempted": True,
        "succeeded": completed.returncode == 0,
        "method": "taskkill",
        "process_id": process_id,
    }


def _no_process_tree_cleanup() -> dict[str, Any]:
    return {"attempted": False, "succeeded": None, "method": None}


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


__all__ = [
    "WindowsSystemTerminalRunner",
    "WindowsTerminalProcessResult",
]
