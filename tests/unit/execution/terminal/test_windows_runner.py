from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

import pytest

from isotope.execution.terminal.runner import (
    TerminalBackendRequest,
    WindowsSystemTerminalRunner,
    WindowsTerminalProcessResult,
)
from isotope.execution.terminal.windows_runner import _sanitized_windows_env


def test_windows_system_terminal_runner_rejects_non_exec_argv(tmp_path):
    request = _request(command_request={"kind": "backend_native_task", "task": {"prompt": "inspect"}})
    runner = WindowsSystemTerminalRunner(tmp_path, executable_resolver=lambda _: "C:\\Tools\\safe.exe")

    with pytest.raises(ValueError, match="only supports exec_argv"):
        runner.run(request)


def test_windows_system_terminal_runner_requires_shell_false_and_allowlist(tmp_path):
    shell_request = _request(
        grants={
            "terminal": {
                "shell": True,
                "argv_policy": "allowlist",
                "allowed_commands": ["safe"],
            }
        }
    )
    disallowed_request = _request(argv=["unsafe"])
    runner = WindowsSystemTerminalRunner(tmp_path, executable_resolver=lambda _: "C:\\Tools\\safe.exe")

    with pytest.raises(ValueError, match="requires shell=False"):
        runner.run(shell_request)
    with pytest.raises(PermissionError, match="not allowed"):
        runner.run(disallowed_request)


def test_windows_system_terminal_runner_records_resolved_executable_and_transcript(tmp_path):
    calls = []

    def process_runner(*, argv, cwd, timeout_seconds):
        calls.append({"argv": argv, "cwd": cwd, "timeout_seconds": timeout_seconds})
        return WindowsTerminalProcessResult(exit_code=0, stdout="hello from windows", stderr="", timed_out=False)

    runner = WindowsSystemTerminalRunner(
        tmp_path,
        executable_resolver=lambda command: f"C:\\Tools\\{command}.exe",
        process_runner=process_runner,
    )

    result = runner.run(_request(argv=["safe", "--version"], max_output_bytes=8))

    assert result.status == "completed"
    assert result.reason_code == "terminal_windows_runner_completed"
    assert result.exit_code == 0
    assert "hello from windows" not in result.summary
    assert calls == [
        {
            "argv": ["C:\\Tools\\safe.exe", "--version"],
            "cwd": str(tmp_path.resolve()),
            "timeout_seconds": 5,
        }
    ]
    transcript = json.loads(result.output_artifacts[0].content)
    assert transcript["argv"] == ["safe", "--version"]
    assert transcript["resolved_executable"] == "C:\\Tools\\safe.exe"
    assert transcript["stdout"] == "hello fr"
    assert transcript["truncated"] is True
    assert transcript["shell"] is False
    assert transcript["platform"] == "windows"
    assert transcript["process_tree_cleanup"] == {"attempted": False, "succeeded": None, "method": None}


def test_windows_system_terminal_runner_rejects_cmd_bat_and_package_manager_exec_argv(tmp_path):
    cmd_runner = WindowsSystemTerminalRunner(
        tmp_path,
        executable_resolver=lambda command: f"C:\\Tools\\{command}.cmd",
    )
    npm_runner = WindowsSystemTerminalRunner(
        tmp_path,
        executable_resolver=lambda command: f"C:\\Tools\\{command}.exe",
    )

    with pytest.raises(PermissionError, match=".cmd"):
        cmd_runner.run(_request(argv=["safe"]))
    with pytest.raises(PermissionError, match="profile-backed"):
        npm_runner.run(_request(argv=["npm"], allowed_commands=["npm"]))


def test_windows_system_terminal_runner_reports_nonzero_timeout_and_start_failure(tmp_path):
    nonzero_runner = WindowsSystemTerminalRunner(
        tmp_path,
        executable_resolver=lambda command: f"C:\\Tools\\{command}.exe",
        process_runner=lambda **_: WindowsTerminalProcessResult(
            exit_code=5,
            stdout="",
            stderr="bad",
            timed_out=False,
        ),
    )
    timeout_runner = WindowsSystemTerminalRunner(
        tmp_path,
        executable_resolver=lambda command: f"C:\\Tools\\{command}.exe",
        process_runner=lambda **_: WindowsTerminalProcessResult(
            exit_code=None,
            stdout="partial",
            stderr="timeout",
            timed_out=True,
            process_id=99,
        ),
        cleanup_process_tree=lambda process_id: {
            "attempted": True,
            "succeeded": True,
            "method": "taskkill",
            "process_id": process_id,
        },
    )
    start_failure_runner = WindowsSystemTerminalRunner(
        tmp_path,
        executable_resolver=lambda command: f"C:\\Tools\\{command}.exe",
        process_runner=lambda **_: WindowsTerminalProcessResult(
            exit_code=None,
            stdout="",
            stderr="cannot start",
            timed_out=False,
            start_error="cannot start",
        ),
    )

    nonzero = nonzero_runner.run(_request(argv=["safe"]))
    timeout = timeout_runner.run(_request(argv=["safe"]))
    start_failure = start_failure_runner.run(_request(argv=["safe"]))

    assert nonzero.status == "failed"
    assert nonzero.reason_code == "terminal_windows_runner_exit_nonzero"
    assert nonzero.exit_code == 5
    assert timeout.status == "timeout"
    assert timeout.reason_code == "terminal_windows_runner_timeout"
    assert timeout.retryable is True
    assert json.loads(timeout.output_artifacts[0].content)["process_tree_cleanup"] == {
        "attempted": True,
        "succeeded": True,
        "method": "taskkill",
        "process_id": 99,
    }
    assert start_failure.status == "failed"
    assert start_failure.reason_code == "terminal_windows_runner_start_failed"


def test_windows_system_terminal_runner_default_runner_exposes_pid_for_timeout_cleanup(tmp_path):
    python_exe = _python_executable_with_exe_suffix(tmp_path)
    cleanup_calls = []
    runner = WindowsSystemTerminalRunner(
        tmp_path,
        executable_resolver=lambda command: str(python_exe),
        cleanup_process_tree=lambda process_id: _record_and_terminate(cleanup_calls, process_id),
    )

    result = runner.run(
        _request(
            argv=["python", "-c", "import time; time.sleep(10)"],
            allowed_commands=["python"],
            timeout_seconds=1,
        )
    )

    assert result.status == "timeout"
    assert result.reason_code == "terminal_windows_runner_timeout"
    assert cleanup_calls and isinstance(cleanup_calls[0], int)


def test_windows_runner_env_preserves_required_windows_process_variables():
    env = _sanitized_windows_env(
        platform_name="nt",
        base_env={
            "PATH": "C:\\Tools",
            "SystemRoot": "C:\\Windows",
            "WINDIR": "C:\\Windows",
            "ComSpec": "C:\\Windows\\System32\\cmd.exe",
            "SECRET_TOKEN": "do-not-copy",
        },
    )

    assert env["PATH"] == "C:\\Tools"
    assert env["SystemRoot"] == "C:\\Windows"
    assert env["ComSpec"] == "C:\\Windows\\System32\\cmd.exe"
    assert "SECRET_TOKEN" not in env


def _request(
    *,
    argv: list[str] | None = None,
    allowed_commands: list[str] | None = None,
    max_output_bytes: int = 4096,
    grants: dict | None = None,
    command_request: dict | None = None,
    timeout_seconds: int = 5,
) -> TerminalBackendRequest:
    argv = argv or ["safe"]
    return TerminalBackendRequest(
        run_id="run_windows_terminal",
        proposal_id="prop_windows_terminal",
        decision_id="dec_windows_terminal",
        execution_id="exec_windows_terminal",
        policy_profile_id="default",
        policy_version="v0.2",
        registry_id="default",
        registry_version="v0.2",
        grants=grants
        if grants is not None
        else {
            "terminal": {
                "shell": False,
                "argv_policy": "allowlist",
                "allowed_commands": allowed_commands or ["safe"],
                "max_output_bytes": max_output_bytes,
            }
        },
        workspace_binding={
            "workspace_id": "workspace_windows_terminal",
            "mode": "shared_ro",
        },
        command_request=command_request or {"kind": "exec_argv", "argv": argv},
        budget={"seconds": timeout_seconds},
        artifact_policy={"capture": ["transcript"]},
        basis_event_ids=["evt_decided"],
    )


def _python_executable_with_exe_suffix(tmp_path: Path) -> Path:
    executable = Path(sys.executable)
    if executable.suffix.lower() == ".exe":
        return executable
    linked = tmp_path / "python.exe"
    linked.symlink_to(executable)
    return linked


def _record_and_terminate(cleanup_calls: list[int | None], process_id: int | None) -> dict:
    cleanup_calls.append(process_id)
    if process_id is not None:
        try:
            os.kill(process_id, signal.SIGTERM)
        except OSError:
            pass
    return {"attempted": True, "succeeded": True, "method": "test", "process_id": process_id}
