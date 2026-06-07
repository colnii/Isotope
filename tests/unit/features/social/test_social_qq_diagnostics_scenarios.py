from __future__ import annotations

import json
from pathlib import Path

from isotope.features.social.runner import main
from tests.unit.features.social.test_social_qq_startup_scenarios import _scenario_report
from tests.unit.features.social.test_social_runner import _prepare_profiled_replay_pack


def test_social_runner_qq_beta_diagnostics_guides_missing_replay_scenarios_report(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, _replay_report = _prepare_profiled_replay_pack(tmp_path, capsys)

    code = main(["qq", "beta-diagnostics", "--pack-dir", str(beta_dir), "--json"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "needs_action"
    assert payload["summary"]["replay_report"]["exists"] is True
    assert payload["summary"]["replay_scenarios_report"] == {
        "exists": False,
        "path": str(beta_dir / "logs" / "replay-scenarios-report.json"),
        "passed": None,
    }
    assert [step["name"] for step in payload["next_steps"]] == [
        "create_replay_scenarios",
        "run_replay_scenarios",
        "rerun_diagnostics",
    ]
    assert "qq init-replay-scenarios" in payload["next_steps"][0]["command"]
    assert "qq replay-scenarios" in payload["next_steps"][1]["command"]


def test_social_runner_qq_beta_diagnostics_blocks_failed_replay_scenarios_report(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, _replay_report = _prepare_profiled_replay_pack(tmp_path, capsys)
    _scenario_report(beta_dir / "logs" / "replay-scenarios-report.json", passed=False)

    code = main(["qq", "beta-diagnostics", "--pack-dir", str(beta_dir), "--json"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "needs_action"
    assert payload["summary"]["replay_scenarios_report"]["exists"] is True
    assert payload["summary"]["replay_scenarios_report"]["passed"] is False
    failed = [check for check in payload["checks"] if not check["ok"]]
    assert [check["name"] for check in failed] == ["replay_scenarios_report"]
    assert payload["next_steps"][0]["name"] == "fix_startup_check"
    assert "--replay-scenarios-report logs/replay-scenarios-report.json" in (
        payload["next_steps"][0]["command"]
    )
    assert "replay_scenarios_report" in payload["next_steps"][0]["reason"]


def test_social_runner_qq_beta_diagnostics_ready_after_replay_scenarios_report(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, _replay_report = _prepare_profiled_replay_pack(tmp_path, capsys)
    _scenario_report(beta_dir / "logs" / "replay-scenarios-report.json", passed=True)

    code = main(["qq", "beta-diagnostics", "--pack-dir", str(beta_dir), "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["summary"]["replay_scenarios_report"]["exists"] is True
    assert payload["summary"]["replay_scenarios_report"]["passed"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "beta_pack",
        "profile_assets",
        "sticker_assets",
        "llm_reply_provider",
        "replay_report",
        "replay_scenarios_report",
    ]
    assert payload["next_steps"][0]["command"] == "./health.sh"
