from __future__ import annotations

from agents.executor import terminal_backend as app_terminal_backend
from agents.tools import terminal as app_terminal
from isotope_kernel import terminal as legacy_terminal
from isotope_kernel import terminal_backend as legacy_terminal_backend
from isotope_kernel import terminal_system_runner as legacy_terminal_system_runner


def test_legacy_terminal_module_reexports_app_terminal_symbols():
    assert legacy_terminal.ControlledTerminalRunner is app_terminal.ControlledTerminalRunner
    assert legacy_terminal.TerminalExecutionError is app_terminal.TerminalExecutionError
    assert legacy_terminal.TerminalExecutionResult is app_terminal.TerminalExecutionResult
    assert legacy_terminal.cap_terminal_output is app_terminal.cap_terminal_output
    assert legacy_terminal.default_terminal_capabilities is app_terminal.default_terminal_capabilities
    assert legacy_terminal.terminal_grant_from is app_terminal.terminal_grant_from
    assert legacy_terminal.validate_argv is app_terminal.validate_argv


def test_legacy_terminal_backend_module_reexports_app_backend_symbols():
    assert legacy_terminal_backend.TerminalBackendAdapter is app_terminal_backend.TerminalBackendAdapter
    assert legacy_terminal_backend.TerminalBackendConfig is app_terminal_backend.TerminalBackendConfig
    assert legacy_terminal_backend.TerminalBackendProtocolError is app_terminal_backend.TerminalBackendProtocolError
    assert legacy_terminal_backend.TerminalBackendResult is app_terminal_backend.TerminalBackendResult
    assert legacy_terminal_backend.TerminalBackendRunResult is app_terminal_backend.TerminalBackendRunResult
    assert legacy_terminal_backend.build_terminal_backend_request is app_terminal_backend.build_terminal_backend_request


def test_legacy_terminal_system_runner_reexports_app_linux_runner():
    assert legacy_terminal_system_runner.LinuxSystemTerminalRunner is app_terminal_backend.LinuxSystemTerminalRunner
