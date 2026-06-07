from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from isotope.features.social.runner import main
from tests.unit.features.social.test_social_runner import _read_json


def _init_beta_pack(tmp_path: Path, capsys) -> Path:
    output_dir = tmp_path / "qq-beta"
    assert main(
        [
            "qq",
            "init-beta",
            "--output-dir",
            str(output_dir),
            "--group",
            "99999",
            "--operator",
            "op",
            "--bot-user-id",
            "bot_qq",
            "--websocket-url",
            "ws://127.0.0.1:3001",
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    return output_dir


def _script_env() -> dict[str, str]:
    return {
        **os.environ,
        "PATH": "/home/lumber/Github/isotope/.venv/bin:"
        + os.environ.get("PATH", ""),
        "PYTHONPATH": str(Path.cwd() / "src")
        + os.pathsep
        + os.environ.get("PYTHONPATH", ""),
    }


def test_social_runner_qq_beta_pack_writes_sticker_operator_assets(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = _init_beta_pack(tmp_path, capsys)

    script = (output_dir / "import-stickers.sh").read_text(encoding="utf-8")
    manifest = _read_json(output_dir / "sticker-assets" / "manifest.json")

    assert "qq import-stickers" in script
    assert "qq apply-profile" in script
    assert "qq replay-scenarios" in script
    assert "./startup-check.sh" in script
    assert "./diagnostics.sh" in script
    assert "live-run" not in script
    assert manifest["stickers"][0]["sticker_id"] == "ship-it"
    assert manifest["stickers"][0]["file"] == "ship.png"


def test_social_runner_qq_import_stickers_script_runs_local_ready_chain(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = _init_beta_pack(tmp_path, capsys)
    (output_dir / "sticker-assets" / "ship.png").write_bytes(b"fake sticker image")

    result = subprocess.run(
        ["./import-stickers.sh"],
        cwd=output_dir,
        env=_script_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "live-run" not in result.stdout
    assert "live-run" not in result.stderr

    profile_dir = tmp_path / "qq-profile"
    sticker_library = _read_json(profile_dir / "sticker-library.json")
    assert sticker_library["entries"][0]["sticker_id"] == "ship-it"
    assert sticker_library["entries"][0]["media"]["local_path"] == os.path.relpath(
        output_dir / "sticker-assets" / "ship.png",
        start=profile_dir,
    )

    config = _read_json(output_dir / "config.json")
    assert config["sticker_library_path"] == "../qq-profile/sticker-library.json"
    assert (output_dir / "logs" / "replay-scenarios-report.json").is_file()
    assert (
        _read_json(output_dir / "logs" / "replay-scenarios-report.json")["passed"]
        is True
    )

    json_lines = [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.strip().startswith("{")
    ]
    assert json_lines[-1]["command"] == "beta-diagnostics"
    assert json_lines[-1]["status"] == "ready"


def test_social_runner_qq_import_stickers_script_reports_missing_asset(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = _init_beta_pack(tmp_path, capsys)

    result = subprocess.run(
        ["./import-stickers.sh"],
        cwd=output_dir,
        env=_script_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 2
    assert "sticker file does not exist" in result.stdout
    assert "ship.png" in result.stdout
