"""Compatibility import for the application terminal backend implementation."""

from isotope.execution.terminal_backend import (
    TerminalBackendAdapter,
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
    build_terminal_backend_request,
    default_terminal_backend_config,
)

__all__ = [
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
