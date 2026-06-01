from __future__ import annotations

from isotope.features.supervisor.commands.parser import build_parser


def test_supervisor_cli_accepts_state_root_as_primary_state_directory_option():
    args = build_parser().parse_args(["worker-review", "--state-root", "/tmp/isotope-state"])

    assert args.codex_home == "/tmp/isotope-state"


def test_supervisor_cli_keeps_codex_home_as_hidden_compatibility_alias():
    parser = build_parser()

    args = parser.parse_args(["worker-review", "--codex-home", "/tmp/legacy-state"])

    assert args.codex_home == "/tmp/legacy-state"
    assert "--codex-home" not in parser.format_help()
