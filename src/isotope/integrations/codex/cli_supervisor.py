"""Codex CLI argument builders for Supervisor-managed workers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cli_validation import non_empty_string, stripped_non_empty_string


@dataclass(frozen=True)
class CodexSupervisorCliConfig:
    workspace_root: str
    executable: str = "codex"
    model: str | None = None
    config_overrides: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        non_empty_string("workspace_root", self.workspace_root)
        object.__setattr__(
            self,
            "executable",
            stripped_non_empty_string("executable", self.executable),
        )
        if self.model is not None:
            object.__setattr__(
                self,
                "model",
                stripped_non_empty_string("model", self.model),
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
    prompt_text = non_empty_string("prompt", prompt)
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
    prompt_text = non_empty_string("prompt", prompt)
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
    tmux_session_text = stripped_non_empty_string("tmux_session", tmux_session)
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
    prompt_text = non_empty_string("prompt", prompt)
    session_text = stripped_non_empty_string("session_id", session_id) if session_id else None
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


def _config_overrides_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("config_overrides must be a list or tuple")
    return tuple(
        stripped_non_empty_string("config_overrides entries", item)
        for item in value
    )


def _validate_supervisor_config(config: CodexSupervisorCliConfig) -> None:
    if not isinstance(config, CodexSupervisorCliConfig):
        raise TypeError("config must be a CodexSupervisorCliConfig")


def _supervisor_workspace_root(config: CodexSupervisorCliConfig) -> str:
    _validate_supervisor_config(config)
    return str(Path(config.workspace_root).expanduser())


__all__ = [
    "CodexSupervisorCliConfig",
    "build_supervisor_codex_option_args",
    "build_supervisor_interactive_argv",
    "build_supervisor_launch_exec_argv",
    "build_supervisor_resume_exec_argv",
    "build_supervisor_tmux_launch_command",
]
