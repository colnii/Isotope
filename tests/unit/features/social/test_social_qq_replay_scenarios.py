from __future__ import annotations

import json
from pathlib import Path

from isotope.features.social.runner import main


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
