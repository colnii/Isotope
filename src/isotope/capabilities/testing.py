"""Allowlisted test command capability for native coding."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .tools.terminal import (
    ControlledTerminalRunner,
    TerminalExecutionError,
    default_terminal_capabilities,
    validate_argv,
)
from ..platform.schemas.input_contract import missing_required_input_keys


TEST_RUN_CAPABILITY = "test.run"
_DEFAULT_TIMEOUT_SECONDS = 30
_MAX_TIMEOUT_SECONDS = 120


def is_test_run_capability(capability_id: str) -> bool:
    return capability_id == TEST_RUN_CAPABILITY


def validate_test_run_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != TEST_RUN_CAPABILITY:
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
    input_mapping["allowed_commands"] = _string_list(
        input_mapping.get(
            "allowed_commands",
            default_terminal_capabilities()["allowed_commands"],
        ),
        field_name="allowed_commands",
    )
    input_mapping["timeout_seconds"] = _limited_int(
        input_mapping.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS),
        field_name="timeout_seconds",
        minimum=1,
        maximum=_MAX_TIMEOUT_SECONDS,
    )
    input_mapping["max_output_bytes"] = _limited_int(
        input_mapping.get(
            "max_output_bytes",
            default_terminal_capabilities()["max_output_bytes"],
        ),
        field_name="max_output_bytes",
        minimum=1,
        maximum=65536,
    )
    return input_mapping


def run_test_run(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "cwd", "argv"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_test_run_inputs(
        capability_id=TEST_RUN_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    cwd = Path(input_mapping["cwd"]).expanduser()
    if not cwd.exists():
        raise ValueError("cwd must exist before running tests")
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory before running tests")

    grants = {
        "terminal": {
            "shell": False,
            "argv_policy": "allowlist",
            "allowed_commands": list(input_mapping["allowed_commands"]),
            "approval_required_commands": [],
            "max_output_bytes": input_mapping["max_output_bytes"],
        }
    }
    try:
        terminal_result = ControlledTerminalRunner(cwd).run(
            input_mapping["argv"],
            grants=grants,
            timeout_seconds=input_mapping["timeout_seconds"],
        )
        test_result = _terminal_result_payload(
            terminal_result,
            status="passed",
            reason_code=None,
        )
    except TerminalExecutionError as exc:
        if exc.error_reason_code == "terminal_command_not_allowed":
            raise PermissionError(str(exc)) from exc
        if exc.terminal_result is not None:
            test_result = _terminal_result_payload(
                exc.terminal_result,
                status="failed",
                reason_code=exc.error_reason_code,
            )
        elif exc.error_reason_code == "terminal_timeout":
            test_result = {
                "status": "timeout",
                "argv": list(input_mapping["argv"]),
                "exit_code": None,
                "stdout_excerpt": "",
                "stderr_excerpt": "",
                "output_truncated": False,
                "timeout_seconds": input_mapping["timeout_seconds"],
                "reason_code": exc.error_reason_code,
                "artifact_write": "not_performed",
                "shell": False,
            }
        else:
            raise RuntimeError(str(exc)) from exc

    return {
        "kind": "capability_run_result",
        "capability_id": TEST_RUN_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "test_result": test_result,
    }


def _terminal_result_payload(
    terminal_result,
    *,
    status: str,
    reason_code: str | None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "argv": list(terminal_result.argv),
        "exit_code": terminal_result.exit_code,
        "stdout_excerpt": terminal_result.stdout,
        "stderr_excerpt": terminal_result.stderr,
        "output_truncated": terminal_result.truncated,
        "max_output_bytes": terminal_result.max_output_bytes,
        "artifact_write": "not_performed",
        "shell": False,
    }
    if reason_code is not None:
        payload["reason_code"] = reason_code
    return payload


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _string_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list of strings")
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


__all__ = [
    "TEST_RUN_CAPABILITY",
    "is_test_run_capability",
    "run_test_run",
    "validate_test_run_inputs",
]
