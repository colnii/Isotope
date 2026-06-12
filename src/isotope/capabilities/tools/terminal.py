"""Controlled terminal execution for application agents."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_ALLOWED_COMMANDS = ("echo", "printf", "pwd", "true", "false", "sleep")
DEFAULT_APPROVAL_REQUIRED_COMMANDS = ("bash", "pwsh", "powershell.exe")
DEFAULT_MAX_OUTPUT_BYTES = 4096
DEFAULT_TERMINAL_APPROVAL_MODE = "allowlist"
TERMINAL_APPROVAL_MODES = ("single_approval", "allowlist", "yolo")
TERMINAL_EXEC_CAPABILITY = "terminal.exec"
_DEFAULT_TIMEOUT_SECONDS = 30
_MAX_TIMEOUT_SECONDS = 120


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
        violation = terminal_grant_policy_violation(argv, terminal_grant)
        if violation is not None:
            raise TerminalExecutionError(
                violation["message"],
                reason_code=violation["reason_code"],
                details=violation.get("details"),
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


def terminal_grant_policy_violation(
    argv: list[str],
    terminal_grant: dict[str, Any],
) -> dict[str, Any] | None:
    if terminal_grant.get("shell") is not False:
        return {
            "message": "terminal shell execution is not granted",
            "reason_code": "terminal_shell_not_granted",
        }
    policy = terminal_grant.get("argv_policy")
    if policy == "allowlist":
        allowed = terminal_grant.get("allowed_commands", [])
        if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
            return {
                "message": "terminal allowed command grant is malformed",
                "reason_code": "terminal_grant_malformed",
            }
        if argv[0] not in set(allowed):
            return {
                "message": "terminal command is not allowed",
                "reason_code": "terminal_command_not_allowed",
                "details": {"argv0": argv[0]},
            }
        return None
    if policy == "exact_argv":
        allowed_argv = terminal_grant.get("allowed_argv")
        if not isinstance(allowed_argv, list) or not all(
            isinstance(item, str) for item in allowed_argv
        ):
            return {
                "message": "terminal exact argv grant is malformed",
                "reason_code": "terminal_grant_malformed",
            }
        if argv != allowed_argv:
            return {
                "message": "terminal argv does not match approved command",
                "reason_code": "terminal_command_not_allowed",
                "details": {"argv0": argv[0]},
            }
        return None
    if policy == "unrestricted":
        return None
    return {
        "message": "terminal argv policy is not supported",
        "reason_code": "terminal_policy_unsupported",
    }


def default_terminal_capabilities() -> dict[str, Any]:
    return {
        "shell": False,
        "argv_policy": "allowlist",
        "approval_mode": DEFAULT_TERMINAL_APPROVAL_MODE,
        "approval_modes": list(TERMINAL_APPROVAL_MODES),
        "allowed_commands": list(DEFAULT_ALLOWED_COMMANDS),
        "approval_required_commands": list(DEFAULT_APPROVAL_REQUIRED_COMMANDS),
        "max_output_bytes": DEFAULT_MAX_OUTPUT_BYTES,
    }


def is_terminal_exec_capability(capability_id: str) -> bool:
    return capability_id == TERMINAL_EXEC_CAPABILITY


def validate_terminal_exec_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if not is_terminal_exec_capability(capability_id):
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    if "argv" not in missing_inputs:
        input_mapping["argv"] = validate_argv(input_mapping.get("argv"))
    input_mapping["approval_mode"] = _approval_mode(
        input_mapping.get("approval_mode", DEFAULT_TERMINAL_APPROVAL_MODE)
    )
    input_mapping["allowed_commands"] = _string_list(
        input_mapping.get("allowed_commands", list(DEFAULT_ALLOWED_COMMANDS)),
        field_name="allowed_commands",
        allow_empty=True,
    )
    input_mapping["timeout_seconds"] = _limited_int(
        input_mapping.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS),
        field_name="timeout_seconds",
        minimum=1,
        maximum=_MAX_TIMEOUT_SECONDS,
    )
    input_mapping["max_output_bytes"] = _limited_int(
        input_mapping.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES),
        field_name="max_output_bytes",
        minimum=1,
        maximum=65536,
    )
    return input_mapping


def run_terminal_exec(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    from isotope.platform.schemas.input_contract import missing_required_input_keys
    from isotope.runtime.in_process import InProcessServer

    required_inputs = ["root", "cwd", "argv"]
    missing_inputs = missing_required_input_keys(inputs, required_inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_terminal_exec_inputs(
        capability_id=TERMINAL_EXEC_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    root = Path(input_mapping["root"]).expanduser()
    cwd = Path(input_mapping["cwd"]).expanduser()
    if not cwd.exists():
        raise ValueError("cwd must exist before running terminal.exec")
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory before running terminal.exec")
    argv = list(input_mapping["argv"])
    approval_mode = str(input_mapping["approval_mode"])
    allowed_commands = list(input_mapping["allowed_commands"])
    api = InProcessServer(root)
    session = api.create_session()
    run = api.create_run(
        session["session_id"],
        f"terminal.exec: {argv[0]}",
    )
    intent = {
        "action": "call_tool",
        "tool": "terminal_exec",
        "argv": argv,
        "cwd": str(cwd),
        "summary": f"terminal.exec command: {argv[0]}",
        "terminal_approval_mode": approval_mode,
        "terminal_allowed_commands": allowed_commands,
        "terminal_max_output_bytes": input_mapping["max_output_bytes"],
        "budget": {"seconds": input_mapping["timeout_seconds"]},
    }
    result = api.submit_action(
        run["run_id"],
        intent,
        requires_approval=_terminal_exec_requires_approval(
            argv,
            approval_mode=approval_mode,
            allowed_commands=allowed_commands,
        ),
    )
    return _terminal_exec_capacity_result(
        result,
        run_id=run["run_id"],
        argv=argv,
        approval_mode=approval_mode,
    )


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


def _terminal_exec_requires_approval(
    argv: list[str],
    *,
    approval_mode: str,
    allowed_commands: list[str],
) -> bool:
    if approval_mode == "yolo":
        return False
    if approval_mode == "single_approval":
        return True
    approval_required = set(DEFAULT_APPROVAL_REQUIRED_COMMANDS)
    return argv[0] not in set(allowed_commands) or argv[0] in approval_required


def _terminal_exec_capacity_result(
    result: dict[str, Any],
    *,
    run_id: str,
    argv: list[str],
    approval_mode: str,
) -> dict[str, Any]:
    status = str(result.get("status", "unknown"))
    terminal: dict[str, Any] = {
        "status": status,
        "run_id": run_id,
        "argv0": argv[0],
        "approval_mode": approval_mode,
        "shell": False,
    }
    for key in ("approval_id", "proposal_id", "decision_id", "execution_id"):
        value = result.get(key)
        if isinstance(value, str) and value:
            terminal[key] = value
    artifact_ref = result.get("artifact_ref")
    if hasattr(artifact_ref, "to_dict"):
        terminal["artifact_ref"] = artifact_ref.to_dict()
    elif isinstance(artifact_ref, dict):
        terminal["artifact_ref"] = dict(artifact_ref)
    return {
        "kind": "capability_run_result",
        "capability_id": TERMINAL_EXEC_CAPABILITY,
        "status": status,
        "runner_kind": "runtime_terminal",
        "terminal_exec": terminal,
    }


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


def _approval_mode(value: Any) -> str:
    if not isinstance(value, str) or value not in TERMINAL_APPROVAL_MODES:
        supported = ", ".join(TERMINAL_APPROVAL_MODES)
        raise ValueError(f"approval_mode must be one of: {supported}")
    return value


def _string_list(value: Any, *, field_name: str, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    if not value and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")
        result.append(item.strip())
    return result


def _limited_int(value: Any, *, field_name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return value


def _sanitized_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


__all__ = [
    "ControlledTerminalRunner",
    "DEFAULT_APPROVAL_REQUIRED_COMMANDS",
    "DEFAULT_TERMINAL_APPROVAL_MODE",
    "TERMINAL_APPROVAL_MODES",
    "TERMINAL_EXEC_CAPABILITY",
    "TerminalExecutionError",
    "TerminalExecutionResult",
    "cap_terminal_output",
    "default_terminal_capabilities",
    "is_terminal_exec_capability",
    "run_terminal_exec",
    "terminal_grant_from",
    "terminal_grant_policy_violation",
    "validate_terminal_exec_inputs",
    "validate_argv",
]
