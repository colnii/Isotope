from __future__ import annotations

from isotope.integrations.codex import cli
from isotope.integrations.codex import cli_supervisor


def test_codex_cli_facade_reexports_supervisor_launch_helpers() -> None:
    assert cli.CodexSupervisorCliConfig is cli_supervisor.CodexSupervisorCliConfig
    assert (
        cli.build_supervisor_launch_exec_argv
        is cli_supervisor.build_supervisor_launch_exec_argv
    )
    assert (
        cli.build_supervisor_resume_exec_argv
        is cli_supervisor.build_supervisor_resume_exec_argv
    )
    assert (
        cli.build_supervisor_tmux_launch_command
        is cli_supervisor.build_supervisor_tmux_launch_command
    )
