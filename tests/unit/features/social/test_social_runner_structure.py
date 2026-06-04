from __future__ import annotations

from pathlib import Path


SOCIAL_DIR = Path("src/isotope/features/social")


def test_social_runner_keeps_qq_cli_registration_split() -> None:
    runner_source = (SOCIAL_DIR / "runner.py").read_text(encoding="utf-8")
    qq_runner_source = (SOCIAL_DIR / "qq_runner.py").read_text(encoding="utf-8")

    assert len(runner_source.splitlines()) < 700
    assert "register_qq_commands" in qq_runner_source
    assert "handle_qq_command" in qq_runner_source
    assert "qq_subparsers.add_parser" not in runner_source
    assert "def _handle_qq(" not in runner_source
