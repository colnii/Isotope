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


def test_social_runner_qq_first_run_rehearsal_script_is_local_only(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = _init_beta_pack(tmp_path, capsys)

    rehearsal = (output_dir / "first-run-rehearsal.sh").read_text(encoding="utf-8")

    assert "qq init-profile" in rehearsal
    assert "qq apply-profile" in rehearsal
    assert "qq init-replay" in rehearsal
    assert "qq replay " in rehearsal
    assert "qq init-replay-scenarios" in rehearsal
    assert "qq replay-scenarios" in rehearsal
    assert "./startup-check.sh" in rehearsal
    assert "./diagnostics.sh" in rehearsal
    assert "live-run" not in rehearsal
    assert "dry-run.sh" not in rehearsal
    assert "send-run.sh" not in rehearsal


def test_social_runner_qq_first_run_rehearsal_runs_local_ready_chain(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = _init_beta_pack(tmp_path, capsys)

    result = subprocess.run(
        ["./first-run-rehearsal.sh"],
        cwd=output_dir,
        env={
            **os.environ,
            "PATH": "/home/lumber/Github/isotope/.venv/bin:"
            + os.environ.get("PATH", ""),
            "PYTHONPATH": str(Path.cwd() / "src")
            + os.pathsep
            + os.environ.get("PYTHONPATH", ""),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "live-run" not in result.stdout
    assert "live-run" not in result.stderr
    assert (tmp_path / "qq-profile" / "role-card.json").is_file()
    assert (tmp_path / "qq-profile" / "sticker-library.json").is_file()
    assert (output_dir / "replay.json").is_file()
    assert (output_dir / "logs" / "replay-report.json").is_file()
    assert (output_dir / "replay-scenarios" / "index.json").is_file()
    assert (output_dir / "logs" / "replay-scenarios-report.json").is_file()
    assert _read_json(output_dir / "logs" / "replay-report.json")["passed"] is True
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
    assert json_lines[-1]["next_steps"][0]["command"] == "./health.sh"
