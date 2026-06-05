from __future__ import annotations

import json
from pathlib import Path
import tomllib

from tests.unit.features.social.test_social_runner import (
    _config,
    _event,
    _read_json,
    _write_json,
    main,
)


def test_social_runner_qq_init_replay_writes_editable_event_file(
    tmp_path: Path,
    capsys,
) -> None:
    replay_path = tmp_path / "replay.json"

    code = main(
        [
            "qq",
            "init-replay",
            "--output",
            str(replay_path),
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
    assert payload["command"] == "init-replay"
    assert payload["output"] == str(replay_path)
    replay = _read_json(replay_path)
    assert replay["runtime"] == {
        "wake_keywords": ["看看", "帮我", "bot"],
        "autonomy_score": 1.0,
        "sticker_emotion": "positive",
        "sticker_scene_tags": ["review"],
        "allow_sticker_only": True,
    }
    assert replay["expectations"] == {
        "require_processed_events": 2,
        "min_proposed_actions": 1,
        "min_sticker_candidates": 1,
        "require_sticker_candidate_ids": ["ship-it"],
        "forbid_sticker_candidate_ids": [],
        "require_sticker_block_reasons": [],
        "forbid_sticker_block_reasons": [],
        "max_selected_sticker_actions": 0,
        "max_send_feedback": 0,
        "max_sent_group_messages": 0,
        "require_all_dry_run": True,
    }
    assert len(replay["events"]) == 2
    assert replay["events"][0]["group_id"] == 99999
    assert replay["events"][0]["message"][0]["type"] == "at"
    assert replay["events"][1]["raw_message"] == "这个结果可以发了吗？"


def test_social_runner_qq_replay_writes_decision_report(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir = tmp_path / "qq-beta"
    profile_dir = tmp_path / "qq-profile"
    replay_path = beta_dir / "replay.json"
    report_path = beta_dir / "logs" / "replay-report.json"

    assert main(
        [
            "qq",
            "init-beta",
            "--output-dir",
            str(beta_dir),
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
    assert main(
        [
            "qq",
            "init-profile",
            "--output-dir",
            str(profile_dir),
            "--group",
            "99999",
            "--name",
            "群聊工程猫",
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "qq",
            "apply-profile",
            "--pack-dir",
            str(beta_dir),
            "--profile-dir",
            str(profile_dir),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "qq",
            "init-replay",
            "--output",
            str(replay_path),
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
            "replay",
            "--config-json",
            str(beta_dir / "config.json"),
            "--state-root",
            str(beta_dir / "state"),
            "--replay-json",
            str(replay_path),
            "--output",
            str(report_path),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "replay"
    assert payload["dry_run"] is True
    assert payload["processed_events"] == 2
    assert payload["output"] == str(report_path)
    assert payload["passed"] is True

    report = _read_json(report_path)
    assert report["passed"] is True
    assert [item["name"] for item in report["expectations"]] == [
        "require_processed_events",
        "min_proposed_actions",
        "min_sticker_candidates",
        "require_sticker_candidate_ids",
        "forbid_sticker_candidate_ids",
        "require_sticker_block_reasons",
        "forbid_sticker_block_reasons",
        "max_selected_sticker_actions",
        "max_send_feedback",
        "max_sent_group_messages",
        "require_all_dry_run",
    ]
    assert all(item["ok"] for item in report["expectations"])
    assert report["summary"]["event_count"] == 2
    assert report["summary"]["processed_events"] == 2
    assert report["summary"]["proposed_action_count"] >= 1
    assert report["summary"]["sticker_candidate_count"] >= 1
    assert report["summary"]["sticker_candidate_ids"] == ["ship-it"]
    assert report["summary"]["sticker_candidate_block_reason_counts"] == {}
    assert report["summary"]["selected_sticker_ids"] == []
    assert report["summary"]["selected_sticker_action_count"] == 0
    assert report["summary"]["send_feedback_count"] == 0
    assert report["turns"][0]["decision"]["dry_run"] is True
    assert report["sent_group_messages"] == []
    state = _read_json(beta_dir / "state" / "social-qq-state.json")
    assert [entry["kind"] for entry in state["audit_entries"]] == ["decision", "decision"]


def test_social_runner_qq_replay_reports_failed_expectations(
    tmp_path: Path,
    capsys,
) -> None:
    config = _write_json(tmp_path / "config.json", _config())
    replay = _write_json(
        tmp_path / "replay.json",
        {
            "events": [_event()],
            "runtime": {
                "wake_keywords": ["看看"],
                "autonomy_score": 1.0,
                "sticker_emotion": "positive",
                "sticker_scene_tags": ["review"],
                "allow_sticker_only": True,
            },
            "expectations": {
                "require_processed_events": 2,
                "min_sticker_candidates": 99,
                "require_sticker_candidate_ids": ["missing-sticker"],
                "forbid_sticker_candidate_ids": ["ship-it"],
                "max_send_feedback": 0,
                "require_all_dry_run": True,
            },
        },
    )
    report_path = tmp_path / "report.json"

    assert main(
        [
            "qq",
            "replay",
            "--config-json",
            str(config),
            "--state-root",
            str(tmp_path / "state"),
            "--replay-json",
            str(replay),
            "--output",
            str(report_path),
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False
    report = _read_json(report_path)
    failed = [item for item in report["expectations"] if not item["ok"]]
    assert [item["name"] for item in failed] == [
        "require_processed_events",
        "min_sticker_candidates",
        "require_sticker_candidate_ids",
        "forbid_sticker_candidate_ids",
    ]
    assert failed[0]["expected"] == 2
    assert failed[0]["actual"] == 1
    assert failed[2]["expected"] == ["missing-sticker"]
    assert failed[2]["actual"] == ["ship-it"]
    assert failed[3]["expected"] == ["ship-it"]
    assert failed[3]["actual"] == ["ship-it"]


def test_social_runner_qq_replay_reports_sticker_block_reasons(
    tmp_path: Path,
    capsys,
) -> None:
    config_payload = _config()
    config_payload["role_card"]["stickers"]["use_frequency"] = 0.0
    config = _write_json(tmp_path / "config.json", config_payload)
    replay = _write_json(
        tmp_path / "replay.json",
        {
            "events": [_event()],
            "runtime": {
                "wake_keywords": ["看看"],
                "autonomy_score": 1.0,
                "sticker_emotion": "positive",
                "sticker_scene_tags": ["review"],
                "allow_sticker_only": True,
            },
            "expectations": {
                "require_processed_events": 1,
                "min_proposed_actions": 1,
                "min_sticker_candidates": 0,
                "require_sticker_block_reasons": ["use_frequency_zero"],
                "forbid_sticker_block_reasons": ["recent_sticker_feedback"],
                "max_send_feedback": 0,
                "require_all_dry_run": True,
            },
        },
    )
    report_path = tmp_path / "report.json"

    assert main(
        [
            "qq",
            "replay",
            "--config-json",
            str(config),
            "--state-root",
            str(tmp_path / "state"),
            "--replay-json",
            str(replay),
            "--output",
            str(report_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    report = _read_json(report_path)
    assert report["passed"] is True
    assert [
        item
        for item in report["expectations"]
        if item["name"]
        in {"require_sticker_block_reasons", "forbid_sticker_block_reasons"}
    ] == [
        {
            "name": "require_sticker_block_reasons",
            "ok": True,
            "expected": ["use_frequency_zero"],
            "actual": ["use_frequency_zero"],
        },
        {
            "name": "forbid_sticker_block_reasons",
            "ok": True,
            "expected": ["recent_sticker_feedback"],
            "actual": ["use_frequency_zero"],
        },
    ]
    assert report["summary"]["sticker_candidate_count"] == 0
    assert report["summary"]["sticker_candidate_block_reason_counts"] == {
        "use_frequency_zero": 1
    }
    proposed = report["turns"][0]["decision"]["proposed"][0]
    assert proposed["candidate_id"] == "reply_text"
    assert proposed["metadata"]["sticker_selection"]["blocked_reasons"] == [
        "use_frequency_zero"
    ]


def test_social_runner_qq_replay_reports_failed_sticker_block_reason_expectations(
    tmp_path: Path,
    capsys,
) -> None:
    config_payload = _config()
    config_payload["role_card"]["stickers"]["use_frequency"] = 0.0
    config = _write_json(tmp_path / "config.json", config_payload)
    replay = _write_json(
        tmp_path / "replay.json",
        {
            "events": [_event()],
            "runtime": {
                "wake_keywords": ["看看"],
                "autonomy_score": 1.0,
                "sticker_emotion": "positive",
                "sticker_scene_tags": ["review"],
                "allow_sticker_only": True,
            },
            "expectations": {
                "require_processed_events": 1,
                "min_proposed_actions": 1,
                "require_sticker_block_reasons": ["no_matching_sticker"],
                "forbid_sticker_block_reasons": ["use_frequency_zero"],
                "require_all_dry_run": True,
            },
        },
    )
    report_path = tmp_path / "report.json"

    assert main(
        [
            "qq",
            "replay",
            "--config-json",
            str(config),
            "--state-root",
            str(tmp_path / "state"),
            "--replay-json",
            str(replay),
            "--output",
            str(report_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    report = _read_json(report_path)
    failed = [
        item
        for item in report["expectations"]
        if item["name"]
        in {"require_sticker_block_reasons", "forbid_sticker_block_reasons"}
    ]
    assert report["passed"] is False
    assert failed == [
        {
            "name": "require_sticker_block_reasons",
            "ok": False,
            "expected": ["no_matching_sticker"],
            "actual": ["use_frequency_zero"],
        },
        {
            "name": "forbid_sticker_block_reasons",
            "ok": False,
            "expected": ["use_frequency_zero"],
            "actual": ["use_frequency_zero"],
        },
    ]
