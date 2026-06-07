"""Explicit server wiring for the Codex CLI codex_task backend."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ...platform.registry.actions import ActionTypeRegistry
from ...runtime.in_process import InProcessServer
from .cli import (
    DEFAULT_CODEX_CLI_MAX_OUTPUT_BYTES,
    CodexCliBackend,
    CodexCliBackendConfig,
)
from .task import SUPPORTED_CODEX_TASK_PROTOCOL_VERSION


DEFAULT_CODEX_CLI_SERVER_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class CodexCliServerConfig:
    """Configuration for explicitly enabling codex_task on an in-process server."""

    workspace_root: str
    executable: str = "codex"
    codex_home: str | None = None
    timeout_seconds: int = DEFAULT_CODEX_CLI_SERVER_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_CODEX_CLI_MAX_OUTPUT_BYTES
    skip_git_repo_check: bool = True
    inherit_proxy_env: bool = True
    model: str | None = None
    profile: str | None = None
    adapter_id: str = "codex_cli"
    adapter_version: str = "server-wiring.v0.1"

    def __post_init__(self) -> None:
        _non_empty_string("workspace_root", self.workspace_root)
        _non_empty_string("executable", self.executable)
        if self.codex_home is not None:
            _non_empty_string("codex_home", self.codex_home)
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        if not isinstance(self.max_output_bytes, int) or self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be a positive integer")
        if not isinstance(self.skip_git_repo_check, bool):
            raise ValueError("skip_git_repo_check must be a bool")
        if not isinstance(self.inherit_proxy_env, bool):
            raise ValueError("inherit_proxy_env must be a bool")
        if self.model is not None:
            _non_empty_string("model", self.model)
        if self.profile is not None:
            _non_empty_string("profile", self.profile)
        _non_empty_string("adapter_id", self.adapter_id)
        _non_empty_string("adapter_version", self.adapter_version)


def create_codex_cli_server(
    root: Path | str,
    *,
    config: CodexCliServerConfig,
    checkpoint_store: Any | None = None,
    process_runner: Callable[..., Any] = subprocess.run,
    executable_resolver: Callable[[str], str | None] = shutil.which,
) -> InProcessServer:
    """Create an InProcessServer with codex_task explicitly wired to local Codex CLI."""

    if not isinstance(config, CodexCliServerConfig):
        raise TypeError("config must be a CodexCliServerConfig")
    workspace_root = Path(config.workspace_root).expanduser().resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    backend = CodexCliBackend(
        CodexCliBackendConfig(
            workspace_root=str(workspace_root),
            executable=config.executable,
            codex_home=config.codex_home,
            sandbox="read-only",
            approval_policy="never",
            max_output_bytes=config.max_output_bytes,
            skip_git_repo_check=config.skip_git_repo_check,
            inherit_proxy_env=config.inherit_proxy_env,
            model=config.model,
            profile=config.profile,
        ),
        process_runner=process_runner,
        executable_resolver=executable_resolver,
    )
    return InProcessServer(
        Path(root),
        checkpoint_store=checkpoint_store,
        registry=ActionTypeRegistry.default(
            enable_codex_task=True,
            codex_task_budget_seconds=config.timeout_seconds,
        ),
        codex_task_adapter=backend,
        codex_task_adapter_config={
            "adapter_id": config.adapter_id,
            "adapter_version": config.adapter_version,
            "protocol_version": SUPPORTED_CODEX_TASK_PROTOCOL_VERSION,
            "mode": "agent_cli_task",
        },
    )


def _non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain NUL")
    return value


__all__ = [
    "CodexCliServerConfig",
    "create_codex_cli_server",
]
