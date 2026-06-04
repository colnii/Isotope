"""Profile command handlers for QQ social commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .profile_pack import (
    QQProfileApplyConfig,
    QQProfilePackConfig,
    apply_qq_profile_pack,
    create_qq_profile_pack,
)


def handle_init_profile(args: argparse.Namespace) -> dict[str, Any]:
    result = create_qq_profile_pack(
        QQProfilePackConfig(
            output_dir=Path(args.output_dir),
            group_id=args.group,
            role_name=args.name,
            force=bool(args.force),
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "init-profile"})
    return payload


def handle_apply_profile(args: argparse.Namespace) -> dict[str, Any]:
    result = apply_qq_profile_pack(
        QQProfileApplyConfig(
            pack_dir=Path(args.pack_dir),
            profile_dir=Path(args.profile_dir),
        )
    )
    payload = result.to_public_dict()
    payload.update({"status": "ok", "command": "apply-profile"})
    return payload
