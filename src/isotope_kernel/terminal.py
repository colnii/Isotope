"""Compatibility import for the application terminal tool implementation."""

from agents.tools.terminal import (
    ControlledTerminalRunner,
    TerminalExecutionError,
    TerminalExecutionResult,
    cap_terminal_output,
    default_terminal_capabilities,
    terminal_grant_from,
    validate_argv,
)

__all__ = [
    "ControlledTerminalRunner",
    "TerminalExecutionError",
    "TerminalExecutionResult",
    "cap_terminal_output",
    "default_terminal_capabilities",
    "terminal_grant_from",
    "validate_argv",
]
