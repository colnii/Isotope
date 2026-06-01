"""Structured Windows-native smoke harness schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


WINDOWS_SMOKE_SCHEMA_VERSION = "windows-smoke.v0.1"


@dataclass(frozen=True)
class WindowsSmokeStep:
    name: str
    argv: list[str]
    cwd: str = "."
    env_overlay: dict[str, str] = field(default_factory=dict)
    required_artifacts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _non_empty_string("name", self.name)
        _argv(self.argv)
        _non_empty_string("cwd", self.cwd)
        _string_dict("env_overlay", self.env_overlay)
        _string_list("required_artifacts", self.required_artifacts, allow_empty=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "env_overlay": dict(self.env_overlay),
            "required_artifacts": list(self.required_artifacts),
        }


@dataclass(frozen=True)
class WindowsSmokePlan:
    source_root: str | Path
    profile_id: str
    profile_version: str
    workspace_strategy: str
    steps: list[WindowsSmokeStep]
    timeout_seconds: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        _non_empty_string("source_root", str(self.source_root))
        _non_empty_string("profile_id", self.profile_id)
        _non_empty_string("profile_version", self.profile_version)
        if self.workspace_strategy not in {"direct", "copy_to_temp", "auto"}:
            raise ValueError("workspace_strategy must be direct, copy_to_temp, or auto")
        if not isinstance(self.steps, list) or not self.steps:
            raise ValueError("steps must be a non-empty list")
        for index, step in enumerate(self.steps):
            if not isinstance(step, WindowsSmokeStep):
                raise ValueError(f"steps[{index}] must be a WindowsSmokeStep")
        _positive_int("timeout_seconds", self.timeout_seconds)
        _positive_int("max_output_bytes", self.max_output_bytes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_root": str(self.source_root),
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "workspace_strategy": self.workspace_strategy,
            "steps": [step.to_dict() for step in self.steps],
            "timeout_seconds": self.timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
        }


@dataclass(frozen=True)
class WindowsSmokeStepResult:
    name: str
    argv: list[str]
    cwd: str
    started_at: str
    finished_at: str
    exit_code: int | None
    stdout: str
    stderr: str
    truncated: bool
    reason_code: str
    artifacts: list[str] = field(default_factory=list)
    copied_workspace_path: str | None = None
    process_tree_cleanup: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_empty_string("name", self.name)
        _argv(self.argv)
        _non_empty_string("cwd", self.cwd)
        _non_empty_string("started_at", self.started_at)
        _non_empty_string("finished_at", self.finished_at)
        if self.exit_code is not None and not isinstance(self.exit_code, int):
            raise ValueError("exit_code must be an int or None")
        if not isinstance(self.stdout, str):
            raise ValueError("stdout must be a string")
        if not isinstance(self.stderr, str):
            raise ValueError("stderr must be a string")
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be a bool")
        _non_empty_string("reason_code", self.reason_code)
        _string_list("artifacts", self.artifacts, allow_empty=True)
        if self.copied_workspace_path is not None:
            _non_empty_string("copied_workspace_path", self.copied_workspace_path)
        if not isinstance(self.process_tree_cleanup, dict):
            raise ValueError("process_tree_cleanup must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "truncated": self.truncated,
            "reason_code": self.reason_code,
            "artifacts": list(self.artifacts),
            "copied_workspace_path": self.copied_workspace_path,
            "process_tree_cleanup": dict(self.process_tree_cleanup),
        }


@dataclass(frozen=True)
class WindowsSmokeReport:
    runner_version: str
    profile_id: str
    profile_version: str
    host_mode: str
    platform_info: dict[str, Any]
    tool_versions: dict[str, str]
    source_root_kind: str
    workspace_strategy_decision: dict[str, Any]
    repo_revision_if_available: str | None
    started_at: str
    finished_at: str
    status: str
    reason_code: str
    diagnostic_report: dict[str, Any]
    public_summary: dict[str, Any]
    schema_version: str = WINDOWS_SMOKE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _non_empty_string("schema_version", self.schema_version)
        _non_empty_string("runner_version", self.runner_version)
        _non_empty_string("profile_id", self.profile_id)
        _non_empty_string("profile_version", self.profile_version)
        if self.host_mode not in {"windows_python", "wsl_to_windows_helper", "unsupported"}:
            raise ValueError("host_mode is not supported")
        if not isinstance(self.platform_info, dict):
            raise ValueError("platform_info must be a dict")
        _string_dict("tool_versions", self.tool_versions)
        _non_empty_string("source_root_kind", self.source_root_kind)
        if not isinstance(self.workspace_strategy_decision, dict):
            raise ValueError("workspace_strategy_decision must be a dict")
        if self.repo_revision_if_available is not None:
            _non_empty_string("repo_revision_if_available", self.repo_revision_if_available)
        _non_empty_string("started_at", self.started_at)
        _non_empty_string("finished_at", self.finished_at)
        if self.status not in {"completed", "failed", "timeout", "unsupported"}:
            raise ValueError("status is not supported")
        _non_empty_string("reason_code", self.reason_code)
        if not isinstance(self.diagnostic_report, dict):
            raise ValueError("diagnostic_report must be a dict")
        if not isinstance(self.public_summary, dict):
            raise ValueError("public_summary must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runner_version": self.runner_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "host_mode": self.host_mode,
            "platform_info": dict(self.platform_info),
            "tool_versions": dict(self.tool_versions),
            "source_root_kind": self.source_root_kind,
            "workspace_strategy_decision": dict(self.workspace_strategy_decision),
            "repo_revision_if_available": self.repo_revision_if_available,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "reason_code": self.reason_code,
            "diagnostic_report": dict(self.diagnostic_report),
            "public_summary": dict(self.public_summary),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


def redact_public_summary(
    *,
    status: str,
    reason_code: str,
    profile_id: str,
    host_mode: str,
    workspace_strategy_decision: dict[str, Any],
    diagnostic_report: dict[str, Any],
    redaction_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Build the low-sensitive summary from diagnostic report data."""

    _non_empty_string("status", status)
    _non_empty_string("reason_code", reason_code)
    _non_empty_string("profile_id", profile_id)
    _non_empty_string("host_mode", host_mode)
    if not isinstance(workspace_strategy_decision, dict):
        raise ValueError("workspace_strategy_decision must be a dict")
    if not isinstance(diagnostic_report, dict):
        raise ValueError("diagnostic_report must be a dict")
    _string_list("redaction_paths", redaction_paths or [], allow_empty=True)

    steps = diagnostic_report.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("diagnostic_report.steps must be a list")
    return {
        "status": status,
        "reason_code": reason_code,
        "profile_id": profile_id,
        "host_mode": host_mode,
        "workspace_strategy": workspace_strategy_decision.get("strategy", "unknown"),
        "step_summaries": [_public_step_summary(step) for step in steps],
    }


def _public_step_summary(step: Any) -> dict[str, Any]:
    if not isinstance(step, dict):
        raise ValueError("diagnostic_report step must be a dict")
    return {
        "name": step.get("name"),
        "exit_code": step.get("exit_code"),
        "reason_code": step.get("reason_code"),
        "truncated": step.get("truncated", False),
    }


def _argv(value: list[str]) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("argv must be a non-empty list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"argv[{index}] must be a non-empty string")
        if "\x00" in item:
            raise ValueError(f"argv[{index}] must not contain NUL")


def _non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _string_dict(field_name: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(item, str):
            raise ValueError(f"{field_name}[{key}] must be a string")


def _string_list(field_name: str, value: Any, *, allow_empty: bool) -> None:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{field_name} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")


def _positive_int(field_name: str, value: Any) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive int")


__all__ = [
    "WINDOWS_SMOKE_SCHEMA_VERSION",
    "WindowsSmokePlan",
    "WindowsSmokeReport",
    "WindowsSmokeStep",
    "WindowsSmokeStepResult",
    "redact_public_summary",
]
