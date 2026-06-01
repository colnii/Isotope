"""Structured Windows-native smoke harness schemas."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


WINDOWS_SMOKE_SCHEMA_VERSION = "windows-smoke.v0.1"
WINDOWS_PATH_RISK_LENGTH = 200
COPY_INCLUDE_FILES = (
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "Cargo.toml",
    "Cargo.lock",
)
COPY_INCLUDE_DIRS = (
    "apps/desktop",
    "src",
    "apps/desktop/src-tauri",
)
COPY_EXCLUDE_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "target",
    "dist",
    "build",
    ".svelte-kit",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
READ_ONLY_MUTATION_POLICIES = {"read_only", "check"}


class WindowsSmokeWorkspaceError(RuntimeError):
    """Workspace resolution or copy-policy failure."""

    def __init__(self, message: str, *, reason_code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = dict(details or {})


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


@dataclass(frozen=True)
class WindowsWorkspaceDecision:
    strategy: str
    source_root: str
    source_root_kind: str
    workspace_root: str | None
    reason: str
    cleanup_on_success: bool
    keep_on_failure: bool

    def __post_init__(self) -> None:
        if self.strategy not in {"direct", "copy_to_temp", "unsupported"}:
            raise ValueError("workspace decision strategy is not supported")
        _non_empty_string("source_root", self.source_root)
        _non_empty_string("source_root_kind", self.source_root_kind)
        if self.workspace_root is not None:
            _non_empty_string("workspace_root", self.workspace_root)
        _non_empty_string("reason", self.reason)
        if not isinstance(self.cleanup_on_success, bool):
            raise ValueError("cleanup_on_success must be a bool")
        if not isinstance(self.keep_on_failure, bool):
            raise ValueError("keep_on_failure must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "source_root": self.source_root,
            "source_root_kind": self.source_root_kind,
            "workspace_root": self.workspace_root,
            "reason": self.reason,
            "cleanup_on_success": self.cleanup_on_success,
            "keep_on_failure": self.keep_on_failure,
        }


def resolve_windows_host_mode(
    *,
    platform_name: str | None = None,
    has_wsl_interop: bool | None = None,
) -> str:
    platform = platform_name or sys.platform
    if platform == "win32":
        return "windows_python"
    if has_wsl_interop is None:
        has_wsl_interop = _detect_wsl_windows_interop()
    if platform.startswith("linux") and has_wsl_interop:
        return "wsl_to_windows_helper"
    return "unsupported"


def resolve_windows_workspace(
    *,
    source_root: str | Path,
    host_mode: str,
    workspace_strategy: str,
    source_root_kind: str | None = None,
    mutation_policy: str = "read_only",
    temp_root: str = "C:\\isotope-smoke",
    run_id: str = "run",
    allow_direct_mutation: bool = False,
    windows_path_risk_length: int = WINDOWS_PATH_RISK_LENGTH,
) -> WindowsWorkspaceDecision:
    source_text = str(source_root)
    _non_empty_string("source_root", source_text)
    if host_mode not in {"windows_python", "wsl_to_windows_helper", "unsupported"}:
        raise ValueError("host_mode is not supported")
    if workspace_strategy not in {"direct", "copy_to_temp", "auto"}:
        raise ValueError("workspace_strategy must be direct, copy_to_temp, or auto")
    _non_empty_string("mutation_policy", mutation_policy)
    _non_empty_string("temp_root", temp_root)
    _non_empty_string("run_id", run_id)
    source_kind = source_root_kind or classify_windows_source_root(source_text)

    if host_mode == "unsupported":
        return WindowsWorkspaceDecision(
            strategy="unsupported",
            source_root=source_text,
            source_root_kind=source_kind,
            workspace_root=None,
            reason="windows_host_unsupported",
            cleanup_on_success=False,
            keep_on_failure=True,
        )
    if workspace_strategy == "direct":
        return _direct_workspace_decision(source_text, source_kind, reason="workspace_strategy_direct")
    if workspace_strategy == "copy_to_temp":
        return _copy_workspace_decision(
            source_text,
            source_kind,
            temp_root=temp_root,
            run_id=run_id,
            reason="workspace_strategy_copy_to_temp",
        )
    if host_mode != "windows_python" or source_kind != "windows_local":
        return _copy_workspace_decision(
            source_text,
            source_kind,
            temp_root=temp_root,
            run_id=run_id,
            reason="source_root_requires_windows_local_copy",
        )
    if mutation_policy not in READ_ONLY_MUTATION_POLICIES and not allow_direct_mutation:
        return _copy_workspace_decision(
            source_text,
            source_kind,
            temp_root=temp_root,
            run_id=run_id,
            reason="mutation_policy_requires_copy",
        )
    if len(source_text) >= windows_path_risk_length:
        return _copy_workspace_decision(
            source_text,
            source_kind,
            temp_root=temp_root,
            run_id=run_id,
            reason="windows_path_length_risk",
        )
    return _direct_workspace_decision(source_text, source_kind, reason="safe_windows_local_read_only")


def classify_windows_source_root(source_root: str | Path) -> str:
    text = str(source_root)
    normalized = text.replace("/", "\\")
    if normalized.lower().startswith("\\\\wsl.localhost\\") or normalized.lower().startswith("\\\\wsl$\\"):
        return "wsl_unc"
    if len(normalized) >= 3 and normalized[1:3] == ":\\" and normalized[0].isalpha():
        return "windows_local"
    if text.startswith("/"):
        return "posix_path"
    return "unknown"


def collect_windows_workspace_copy_items(source_root: str | Path) -> list[Path]:
    root = Path(source_root).resolve()
    if not root.exists() or not root.is_dir():
        raise WindowsSmokeWorkspaceError(
            "workspace source root is unavailable",
            reason_code="windows_smoke_workspace_unavailable",
            details={"source_root": str(source_root)},
        )
    items: list[Path] = []
    for relative_name in COPY_INCLUDE_FILES:
        candidate = root / relative_name
        if candidate.exists() and _is_copyable_path(root, candidate):
            items.append(Path(relative_name))
    for relative_name in COPY_INCLUDE_DIRS:
        candidate = root / relative_name
        if candidate.exists() and candidate.is_dir():
            items.extend(_copyable_tree_items(root, candidate))
    return sorted(set(items), key=lambda item: item.as_posix())


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


def _direct_workspace_decision(source_root: str, source_root_kind: str, *, reason: str) -> WindowsWorkspaceDecision:
    return WindowsWorkspaceDecision(
        strategy="direct",
        source_root=source_root,
        source_root_kind=source_root_kind,
        workspace_root=source_root,
        reason=reason,
        cleanup_on_success=False,
        keep_on_failure=True,
    )


def _copy_workspace_decision(
    source_root: str,
    source_root_kind: str,
    *,
    temp_root: str,
    run_id: str,
    reason: str,
) -> WindowsWorkspaceDecision:
    return WindowsWorkspaceDecision(
        strategy="copy_to_temp",
        source_root=source_root,
        source_root_kind=source_root_kind,
        workspace_root=_join_windows_path(temp_root, run_id),
        reason=reason,
        cleanup_on_success=True,
        keep_on_failure=True,
    )


def _join_windows_path(root: str, child: str) -> str:
    return root.rstrip("\\/") + "\\" + child.strip("\\/")


def _copyable_tree_items(root: Path, directory: Path) -> list[Path]:
    items: list[Path] = []
    for current_root, dirnames, filenames in os.walk(directory, followlinks=False):
        current = Path(current_root)
        _reject_escaping_symlink(root, current)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not _is_excluded_relative((current / dirname).relative_to(root))
        ]
        for dirname in list(dirnames):
            _reject_escaping_symlink(root, current / dirname)
        for filename in filenames:
            path = current / filename
            if _is_copyable_path(root, path):
                items.append(path.relative_to(root))
    return items


def _is_copyable_path(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    if _is_excluded_relative(relative):
        return False
    _reject_escaping_symlink(root, path)
    return path.is_file() or path.is_symlink()


def _is_excluded_relative(relative: Path) -> bool:
    return any(part in COPY_EXCLUDE_NAMES for part in relative.parts)


def _reject_escaping_symlink(root: Path, path: Path) -> None:
    if not path.is_symlink():
        return
    root_resolved = root.resolve()
    target = path.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise WindowsSmokeWorkspaceError(
            "workspace copy policy rejects symlinks escaping source_root",
            reason_code="windows_smoke_workspace_symlink_escape",
            details={"path": str(path), "target": str(target), "source_root": str(root)},
        ) from exc


def _detect_wsl_windows_interop() -> bool:
    return bool(os.environ.get("WSL_INTEROP") and shutil.which("powershell.exe"))


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


from .windows_smoke_runner import (  # noqa: E402
    WindowsCommandProfile,
    WindowsProcessResult,
    build_windows_powershell_helper_argv,
    build_windows_smoke_plan_from_profile,
    get_windows_command_profile,
    run_windows_native_smoke_plan,
)


__all__ = [
    "WINDOWS_SMOKE_SCHEMA_VERSION",
    "WindowsCommandProfile",
    "WindowsProcessResult",
    "WindowsSmokeWorkspaceError",
    "WindowsSmokePlan",
    "WindowsSmokeReport",
    "WindowsSmokeStep",
    "WindowsSmokeStepResult",
    "WindowsWorkspaceDecision",
    "build_windows_powershell_helper_argv",
    "build_windows_smoke_plan_from_profile",
    "collect_windows_workspace_copy_items",
    "get_windows_command_profile",
    "redact_public_summary",
    "resolve_windows_host_mode",
    "resolve_windows_workspace",
    "run_windows_native_smoke_plan",
]
