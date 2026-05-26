"""Pytest gate for Supervisor-managed workers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from ..registry import ManagedCodexRecord

RunCommand = Callable[..., subprocess.CompletedProcess[str]]

TEST_GATE_COMMAND = [".venv/bin/python", "-m", "pytest", "tests", "-q"]
OUTPUT_TAIL_LINES = 40


def collect_worker_test_gate(
    record: ManagedCodexRecord,
    *,
    protocol: dict[str, str | None],
    cwd: Path,
    cwd_exists: bool,
    run: RunCommand,
) -> dict[str, Any]:
    """Run the standard pytest gate for done process workers."""
    status = (protocol.get("status") or "").strip().lower()
    if not cwd_exists:
        return _skipped("cwd/worktree 缺失，跳过 pytest。")
    if record.backend != "process":
        return _skipped(f"worker backend={record.backend}，跳过 process worker pytest gate。")
    if status != "done":
        return _skipped("worker 未汇报 done，跳过 pytest gate。")

    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    command = _test_gate_command(cwd)
    try:
        completed = run(
            command,
            cwd=str(cwd),
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError, TypeError) as exc:
        return {
            "test_status": "failed",
            "test_passed": False,
            "test_exit_code": None,
            "test_output_tail": f"pytest gate failed to start: {exc}",
        }

    output_tail = _output_tail(completed.stdout, completed.stderr)
    passed = completed.returncode == 0
    return {
        "test_status": "passed" if passed else "failed",
        "test_passed": passed,
        "test_exit_code": completed.returncode,
        "test_output_tail": output_tail,
    }


def _test_gate_command(cwd: Path) -> list[str]:
    local_python = cwd / ".venv" / "bin" / "python"
    if local_python.exists():
        return TEST_GATE_COMMAND
    return [sys.executable, *TEST_GATE_COMMAND[1:]]


def _skipped(reason: str) -> dict[str, Any]:
    return {
        "test_status": "skipped",
        "test_passed": None,
        "test_exit_code": None,
        "test_output_tail": reason,
    }


def _output_tail(stdout: str | None, stderr: str | None) -> str:
    text = "\n".join(part for part in (stdout or "", stderr or "") if part)
    lines = text.splitlines()
    tail = "\n".join(lines[-OUTPUT_TAIL_LINES:])
    return tail.rstrip()


__all__ = [
    "OUTPUT_TAIL_LINES",
    "TEST_GATE_COMMAND",
    "RunCommand",
    "collect_worker_test_gate",
]
