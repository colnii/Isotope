"""Replay-template command handlers for QQ social commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .replay import QQReplayTemplateConfig, create_qq_replay_template


def handle_init_replay(args: argparse.Namespace) -> dict[str, Any]:
    result = create_qq_replay_template(
        QQReplayTemplateConfig(
            output=Path(args.output),
            group_id=args.group,
            bot_user_id=args.bot_user_id,
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "init-replay"})
    return payload
