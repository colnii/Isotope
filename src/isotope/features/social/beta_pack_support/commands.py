"""Command strings shared by generated QQ beta pack scripts."""

from __future__ import annotations

import shlex
from typing import Protocol


DEFAULT_PROFILE_NAME = "群聊工程猫"


class QQBetaScriptConfig(Protocol):
    group_id: str
    bot_user_id: str


def first_run_rehearsal_command(config: QQBetaScriptConfig) -> str:
    return (
        'PROFILE_DIR="${ISOTOPE_QQ_REHEARSAL_PROFILE_DIR:-../qq-profile}"\n'
        f'PROFILE_NAME="${{ISOTOPE_QQ_REHEARSAL_PROFILE_NAME:-{DEFAULT_PROFILE_NAME}}}"\n'
        'echo "Running local QQ first-run rehearsal. No OneBot connection will be opened." >&2\n'
        "isotope-social qq init-profile --output-dir \"$PROFILE_DIR\" "
        f"--group {shlex.quote(config.group_id)} --name \"$PROFILE_NAME\" --force --json\n"
        "isotope-social qq apply-profile --pack-dir . --profile-dir \"$PROFILE_DIR\" --json\n"
        "isotope-social qq beta-check --pack-dir . --json\n"
        f"{init_replay_command(config)}\n"
        f"{qq_replay_command(config)}\n"
        f"{init_replay_scenarios_command(config)}\n"
        f"{qq_replay_scenarios_command()}\n"
        "./startup-check.sh\n"
        "./diagnostics.sh\n"
    )


def init_replay_command(config: QQBetaScriptConfig) -> str:
    parts = [
        "isotope-social",
        "qq",
        "init-replay",
        "--output",
        "replay.json",
        "--group",
        config.group_id,
        "--bot-user-id",
        config.bot_user_id,
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def init_replay_scenarios_command(config: QQBetaScriptConfig) -> str:
    parts = [
        "isotope-social",
        "qq",
        "init-replay-scenarios",
        "--output-dir",
        "replay-scenarios",
        "--group",
        config.group_id,
        "--bot-user-id",
        config.bot_user_id,
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def qq_replay_command(config: QQBetaScriptConfig) -> str:
    parts = [
        "isotope-social",
        "qq",
        "replay",
        "--config-json",
        "config.json",
        "--state-root",
        "state",
        "--replay-json",
        "replay.json",
        "--output",
        "logs/replay-report.json",
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def qq_replay_scenarios_command() -> str:
    parts = [
        "isotope-social",
        "qq",
        "replay-scenarios",
        "--config-json",
        "config.json",
        "--state-root",
        "state",
        "--scenario-dir",
        "replay-scenarios",
        "--output",
        "logs/replay-scenarios-report.json",
        "--reports-dir",
        "logs/replay-scenario-reports",
        "--json",
    ]
    return " ".join(shlex.quote(part) for part in parts)
