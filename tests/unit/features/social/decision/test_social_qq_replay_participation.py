from __future__ import annotations

from pathlib import Path

from tests.unit.features.social.test_social_runner import (
    _config,
    _event,
    _read_json,
    _write_json,
    main,
)


def test_social_runner_qq_replay_can_use_replay_participation_decision(
    tmp_path: Path,
    capsys,
) -> None:
    config = _write_json(tmp_path / "config.json", _config())
    ordinary_event = _event()
    ordinary_event["message"] = [
        {"type": "text", "data": {"text": "这个 PR 今天能合吗？"}},
    ]
    ordinary_event["raw_message"] = "这个 PR 今天能合吗？"
    replay = _write_json(
        tmp_path / "replay.json",
        {
            "events": [ordinary_event],
            "runtime": {
                "wake_keywords": [],
                "autonomy_score": 0.0,
                "replay_participation_decision": {
                    "action": "respond",
                    "reason": "topic_fit",
                    "confidence": 0.83,
                    "text": "能合，先确认 CI 全绿。",
                },
            },
            "expectations": {
                "require_processed_events": 1,
                "min_respond_actions": 1,
                "require_participation_actions": ["respond"],
                "require_participation_reasons": ["topic_fit"],
                "max_sent_group_messages": 0,
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
    assert report["summary"]["respond_action_count"] == 1
    assert report["summary"]["participation_actions"] == ["respond"]
    assert report["summary"]["participation_reasons"] == ["topic_fit"]
    proposed = report["turns"][0]["decision"]["proposed"][0]
    assert proposed["reply_action"]["parts"][0]["text"] == "能合，先确认 CI 全绿。"


def test_social_runner_qq_replay_can_record_replay_participation_error(
    tmp_path: Path,
    capsys,
) -> None:
    config = _write_json(tmp_path / "config.json", _config())
    replay = _write_json(
        tmp_path / "replay.json",
        {
            "events": [_event()],
            "runtime": {
                "replay_participation_error": "bad model output",
            },
            "expectations": {
                "require_processed_events": 1,
                "min_silent_actions": 1,
                "min_participation_provider_errors": 1,
                "max_sent_group_messages": 0,
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
    assert report["summary"]["silent_action_count"] == 1
    assert report["summary"]["participation_provider_error_count"] == 1
    proposed = report["turns"][0]["decision"]["proposed"][0]
    assert proposed["reason"] == "participation_provider_error"
