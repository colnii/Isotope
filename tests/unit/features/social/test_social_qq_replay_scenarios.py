from __future__ import annotations

import json
from pathlib import Path

from isotope.features.social.runner import main
from tests.unit.features.social.test_social_runner import _config, _write_json


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_social_runner_qq_init_replay_scenarios_writes_tuning_pack(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "replay-scenarios"

    code = main(
        [
            "qq",
            "init-replay-scenarios",
            "--output-dir",
            str(output_dir),
            "--group",
            "99999",
            "--bot-user-id",
            "bot_qq",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "init-replay-scenarios"
    assert payload["output_dir"] == str(output_dir)
    assert payload["scenario_count"] == 3
    assert payload["scenario_files"] == [
        str(output_dir / "01-ship-it-candidate.json"),
        str(output_dir / "02-no-matching-sticker.json"),
        str(output_dir / "03-forbid-frequency-zero.json"),
    ]

    index = _read_json(output_dir / "index.json")
    assert index["kind"] == "qq_replay_scenarios"
    assert [item["scenario_id"] for item in index["scenarios"]] == [
        "ship_it_candidate",
        "no_matching_sticker",
        "forbid_frequency_zero",
    ]
    assert index["scenarios"][0]["replay_command"].endswith(
        " --replay-json 01-ship-it-candidate.json "
        "--output logs/01-ship-it-candidate-report.json --json"
    )

    ship_it = _read_json(output_dir / "01-ship-it-candidate.json")
    assert ship_it["expectations"]["require_sticker_candidate_ids"] == ["ship-it"]
    assert ship_it["expectations"]["forbid_sticker_block_reasons"] == [
        "use_frequency_zero",
        "no_matching_sticker",
        "recent_sticker_feedback",
    ]

    no_match = _read_json(output_dir / "02-no-matching-sticker.json")
    assert no_match["runtime"]["sticker_emotion"] == "unmatched"
    assert no_match["runtime"]["sticker_scene_tags"] == ["unmatched-scene"]
    assert no_match["expectations"]["min_sticker_candidates"] == 0
    assert no_match["expectations"]["require_sticker_block_reasons"] == [
        "no_matching_sticker"
    ]
    assert no_match["expectations"]["forbid_sticker_block_reasons"] == [
        "use_frequency_zero"
    ]

    guard = _read_json(output_dir / "03-forbid-frequency-zero.json")
    assert guard["expectations"]["min_sticker_candidates"] == 1
    assert guard["expectations"]["forbid_sticker_block_reasons"] == [
        "use_frequency_zero"
    ]


def test_social_runner_qq_replay_scenarios_writes_aggregate_report(
    tmp_path: Path,
    capsys,
) -> None:
    scenario_dir = tmp_path / "replay-scenarios"
    report_path = tmp_path / "logs" / "replay-scenarios-report.json"
    reports_dir = tmp_path / "logs" / "replay-scenario-reports"
    config_path = _write_json(tmp_path / "config.json", _config())

    assert main(
        [
            "qq",
            "init-replay-scenarios",
            "--output-dir",
            str(scenario_dir),
            "--group",
            "99999",
            "--bot-user-id",
            "bot_qq",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    code = main(
        [
            "qq",
            "replay-scenarios",
            "--config-json",
            str(config_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scenario-dir",
            str(scenario_dir),
            "--output",
            str(report_path),
            "--reports-dir",
            str(reports_dir),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "replay-scenarios"
    assert payload["passed"] is True
    assert payload["scenario_count"] == 3
    assert payload["passed_count"] == 3
    assert payload["failed_count"] == 0
    assert payload["output"] == str(report_path)
    assert payload["reports_dir"] == str(reports_dir)
    assert [scenario["scenario_id"] for scenario in payload["scenarios"]] == [
        "ship_it_candidate",
        "no_matching_sticker",
        "forbid_frequency_zero",
    ]

    report = _read_json(report_path)
    assert report["kind"] == "qq_replay_scenarios_report"
    assert report["passed"] is True
    assert report["summary"] == {
        "scenario_count": 3,
        "passed_count": 3,
        "failed_count": 0,
    }
    assert all(Path(item["report_json"]).exists() for item in report["scenarios"])
    assert report["scenarios"][1]["summary"][
        "sticker_candidate_block_reason_counts"
    ] == {"no_matching_sticker": 1}


def test_social_runner_qq_replay_scenarios_fails_when_any_scenario_fails(
    tmp_path: Path,
    capsys,
) -> None:
    scenario_dir = tmp_path / "replay-scenarios"
    report_path = tmp_path / "logs" / "replay-scenarios-report.json"
    reports_dir = tmp_path / "logs" / "replay-scenario-reports"
    config_payload = _config()
    config_payload["role_card"]["stickers"]["use_frequency"] = 0.0
    config_path = _write_json(tmp_path / "config.json", config_payload)

    assert main(
        [
            "qq",
            "init-replay-scenarios",
            "--output-dir",
            str(scenario_dir),
            "--group",
            "99999",
            "--bot-user-id",
            "bot_qq",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    code = main(
        [
            "qq",
            "replay-scenarios",
            "--config-json",
            str(config_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scenario-dir",
            str(scenario_dir),
            "--output",
            str(report_path),
            "--reports-dir",
            str(reports_dir),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["command"] == "replay-scenarios"
    assert payload["passed"] is False
    assert payload["scenario_count"] == 3
    assert payload["passed_count"] == 0
    assert payload["failed_count"] == 3
    assert [scenario["passed"] for scenario in payload["scenarios"]] == [
        False,
        False,
        False,
    ]

    report = _read_json(report_path)
    assert report["passed"] is False
    assert report["summary"]["failed_count"] == 3
    failed_names = [
        expectation["name"]
        for scenario in report["scenarios"]
        for expectation in scenario["expectations"]
        if not expectation["ok"]
    ]
    assert "forbid_sticker_block_reasons" in failed_names
