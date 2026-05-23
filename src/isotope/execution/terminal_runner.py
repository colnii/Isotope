"""Terminal backend adapter and local runner for application agents."""

from __future__ import annotations

from .terminal_backend_adapter import TerminalBackendAdapter
from .terminal_backend_policy import build_terminal_backend_request, default_terminal_backend_config
from .terminal_backend_types import (
    TerminalBackendCancelResult,
    TerminalBackendConfig,
    TerminalBackendExecutionError,
    TerminalBackendFailure,
    TerminalBackendNotConfiguredError,
    TerminalBackendOutputArtifact,
    TerminalBackendProtocolError,
    TerminalBackendRequest,
    TerminalBackendResult,
    TerminalBackendRunResult,
)
from .terminal_linux_runner import LinuxSystemTerminalRunner


__all__ = [
    "LinuxSystemTerminalRunner",
    "TerminalBackendAdapter",
    "TerminalBackendCancelResult",
    "TerminalBackendConfig",
    "TerminalBackendExecutionError",
    "TerminalBackendFailure",
    "TerminalBackendNotConfiguredError",
    "TerminalBackendOutputArtifact",
    "TerminalBackendProtocolError",
    "TerminalBackendRequest",
    "TerminalBackendResult",
    "TerminalBackendRunResult",
    "build_terminal_backend_request",
    "default_terminal_backend_config",
]
