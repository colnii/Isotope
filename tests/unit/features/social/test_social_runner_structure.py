from __future__ import annotations

from pathlib import Path


SOCIAL_DIR = Path("src/isotope/features/social")


def test_social_runner_keeps_qq_cli_registration_split() -> None:
    runner_source = (SOCIAL_DIR / "runner.py").read_text(encoding="utf-8")
    qq_runner_source = (SOCIAL_DIR / "qq_runner.py").read_text(encoding="utf-8")
    qq_handlers_source = (SOCIAL_DIR / "qq_handlers.py").read_text(encoding="utf-8")
    qq_runtime_source = (SOCIAL_DIR / "qq_runtime_commands.py").read_text(encoding="utf-8")
    qq_state_source = (SOCIAL_DIR / "qq_state_config.py").read_text(encoding="utf-8")

    assert len(runner_source.splitlines()) < 120
    assert len(qq_handlers_source.splitlines()) < 350
    assert "register_qq_commands" in qq_runner_source
    assert "handle_qq_command" in qq_runner_source
    assert "def qq_handlers(" in qq_handlers_source
    assert "OneBotWebSocketClient" in qq_runtime_source
    assert "def handle_live_run(" in qq_runtime_source
    assert "class StoredQQState" in qq_state_source
    assert "def load_config(" in qq_state_source
    assert "qq_subparsers.add_parser" not in runner_source
    assert "def _handle_qq(" not in runner_source
    assert "def _handle_run(" not in runner_source
    assert "OneBotWebSocketClient" not in runner_source
    assert "OneBotWebSocketClient" not in qq_handlers_source
