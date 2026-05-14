"""Compatibility proxy.

New path:
    isotope.execution.terminal_runner

Planned removal:
    after import-map confirms no active internal imports.
"""

from isotope.execution.terminal_runner import (
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
