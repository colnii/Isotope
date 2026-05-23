"""Codex CLI backend for the codex_task adapter boundary."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ...capabilities.tools.terminal import cap_terminal_output
from .task import (
    CodexTaskNotConfiguredError,
    CodexTaskOutputArtifact,
    CodexTaskProtocolError,
    CodexTaskRequest,
    CodexTaskResult,
)


ALLOWED_CODEX_CLI_SANDBOXES = {"read-only"}
ALLOWED_CODEX_CLI_APPROVAL_POLICIES = {"never"}
DEFAULT_CODEX_CLI_MAX_OUTPUT_BYTES = 65536
CODEX_CLI_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


@dataclass(frozen=True)
class CodexCliBackendConfig:
    workspace_root: str
    executable: str = "codex"
    codex_home: str | None = None
    sandbox: str = "read-only"
    approval_policy: str = "never"
    max_output_bytes: int = DEFAULT_CODEX_CLI_MAX_OUTPUT_BYTES
    ephemeral: bool = True
    ignore_user_config: bool = False
    skip_git_repo_check: bool = False
    inherit_proxy_env: bool = False
    model: str | None = None
    profile: str | None = None

    def __post_init__(self) -> None:
        _non_empty_string("workspace_root", self.workspace_root)
        _non_empty_string("executable", self.executable)
        if self.codex_home is not None:
            _non_empty_string("codex_home", self.codex_home)
        if self.sandbox not in ALLOWED_CODEX_CLI_SANDBOXES:
            raise ValueError("codex cli sandbox must be read-only in this first slice")
        if self.approval_policy not in ALLOWED_CODEX_CLI_APPROVAL_POLICIES:
            raise ValueError("codex cli approval_policy must be never in this first slice")
        if not isinstance(self.max_output_bytes, int) or self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be a positive integer")
        if not isinstance(self.ephemeral, bool):
            raise ValueError("ephemeral must be a bool")
        if not isinstance(self.ignore_user_config, bool):
            raise ValueError("ignore_user_config must be a bool")
        if not isinstance(self.skip_git_repo_check, bool):
            raise ValueError("skip_git_repo_check must be a bool")
        if not isinstance(self.inherit_proxy_env, bool):
            raise ValueError("inherit_proxy_env must be a bool")
        if self.model is not None:
            _non_empty_string("model", self.model)
        if self.profile is not None:
            _non_empty_string("profile", self.profile)


@dataclass(frozen=True)
class CodexSupervisorCliConfig:
    workspace_root: str
    executable: str = "codex"
    model: str | None = None
    config_overrides: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty_string("workspace_root", self.workspace_root)
        object.__setattr__(
            self,
            "executable",
            _stripped_non_empty_string("executable", self.executable),
        )
        if self.model is not None:
            object.__setattr__(
                self,
                "model",
                _stripped_non_empty_string("model", self.model),
            )
        object.__setattr__(
            self,
            "config_overrides",
            _config_overrides_tuple(self.config_overrides),
        )


def build_supervisor_launch_exec_argv(
    config: CodexSupervisorCliConfig,
    *,
    prompt: str,
) -> tuple[str, ...]:
    _validate_supervisor_config(config)
    prompt_text = _non_empty_string("prompt", prompt)
    return (
        config.executable,
        "exec",
        *build_supervisor_codex_option_args(config),
        "-C",
        _supervisor_workspace_root(config),
        "--skip-git-repo-check",
        prompt_text,
    )


def build_supervisor_interactive_argv(
    config: CodexSupervisorCliConfig,
    *,
    prompt: str,
) -> tuple[str, ...]:
    _validate_supervisor_config(config)
    prompt_text = _non_empty_string("prompt", prompt)
    return (
        config.executable,
        *build_supervisor_codex_option_args(config),
        "--cd",
        _supervisor_workspace_root(config),
        "--no-alt-screen",
        prompt_text,
    )


def build_supervisor_tmux_launch_command(
    config: CodexSupervisorCliConfig,
    *,
    tmux_session: str,
    prompt: str,
) -> tuple[str, ...]:
    tmux_session_text = _stripped_non_empty_string("tmux_session", tmux_session)
    return (
        "tmux",
        "new-session",
        "-d",
        "-s",
        tmux_session_text,
        "-c",
        _supervisor_workspace_root(config),
        shlex.join(build_supervisor_interactive_argv(config, prompt=prompt)),
    )


def build_supervisor_resume_exec_argv(
    config: CodexSupervisorCliConfig,
    *,
    prompt: str,
    session_id: str | None = None,
    last: bool = False,
) -> tuple[str, ...]:
    _validate_supervisor_config(config)
    prompt_text = _non_empty_string("prompt", prompt)
    session_text = _stripped_non_empty_string("session_id", session_id) if session_id else None
    if last and session_text:
        raise ValueError("use either session_id or last, not both")
    if not last and not session_text:
        raise ValueError("session_id or last is required")
    target = "--last" if last else session_text or ""
    return (
        config.executable,
        "exec",
        *build_supervisor_codex_option_args(config),
        "-C",
        _supervisor_workspace_root(config),
        "--skip-git-repo-check",
        "resume",
        target,
        prompt_text,
    )


def build_supervisor_codex_option_args(
    config: CodexSupervisorCliConfig,
) -> tuple[str, ...]:
    _validate_supervisor_config(config)
    args: list[str] = []
    if config.model is not None:
        args.extend(["-m", config.model])
    for item in config.config_overrides:
        args.extend(["-c", item])
    return tuple(args)


class CodexCliBackend:
    """Run Codex CLI as the backend for an already approved codex_task request."""

    def __init__(
        self,
        config: CodexCliBackendConfig,
        *,
        process_runner: Callable[..., Any] = subprocess.run,
        executable_resolver: Callable[[str], str | None] = shutil.which,
    ) -> None:
        if not isinstance(config, CodexCliBackendConfig):
            raise TypeError("config must be a CodexCliBackendConfig")
        self.config = config
        self.process_runner = process_runner
        self.executable_path = _resolve_executable(config.executable, executable_resolver)
        self.workspace_root = Path(config.workspace_root).expanduser().resolve()
        self.codex_home = (
            Path(config.codex_home).expanduser().resolve()
            if config.codex_home is not None
            else None
        )

    def run(self, request: CodexTaskRequest) -> CodexTaskResult:
        if not isinstance(request, CodexTaskRequest):
            raise TypeError("run requires a CodexTaskRequest")
        self._validate_request_scope(request)
        prompt = _non_empty_string("task_request.prompt", request.task_request.get("prompt"))
        timeout_seconds = _timeout_seconds_from(request)
        argv = self._argv()
        env = self._env()
        started_at = _utc_now()
        started_monotonic = time.monotonic()
        try:
            completed = self.process_runner(
                argv,
                cwd=str(self.workspace_root),
                env=env,
                input=prompt,
                text=True,
                capture_output=True,
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            finished_at = _utc_now()
            duration_ms = _duration_ms(started_monotonic)
            stdout, stderr, truncated = cap_terminal_output(
                _timeout_text(exc.output),
                _timeout_text(exc.stderr),
                max_output_bytes=self.config.max_output_bytes,
            )
            return self._result(
                request=request,
                status="timeout",
                reason_code="codex_cli_timeout",
                retryable=True,
                started_at=started_at,
                finished_at=finished_at,
                stdout=stdout,
                stderr=stderr,
                exit_code=None,
                timeout_seconds=timeout_seconds,
                duration_ms=duration_ms,
                truncated=truncated,
            )
        except OSError as exc:
            raise CodexTaskNotConfiguredError(
                "codex cli process could not be started",
                details={"executable": self.config.executable},
            ) from exc

        finished_at = _utc_now()
        duration_ms = _duration_ms(started_monotonic)
        stdout, stderr, truncated = cap_terminal_output(
            getattr(completed, "stdout", ""),
            getattr(completed, "stderr", ""),
            max_output_bytes=self.config.max_output_bytes,
        )
        exit_code = _exit_code_from(completed)
        if exit_code == 0:
            status = "completed"
            reason_code = "codex_cli_completed"
            retryable = False
        else:
            status = "failed"
            reason_code = "codex_cli_exit_nonzero"
            retryable = False
        return self._result(
            request=request,
            status=status,
            reason_code=reason_code,
            retryable=retryable,
            started_at=started_at,
            finished_at=finished_at,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timeout_seconds=timeout_seconds,
            duration_ms=duration_ms,
            truncated=truncated,
        )

    def _validate_request_scope(self, request: CodexTaskRequest) -> None:
        if request.workspace_binding.get("mode") != "shared_ro":
            raise CodexTaskProtocolError(
                "codex cli backend requires shared_ro workspace binding",
                reason_code="codex_cli_workspace_not_granted",
            )
        if request.grants.get("workspace", {}).get("mode") != "shared_ro":
            raise CodexTaskProtocolError(
                "codex cli backend requires shared_ro workspace grant",
                reason_code="codex_cli_workspace_not_granted",
            )

    def _argv(self) -> list[str]:
        argv = [
            self.executable_path,
            "--ask-for-approval",
            self.config.approval_policy,
            "exec",
            "--json",
            "--color",
            "never",
            "--sandbox",
            self.config.sandbox,
            "--cd",
            str(self.workspace_root),
        ]
        if self.config.ephemeral:
            argv.append("--ephemeral")
        if self.config.ignore_user_config:
            argv.append("--ignore-user-config")
        if self.config.skip_git_repo_check:
            argv.append("--skip-git-repo-check")
        if self.config.model is not None:
            argv.extend(["--model", self.config.model])
        if self.config.profile is not None:
            argv.extend(["--profile", self.config.profile])
        argv.append("-")
        return argv

    def _env(self) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        if self.codex_home is not None:
            env["CODEX_HOME"] = str(self.codex_home)
        if self.config.inherit_proxy_env:
            for name in CODEX_CLI_PROXY_ENV_NAMES:
                value = os.environ.get(name)
                if value:
                    env[name] = value
        return env

    def _result(
        self,
        *,
        request: CodexTaskRequest,
        status: str,
        reason_code: str,
        retryable: bool,
        started_at: str,
        finished_at: str,
        stdout: str,
        stderr: str,
        exit_code: int | None,
        timeout_seconds: int,
        duration_ms: int,
        truncated: bool,
    ) -> CodexTaskResult:
        transcript = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "timeout_seconds": timeout_seconds,
            "duration_ms": duration_ms,
            "truncated": truncated,
            "max_output_bytes": self.config.max_output_bytes,
            "shell": False,
            "cwd": str(self.workspace_root),
            "argv": self._argv(),
            "stdin_prompt_bytes": len(request.task_request["prompt"].encode("utf-8")),
        }
        return CodexTaskResult(
            adapter_session_id=f"codex_cli:{request.execution_id}",
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            summary=_summary_for(status),
            output_artifacts=[
                CodexTaskOutputArtifact(
                    artifact_type="codex_task_transcript",
                    summary="codex cli transcript captured",
                    content=json.dumps(transcript, sort_keys=True),
                )
            ],
            reason_code=reason_code,
            retryable=retryable,
            resource_usage={
                "exit_code": exit_code,
                "timeout_seconds": timeout_seconds,
                "duration_ms": duration_ms,
                "stdout_bytes": len(stdout.encode("utf-8")),
                "stderr_bytes": len(stderr.encode("utf-8")),
                "truncated": truncated,
            },
        )


def _resolve_executable(
    executable: str,
    executable_resolver: Callable[[str], str | None],
) -> str:
    _non_empty_string("executable", executable)
    if "/" in executable or "\\" in executable:
        path = Path(executable).expanduser()
        if not path.is_absolute():
            raise ValueError("codex cli executable path must be absolute")
        return str(path.resolve(strict=False))
    resolved = executable_resolver(executable)
    if not resolved:
        raise CodexTaskNotConfiguredError(
            "codex cli executable was not found",
            details={"executable": executable},
        )
    return str(Path(resolved).expanduser().resolve(strict=False))


def _timeout_seconds_from(request: CodexTaskRequest) -> int:
    try:
        timeout_seconds = int(request.budget.get("seconds", 0))
    except (TypeError, ValueError) as exc:
        raise CodexTaskProtocolError(
            "codex cli budget seconds must be int-like",
            reason_code="codex_cli_budget_malformed",
        ) from exc
    if timeout_seconds <= 0:
        raise CodexTaskProtocolError(
            "codex cli budget seconds must be positive",
            reason_code="codex_cli_budget_malformed",
        )
    return timeout_seconds


def _exit_code_from(completed: Any) -> int:
    exit_code = getattr(completed, "returncode", None)
    if not isinstance(exit_code, int):
        raise CodexTaskProtocolError(
            "codex cli process result missing integer returncode",
            reason_code="codex_cli_process_result_malformed",
        )
    return exit_code


def _timeout_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def _summary_for(status: str) -> str:
    if status == "completed":
        return "codex cli completed"
    if status == "timeout":
        return "codex cli timed out"
    return "codex cli failed"


def _duration_ms(started_monotonic: float) -> int:
    return max(0, int((time.monotonic() - started_monotonic) * 1000))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain NUL")
    return value


def _stripped_non_empty_string(field_name: str, value: Any) -> str:
    raw = _non_empty_string(field_name, value)
    stripped = raw.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be a non-empty string")
    return stripped


def _config_overrides_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("config_overrides must be a list or tuple")
    return tuple(
        _stripped_non_empty_string("config_overrides entries", item)
        for item in value
    )


def _validate_supervisor_config(config: CodexSupervisorCliConfig) -> None:
    if not isinstance(config, CodexSupervisorCliConfig):
        raise TypeError("config must be a CodexSupervisorCliConfig")


def _supervisor_workspace_root(config: CodexSupervisorCliConfig) -> str:
    _validate_supervisor_config(config)
    return str(Path(config.workspace_root).expanduser())


__all__ = [
    "CodexCliBackend",
    "CodexCliBackendConfig",
    "CodexSupervisorCliConfig",
    "build_supervisor_codex_option_args",
    "build_supervisor_interactive_argv",
    "build_supervisor_launch_exec_argv",
    "build_supervisor_resume_exec_argv",
    "build_supervisor_tmux_launch_command",
]
