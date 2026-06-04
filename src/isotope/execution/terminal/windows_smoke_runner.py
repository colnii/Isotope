"""Fixed-profile execution helpers for the Windows smoke harness."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from isotope.capabilities.tools.terminal import cap_terminal_output

from .windows_smoke import (
    WindowsSmokePlan,
    WindowsSmokeReport,
    WindowsSmokeStep,
    WindowsSmokeStepResult,
    WindowsWorkspaceDecision,
    redact_public_summary,
)


RUNNER_VERSION = "windows-smoke-runner.v0.1"
PROFILE_VERSION = "2026-06-02"
PROFILE_BACKED_SCRIPT_COMMANDS = {"npm", "pnpm", "yarn", "npx"}
WINDOWS_PROCESS_ENV_ALLOWLIST = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "WINDIR",
    "ComSpec",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "ProgramData",
    "ProgramFiles",
    "ProgramFiles(x86)",
    "PROCESSOR_ARCHITECTURE",
)
ProcessRunner = Callable[..., "WindowsProcessResult"]
CleanupProcessTree = Callable[[int | None], dict[str, Any]]


@dataclass(frozen=True)
class WindowsCommandProfile:
    id: str
    description: str
    profile_version: str
    steps: list[WindowsSmokeStep]
    required_tools: list[str]
    cwd_policy: str
    env_policy: str
    timeout_seconds: int
    allowed_executable_extensions: list[str]
    required_artifacts: list[str]
    mutation_policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "profile_version": self.profile_version,
            "steps": [step.to_dict() for step in self.steps],
            "required_tools": list(self.required_tools),
            "cwd_policy": self.cwd_policy,
            "env_policy": self.env_policy,
            "timeout_seconds": self.timeout_seconds,
            "allowed_executable_extensions": list(self.allowed_executable_extensions),
            "required_artifacts": list(self.required_artifacts),
            "mutation_policy": self.mutation_policy,
        }


@dataclass(frozen=True)
class WindowsProcessResult:
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


def get_windows_command_profile(profile_id: str) -> WindowsCommandProfile:
    try:
        return _WINDOWS_COMMAND_PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown windows command profile: {profile_id}") from exc


def build_windows_smoke_plan_from_profile(
    profile_id: str,
    *,
    source_root: str | Path,
    workspace_strategy: str = "auto",
    timeout_seconds: int | None = None,
    max_output_bytes: int = 4096,
) -> WindowsSmokePlan:
    profile = get_windows_command_profile(profile_id)
    return WindowsSmokePlan(
        source_root=source_root,
        profile_id=profile.id,
        profile_version=profile.profile_version,
        workspace_strategy=workspace_strategy,
        steps=list(profile.steps),
        timeout_seconds=timeout_seconds or profile.timeout_seconds,
        max_output_bytes=max_output_bytes,
    )


def run_windows_native_smoke_plan(
    plan: WindowsSmokePlan,
    *,
    host_mode: str,
    source_root_kind: str,
    workspace_decision: WindowsWorkspaceDecision,
    process_runner: ProcessRunner | None = None,
    cleanup_process_tree: CleanupProcessTree | None = None,
    now: Callable[[], str] | None = None,
    platform_info: dict[str, Any] | None = None,
    tool_versions: dict[str, str] | None = None,
    repo_revision_if_available: str | None = None,
) -> WindowsSmokeReport:
    if not isinstance(plan, WindowsSmokePlan):
        raise TypeError("run_windows_native_smoke_plan requires a WindowsSmokePlan")
    if not isinstance(workspace_decision, WindowsWorkspaceDecision):
        raise TypeError("workspace_decision must be a WindowsWorkspaceDecision")
    process_runner = process_runner or _subprocess_process_runner
    cleanup_process_tree = cleanup_process_tree or _default_process_tree_cleanup
    now = now or _utc_now

    report_started_at = now()
    diagnostic_steps: list[dict[str, Any]] = []
    status = "completed"
    reason_code = "windows_smoke_completed"
    missing_artifacts: list[str] = []

    for step in plan.steps:
        step_started_at = now()
        cwd = _resolve_step_cwd(workspace_decision.workspace_root or str(plan.source_root), step.cwd)
        result = process_runner(
            argv=list(step.argv),
            cwd=cwd,
            env_overlay=dict(step.env_overlay),
            timeout_seconds=plan.timeout_seconds,
        )
        step_finished_at = now()
        stdout, stderr, truncated = cap_terminal_output(
            result.stdout,
            result.stderr,
            max_output_bytes=plan.max_output_bytes,
        )
        step_reason_code = _step_reason_code(result)
        cleanup_result: dict[str, Any] = {"attempted": False, "succeeded": None, "method": None}
        if result.timed_out:
            cleanup_result = cleanup_process_tree(result.process_id)

        step_result = WindowsSmokeStepResult(
            name=step.name,
            argv=list(step.argv),
            cwd=cwd,
            started_at=step_started_at,
            finished_at=step_finished_at,
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
            reason_code=step_reason_code,
            artifacts=[],
            copied_workspace_path=(
                workspace_decision.workspace_root if workspace_decision.strategy == "copy_to_temp" else None
            ),
            process_tree_cleanup=cleanup_result,
        )
        diagnostic_steps.append(step_result.to_dict())

        if result.timed_out:
            status = "timeout"
            reason_code = "windows_smoke_command_timeout"
            break
        if result.start_error:
            status = "failed"
            reason_code = "windows_smoke_command_start_failed"
            break
        if result.exit_code != 0:
            status = "failed"
            reason_code = "windows_smoke_command_exit_nonzero"
            break

        missing_artifacts = _missing_required_artifacts(
            workspace_decision.workspace_root or str(plan.source_root),
            step.required_artifacts,
        )
        if missing_artifacts:
            status = "failed"
            reason_code = "windows_smoke_required_artifact_missing"
            break

    diagnostic_report: dict[str, Any] = {
        "source_root": str(plan.source_root),
        "workspace_root": workspace_decision.workspace_root,
        "workspace_decision": workspace_decision.to_dict(),
        "steps": diagnostic_steps,
    }
    if missing_artifacts:
        diagnostic_report["missing_artifacts"] = missing_artifacts
    public_summary = redact_public_summary(
        status=status,
        reason_code=reason_code,
        profile_id=plan.profile_id,
        host_mode=host_mode,
        workspace_strategy_decision=workspace_decision.to_dict(),
        diagnostic_report=diagnostic_report,
        redaction_paths=[
            path
            for path in (
                str(plan.source_root),
                workspace_decision.workspace_root,
                os.environ.get("USERPROFILE"),
                os.environ.get("HOME"),
            )
            if path
        ],
    )
    return WindowsSmokeReport(
        runner_version=RUNNER_VERSION,
        profile_id=plan.profile_id,
        profile_version=plan.profile_version,
        host_mode=host_mode,
        platform_info=dict(platform_info or {}),
        tool_versions=dict(tool_versions or {}),
        source_root_kind=source_root_kind,
        workspace_strategy_decision=workspace_decision.to_dict(),
        repo_revision_if_available=repo_revision_if_available,
        started_at=report_started_at,
        finished_at=now(),
        status=status,
        reason_code=reason_code,
        diagnostic_report=diagnostic_report,
        public_summary=public_summary,
    )


def build_windows_powershell_helper_argv(
    *,
    helper_script: str | Path,
    request_json: str | Path,
    result_json: str | Path,
) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(helper_script),
        str(request_json),
        str(result_json),
    ]


def _step_reason_code(result: WindowsProcessResult) -> str:
    if result.timed_out:
        return "windows_smoke_command_timeout"
    if result.start_error:
        return "windows_smoke_command_start_failed"
    if result.exit_code != 0:
        return "windows_smoke_command_exit_nonzero"
    return "windows_smoke_command_completed"


def _resolve_step_cwd(workspace_root: str, step_cwd: str) -> str:
    if step_cwd in {"", "."}:
        return workspace_root
    if "\\" in workspace_root or _looks_like_windows_drive(workspace_root):
        return workspace_root.rstrip("\\/") + "\\" + step_cwd.strip("\\/")
    return str(Path(workspace_root) / step_cwd)


def _looks_like_windows_drive(path: str) -> bool:
    return len(path) >= 3 and path[1:3] == ":\\" and path[0].isalpha()


def _missing_required_artifacts(workspace_root: str, required_artifacts: list[str]) -> list[str]:
    if not required_artifacts:
        return []
    missing: list[str] = []
    for artifact in required_artifacts:
        path = _resolve_step_cwd(workspace_root, artifact)
        if not Path(path).exists():
            missing.append(artifact)
    return missing


def _subprocess_process_runner(
    *,
    argv: list[str],
    cwd: str,
    env_overlay: dict[str, str],
    timeout_seconds: int,
) -> WindowsProcessResult:
    env = _sanitized_smoke_env(env_overlay=env_overlay)
    try:
        process_argv = _resolve_smoke_process_argv(argv)
        process = subprocess.Popen(
            process_argv,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return WindowsProcessResult(
            exit_code=None,
            stdout=_timeout_text(exc.stdout),
            stderr=_timeout_text(exc.stderr),
            timed_out=True,
            process_id=process.pid,
        )
    except OSError as exc:
        return WindowsProcessResult(
            exit_code=None,
            stdout="",
            stderr=str(exc),
            timed_out=False,
            start_error=str(exc),
        )
    return WindowsProcessResult(
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
    )


def _resolve_smoke_process_argv(
    argv: list[str],
    *,
    platform_name: str | None = None,
    executable_resolver: Callable[[str], str | None] | None = None,
    comspec: str | None = None,
) -> list[str] | str:
    if (platform_name or os.name) != "nt":
        return list(argv)
    resolver = executable_resolver or shutil.which
    resolved = resolver(argv[0])
    if not resolved:
        return list(argv)
    suffix = Path(resolved).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        if argv[0].lower() not in PROFILE_BACKED_SCRIPT_COMMANDS:
            raise OSError("Windows smoke .cmd/.bat execution requires a profile-backed command")
        command_line = f'"{comspec or os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe")}" /d /s /c ""{resolved}"'
        if len(argv) > 1:
            command_line += " " + subprocess.list2cmdline(argv[1:])
        return command_line + '"'
    return [resolved, *argv[1:]]


def _sanitized_smoke_env(
    *,
    env_overlay: dict[str, str] | None = None,
    platform_name: str | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    source = base_env or os.environ
    if (platform_name or os.name) == "nt":
        env = {
            key: source[key]
            for key in WINDOWS_PROCESS_ENV_ALLOWLIST
            if key in source and isinstance(source[key], str)
        }
        env.setdefault("PATH", os.defpath)
    else:
        env = {
            "PATH": source.get("PATH", os.defpath),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
    env.update(dict(env_overlay or {}))
    return env


def _default_process_tree_cleanup(process_id: int | None) -> dict[str, Any]:
    if process_id is None:
        return {"attempted": False, "succeeded": None, "method": None}
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


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_WINDOWS_COMMAND_PROFILES = {
    "desktop_tools_versions": WindowsCommandProfile(
        id="desktop_tools_versions",
        description="Capture desktop toolchain versions without mutating the workspace.",
        profile_version=PROFILE_VERSION,
        steps=[
            WindowsSmokeStep(name="node_version", argv=["node", "--version"], cwd="."),
            WindowsSmokeStep(name="npm_version", argv=["npm", "--version"], cwd="."),
            WindowsSmokeStep(name="python_version", argv=["python", "--version"], cwd="."),
        ],
        required_tools=["node", "npm", "python"],
        cwd_policy="workspace_root",
        env_policy="profile_defined_overlay_only",
        timeout_seconds=30,
        allowed_executable_extensions=[".exe", ".cmd"],
        required_artifacts=[],
        mutation_policy="read_snapshot",
    ),
    "desktop_frontend_check": WindowsCommandProfile(
        id="desktop_frontend_check",
        description="Install desktop frontend dependencies and run the check script.",
        profile_version=PROFILE_VERSION,
        steps=[
            WindowsSmokeStep(name="npm_ci", argv=["npm", "ci"], cwd="apps/desktop"),
            WindowsSmokeStep(name="npm_run_check", argv=["npm", "run", "check"], cwd="apps/desktop"),
        ],
        required_tools=["npm", "node"],
        cwd_policy="apps_desktop",
        env_policy="profile_defined_overlay_only",
        timeout_seconds=180,
        allowed_executable_extensions=[".exe", ".cmd"],
        required_artifacts=[],
        mutation_policy="build",
    ),
    "desktop_frontend_build": WindowsCommandProfile(
        id="desktop_frontend_build",
        description="Install desktop frontend dependencies and build the desktop frontend.",
        profile_version=PROFILE_VERSION,
        steps=[
            WindowsSmokeStep(name="npm_ci", argv=["npm", "ci"], cwd="apps/desktop"),
            WindowsSmokeStep(name="npm_run_build", argv=["npm", "run", "build"], cwd="apps/desktop"),
        ],
        required_tools=["npm", "node"],
        cwd_policy="apps_desktop",
        env_policy="profile_defined_overlay_only",
        timeout_seconds=300,
        allowed_executable_extensions=[".exe", ".cmd"],
        required_artifacts=[],
        mutation_policy="build",
    ),
}


__all__ = [
    "WindowsCommandProfile",
    "WindowsProcessResult",
    "build_windows_powershell_helper_argv",
    "build_windows_smoke_plan_from_profile",
    "get_windows_command_profile",
    "run_windows_native_smoke_plan",
]
