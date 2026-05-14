"""Controlled terminal execution for application agents."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ALLOWED_COMMANDS = ("echo", "printf", "pwd", "true", "false", "sleep")
DEFAULT_MAX_OUTPUT_BYTES = 4096


class TerminalExecutionError(RuntimeError):
    """Structured terminal failure that can be projected into action state."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: dict[str, Any] | None = None,
        terminal_result: TerminalExecutionResult | None = None,
    ) -> None:
        super().__init__(message)
        self.error_reason_code = reason_code
        self.structured_details = dict(details or {})
        self.terminal_result = terminal_result


@dataclass(frozen=True)
class TerminalExecutionResult:
    argv: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool
    max_output_bytes: int

    def to_artifact_content(self) -> str:
        return json.dumps(
            {
                "argv": self.argv,
                "cwd": self.cwd,
                "exit_code": self.exit_code,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "truncated": self.truncated,
                "max_output_bytes": self.max_output_bytes,
                "shell": False,
            },
            sort_keys=True,
        )


class ControlledTerminalRunner:
    """Run argv-only commands under explicit terminal grants."""

    def __init__(self, execution_root: Path):
        self.execution_root = Path(execution_root).resolve()

    def run(
        self,
        argv: Any,
        *,
        grants: dict[str, Any],
        timeout_seconds: int,
    ) -> TerminalExecutionResult:
        command = validate_argv(argv)
        terminal_grant = terminal_grant_from(grants)
        self._ensure_command_allowed(command, terminal_grant)
        max_output_bytes = _positive_int(
            terminal_grant.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES),
            "terminal.max_output_bytes",
        )

        cwd = self._prepare_cwd()
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
            raise TerminalExecutionError(
                f"terminal command timed out after {timeout_seconds}s",
                reason_code="terminal_timeout",
                details={"timeout_seconds": timeout_seconds, "argv0": command[0]},
            ) from exc
        except OSError as exc:
            raise TerminalExecutionError(
                "terminal command could not be started",
                reason_code="terminal_start_failed",
                details={"argv0": command[0]},
            ) from exc

        stdout, stderr, truncated = cap_terminal_output(
            completed.stdout,
            completed.stderr,
            max_output_bytes=max_output_bytes,
        )
        result = TerminalExecutionResult(
            argv=command,
            cwd=str(cwd),
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
            max_output_bytes=max_output_bytes,
        )
        if completed.returncode != 0:
            raise TerminalExecutionError(
                f"terminal command exited with status {completed.returncode}",
                reason_code="terminal_exit_nonzero",
                details={
                    "exit_code": completed.returncode,
                    "argv0": command[0],
                    "output_truncated": truncated,
                },
                terminal_result=result,
            )
        return result

    def _prepare_cwd(self) -> Path:
        self.execution_root.mkdir(parents=True, exist_ok=True)
        return self.execution_root

    def _ensure_command_allowed(self, argv: list[str], terminal_grant: dict[str, Any]) -> None:
        if terminal_grant.get("shell") is not False:
            raise TerminalExecutionError(
                "terminal shell execution is not granted",
                reason_code="terminal_shell_not_granted",
            )
        if terminal_grant.get("argv_policy") != "allowlist":
            raise TerminalExecutionError(
                "terminal argv policy is not supported",
                reason_code="terminal_policy_unsupported",
            )
        allowed = terminal_grant.get("allowed_commands", [])
        if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
            raise TerminalExecutionError(
                "terminal allowed command grant is malformed",
                reason_code="terminal_grant_malformed",
            )
        if argv[0] not in set(allowed):
            raise TerminalExecutionError(
                "terminal command is not allowed",
                reason_code="terminal_command_not_allowed",
                details={"argv0": argv[0]},
            )


def validate_argv(argv: Any) -> list[str]:
    if not isinstance(argv, list) or not argv:
        raise ValueError("terminal_exec argv must be a non-empty list")
    if len(argv) > 32:
        raise ValueError("terminal_exec argv cannot contain more than 32 entries")
    normalized: list[str] = []
    for index, value in enumerate(argv):
        if not isinstance(value, str) or not value:
            raise ValueError(f"terminal_exec argv[{index}] must be a non-empty string")
        if "\x00" in value:
            raise ValueError(f"terminal_exec argv[{index}] cannot contain NUL")
        normalized.append(value)
    command = normalized[0]
    if "/" in command or "\\" in command:
        raise ValueError("terminal_exec argv[0] must be a command name, not a path")
    return normalized


def terminal_grant_from(grants: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(grants, dict):
        raise TerminalExecutionError(
            "terminal grants must be a dict",
            reason_code="terminal_grant_malformed",
        )
    terminal_grant = grants.get("terminal")
    if not isinstance(terminal_grant, dict):
        raise TerminalExecutionError(
            "terminal grant is required",
            reason_code="terminal_grant_missing",
        )
    return terminal_grant


def default_terminal_capabilities() -> dict[str, Any]:
    return {
        "shell": False,
        "argv_policy": "allowlist",
        "allowed_commands": list(DEFAULT_ALLOWED_COMMANDS),
        "approval_required_commands": [],
        "max_output_bytes": DEFAULT_MAX_OUTPUT_BYTES,
    }


def cap_terminal_output(
    stdout: str,
    stderr: str,
    *,
    max_output_bytes: int,
) -> tuple[str, str, bool]:
    stdout = stdout or ""
    stderr = stderr or ""
    budget = max_output_bytes
    capped_stdout, budget, stdout_truncated = _cap_text(stdout, budget)
    capped_stderr, _remaining, stderr_truncated = _cap_text(stderr, budget)
    return capped_stdout, capped_stderr, stdout_truncated or stderr_truncated


def _cap_text(value: str, budget: int) -> tuple[str, int, bool]:
    if budget <= 0:
        return "", 0, bool(value)
    encoded = value.encode("utf-8")
    if len(encoded) <= budget:
        return value, budget - len(encoded), False
    clipped = encoded[:budget].decode("utf-8", errors="ignore")
    return clipped, 0, True


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise TerminalExecutionError(
            f"{field_name} must be a positive integer",
            reason_code="terminal_grant_malformed",
        )
    return value


def _sanitized_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


__all__ = [
    "ControlledTerminalRunner",
    "TerminalExecutionError",
    "TerminalExecutionResult",
    "cap_terminal_output",
    "default_terminal_capabilities",
    "terminal_grant_from",
    "validate_argv",
]
