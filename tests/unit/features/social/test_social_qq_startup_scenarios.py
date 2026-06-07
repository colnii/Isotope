from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from isotope.features.social.runner import main
from tests.unit.features.social.test_social_runner import (
    _prepare_profiled_replay_pack,
    _write_json,
)


def _scenario_report(path: Path, *, passed: bool) -> Path:
    failed_count = 0 if passed else 1
    _write_json(
        path,
        {
            "kind": "qq_replay_scenarios_report",
            "passed": passed,
            "summary": {
                "scenario_count": 3,
                "passed_count": 3 - failed_count,
                "failed_count": failed_count,
            },
            "scenarios": [
                {
                    "scenario_id": "ship_it_candidate",
                    "passed": passed,
                    "report_json": (
                        "logs/replay-scenario-reports/"
                        "01-ship-it-candidate-report.json"
                    ),
                }
            ],
        },
    )
    return path


def test_social_runner_qq_startup_check_accepts_replay_scenarios_report(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, replay_report = _prepare_profiled_replay_pack(tmp_path, capsys)
    scenario_report = _scenario_report(
        beta_dir / "logs" / "replay-scenarios-report.json",
        passed=True,
    )

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(replay_report),
            "--replay-scenarios-report",
            str(scenario_report),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["ready"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "beta_pack",
        "profile_assets",
        "sticker_assets",
        "llm_reply_provider",
        "replay_report",
        "replay_scenarios_report",
    ]
    scenarios_check = payload["checks"][-1]
    assert scenarios_check["ok"] is True
    assert scenarios_check["scenario_count"] == 3
    assert scenarios_check["failed_count"] == 0


def test_social_runner_qq_startup_check_blocks_failed_replay_scenarios_report(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, replay_report = _prepare_profiled_replay_pack(tmp_path, capsys)
    scenario_report = _scenario_report(
        beta_dir / "logs" / "replay-scenarios-report.json",
        passed=False,
    )

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(replay_report),
            "--replay-scenarios-report",
            str(scenario_report),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    failed = [check for check in payload["checks"] if not check["ok"]]
    assert [check["name"] for check in failed] == ["replay_scenarios_report"]
    assert failed[0]["failed_count"] == 1
    assert "replay scenarios report passed must be true" in failed[0]["errors"]


def test_social_runner_qq_init_beta_scripts_gate_replay_scenarios(
    tmp_path: Path,
    capsys,
) -> None:
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

    startup_check = (output_dir / "startup-check.sh").read_text(encoding="utf-8")
    assert "--replay-report logs/replay-report.json" in startup_check
    assert "--replay-scenarios-report logs/replay-scenarios-report.json" in startup_check

    first_run = (output_dir / "first-run.sh").read_text(encoding="utf-8")
    assert "[ -f logs/replay-report.json ]" in first_run
    assert "[ -f logs/replay-scenarios-report.json ]" in first_run
    assert "qq init-replay-scenarios" in first_run
    assert "qq replay-scenarios" in first_run
    assert first_run.index("[ -f logs/replay-report.json ]") < first_run.index(
        "[ -f logs/replay-scenarios-report.json ]"
    )
    assert first_run.index("[ -f logs/replay-scenarios-report.json ]") < first_run.index(
        "./startup-check.sh"
    )


def test_social_runner_qq_first_run_stops_when_replay_scenarios_report_missing(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir, _replay_report = _prepare_profiled_replay_pack(tmp_path, capsys)

    result = subprocess.run(
        ["./first-run.sh"],
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

    assert result.returncode == 2
    assert "Missing logs/replay-scenarios-report.json" in result.stderr
    assert "qq init-replay-scenarios" in result.stderr
    assert "qq replay-scenarios" in result.stderr
    assert "qq live-run" not in result.stderr
    assert "qq live-run" not in result.stdout
