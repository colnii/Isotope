from __future__ import annotations

import json

import pytest

from agents.tools.terminal import (
    ControlledTerminalRunner,
    TerminalExecutionError,
    cap_terminal_output,
    default_terminal_capabilities,
    validate_argv,
)


def _grants(*, allowed_commands: list[str] | None = None) -> dict:
    terminal = default_terminal_capabilities()
    terminal["allowed_commands"] = allowed_commands or ["printf", "false"]
    return {"terminal": terminal}


def test_validate_argv_accepts_only_structured_command_names():
    assert validate_argv(["printf", "hello"]) == ["printf", "hello"]

    with pytest.raises(ValueError, match="non-empty list"):
        validate_argv("printf hello")
    with pytest.raises(ValueError, match="command name"):
        validate_argv(["/bin/printf", "hello"])


def test_controlled_terminal_runner_runs_allowlisted_command(tmp_path):
    result = ControlledTerminalRunner(tmp_path).run(
        ["printf", "isotope-terminal"],
        grants=_grants(),
        timeout_seconds=5,
    )

    assert result.exit_code == 0
    assert result.stdout == "isotope-terminal"
    assert result.stderr == ""
    assert result.truncated is False
    assert json.loads(result.to_artifact_content())["shell"] is False


def test_controlled_terminal_runner_rejects_unlisted_command(tmp_path):
    with pytest.raises(TerminalExecutionError) as exc_info:
        ControlledTerminalRunner(tmp_path).run(
            ["bash", "-lc", "echo nope"],
            grants=_grants(),
            timeout_seconds=5,
        )

    assert exc_info.value.error_reason_code == "terminal_command_not_allowed"


def test_cap_terminal_output_shares_byte_budget_across_streams():
    stdout, stderr, truncated = cap_terminal_output(
        "a" * 6,
        "b" * 6,
        max_output_bytes=8,
    )

    assert stdout == "a" * 6
    assert stderr == "bb"
    assert truncated is True
