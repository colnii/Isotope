from __future__ import annotations

import json
from pathlib import Path

from isotope.features.social import qq_runtime_commands
from tests.unit.features.social.test_social_runner import (
    FakeLiveOneBotClient,
    _config,
    _read_json,
    _write_json,
    main,
)


def test_qq_dry_run_review_exposes_sticker_candidate_review_fields(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    FakeLiveOneBotClient.instances = []
    monkeypatch.setattr(
        qq_runtime_commands,
        "OneBotWebSocketClient",
        FakeLiveOneBotClient,
        raising=False,
    )
    config_payload = _config()
    config_payload["runtime"] = _sticker_runtime()
    config_payload["sticker_library"]["entries"][0]["media"]["local_path"] = (
        "stickers/ship.png"
    )
    config = _write_json(tmp_path / "config.json", config_payload)
    report_path = tmp_path / "dry-run-review.json"

    _run_live_dry_run(tmp_path=tmp_path, config=config, capsys=capsys)
    assert _run_review(tmp_path=tmp_path, report_path=report_path, capsys=capsys) == 0

    report = _read_json(report_path)
    candidate = report["turns"][0]["proposed"][0]
    assert candidate["reply_preview"] == "[sticker:ship-it]"
    assert candidate["sticker"] == {
        "sticker_id": "ship-it",
        "pack_id": "engineering",
        "meaning": "通过时使用",
        "reasons": ["scene_tag:review", "favorite_pack:engineering"],
    }
    assert candidate["sticker_selection"] == {
        "selected": True,
        "sticker_id": "ship-it",
        "pack_id": "engineering",
        "media_ref": "qq-image://ship-it",
        "media_source": "local_pack",
        "local_path": "stickers/ship.png",
        "meaning": "通过时使用",
        "tags": ["ship", "review"],
        "reasons": ["scene_tag:review", "favorite_pack:engineering"],
        "blocked_reasons": [],
        "recent_sticker_ids": [],
        "emotion": "",
        "scene_tags": [],
        "candidate_count": 1,
        "allow_sticker_only": True,
    }


def test_qq_dry_run_review_exposes_sticker_block_reasons_on_text_fallback(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    FakeLiveOneBotClient.instances = []
    monkeypatch.setattr(
        qq_runtime_commands,
        "OneBotWebSocketClient",
        FakeLiveOneBotClient,
        raising=False,
    )
    config_payload = _config()
    config_payload["runtime"] = _sticker_runtime()
    config_payload["role_card"]["stickers"]["use_frequency"] = 0.0
    config = _write_json(tmp_path / "config.json", config_payload)
    report_path = tmp_path / "dry-run-review.json"

    _run_live_dry_run(tmp_path=tmp_path, config=config, capsys=capsys)
    assert _run_review(tmp_path=tmp_path, report_path=report_path, capsys=capsys) == 0

    report = _read_json(report_path)
    candidate = report["turns"][0]["proposed"][0]
    assert candidate["candidate_id"] == "reply_text"
    assert "sticker" not in candidate
    assert candidate["sticker_selection"] == {
        "selected": False,
        "sticker_id": "",
        "pack_id": "",
        "media_ref": "",
        "media_source": "",
        "local_path": "",
        "meaning": "",
        "tags": [],
        "reasons": [],
        "blocked_reasons": ["use_frequency_zero"],
        "recent_sticker_ids": [],
        "emotion": "positive",
        "scene_tags": ["review"],
        "candidate_count": 0,
        "allow_sticker_only": False,
    }
    assert candidate["reply_preview"] == "我看到了，先按上下文处理。"


def _sticker_runtime() -> dict:
    return {
        "sticker_emotion": "positive",
        "sticker_scene_tags": ["review"],
        "allow_sticker_only": True,
    }


def _run_live_dry_run(*, tmp_path: Path, config: Path, capsys) -> None:
    assert main(
        [
            "qq",
            "live-run",
            "--config-json",
            str(config),
            "--state-root",
            str(tmp_path / "state"),
            "--websocket-url",
            "ws://127.0.0.1:3001",
            "--max-events",
            "1",
            "--json",
        ]
    ) == 0
    json.loads(capsys.readouterr().out)


def _run_review(*, tmp_path: Path, report_path: Path, capsys) -> int:
    code = main(
        [
            "qq",
            "review-dry-run",
            "--state-root",
            str(tmp_path / "state"),
            "--group",
            "99999",
            "--output",
            str(report_path),
            "--json",
        ]
    )
    json.loads(capsys.readouterr().out)
    return code
