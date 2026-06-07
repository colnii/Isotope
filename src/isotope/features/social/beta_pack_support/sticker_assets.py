"""Sticker asset helpers for generated QQ beta packs."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .commands import (
    DEFAULT_PROFILE_NAME,
    init_replay_command,
    init_replay_scenarios_command,
    qq_replay_command,
    qq_replay_scenarios_command,
    QQBetaScriptConfig,
)


def write_sticker_asset_template(output_dir: Path) -> Path:
    asset_dir = output_dir / "sticker-assets"
    asset_dir.mkdir(exist_ok=True)
    manifest_path = asset_dir / "manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(
                _sticker_asset_manifest_payload(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return manifest_path


def import_stickers_command(config: QQBetaScriptConfig) -> str:
    return (
        'PROFILE_DIR="${ISOTOPE_QQ_PROFILE_DIR:-../qq-profile}"\n'
        f'PROFILE_NAME="${{ISOTOPE_QQ_PROFILE_NAME:-{DEFAULT_PROFILE_NAME}}}"\n'
        'STICKER_SOURCE_DIR="${ISOTOPE_QQ_STICKER_SOURCE_DIR:-sticker-assets}"\n'
        'STICKER_PACK_ID="${ISOTOPE_QQ_STICKER_PACK_ID:-qq-beta}"\n'
        'echo "Importing local QQ sticker assets. No OneBot connection will be opened." >&2\n'
        'if ! [ -f "$STICKER_SOURCE_DIR/manifest.json" ]; then\n'
        '  echo "Missing sticker manifest: $STICKER_SOURCE_DIR/manifest.json" >&2\n'
        "  exit 2\n"
        "fi\n"
        'if ! [ -f "$PROFILE_DIR/role-card.json" ]; then\n'
        "  isotope-social qq init-profile --output-dir \"$PROFILE_DIR\" "
        f"--group {shlex.quote(config.group_id)} --name \"$PROFILE_NAME\" --force --json\n"
        "fi\n"
        "isotope-social qq import-stickers --source-dir \"$STICKER_SOURCE_DIR\" "
        "--output \"$PROFILE_DIR/sticker-library.json\" "
        f"--group {shlex.quote(config.group_id)} --pack-id \"$STICKER_PACK_ID\" --json\n"
        "isotope-social qq apply-profile --pack-dir . --profile-dir \"$PROFILE_DIR\" --json\n"
        "isotope-social qq beta-check --pack-dir . --json\n"
        f"{init_replay_command(config)}\n"
        f"{qq_replay_command(config)}\n"
        f"{init_replay_scenarios_command(config)}\n"
        f"{qq_replay_scenarios_command()}\n"
        "./startup-check.sh\n"
        "./diagnostics.sh\n"
    )


def _sticker_asset_manifest_payload() -> dict[str, object]:
    return {
        "stickers": [
            {
                "sticker_id": "ship-it",
                "file": "ship.png",
                "tags": ["ship", "thumbs-up", "positive", "review"],
                "meaning": "结果不错、可以推进时使用",
                "source": "qq_beta_sticker_assets",
            }
        ]
    }
