from __future__ import annotations

import json
from pathlib import Path

from isotope.features.social.runner import main
from tests.unit.features.social.test_social_runner import _read_json, _write_json


def test_social_runner_qq_beta_day_report_rolls_up_sticker_review(
    tmp_path: Path,
    capsys,
) -> None:
    dry_run_review = _write_json(
        tmp_path / "dry-run-review.json",
        _dry_run_review_payload(),
    )
    export_log = _write_json(
        tmp_path / "qq-99999.json",
        {"entries": [{"kind": "decision", "group_id": "99999", "payload": {}}]},
    )
    output = tmp_path / "beta-day-report.json"

    assert main(
        [
            "qq",
            "beta-day-report",
            "--date",
            "2026-06-07",
            "--group",
            "99999",
            "--dry-run-review",
            str(dry_run_review),
            "--export-log",
            str(export_log),
            "--output",
            str(output),
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["sticker_review"]["candidate_count"] == 2
    report = _read_json(output)
    assert report["sticker_review"] == {
        "candidate_count": 2,
        "selected_candidate_count": 1,
        "blocked_candidate_count": 1,
        "sticker_ids": ["ship-it"],
        "blocked_reason_counts": {"use_frequency_zero": 1},
        "candidates": [
            {
                "turn_index": 1,
                "candidate_id": "reply_sticker",
                "selected": True,
                "sticker_id": "ship-it",
                "pack_id": "engineering",
                "meaning": "通过时使用",
                "media_ref": "qq-image://ship-it",
                "media_source": "local_pack",
                "local_path": "stickers/ship.png",
                "reasons": ["scene_tag:review"],
                "blocked_reasons": [],
                "reply_preview": "[sticker:ship-it]",
            },
            {
                "turn_index": 2,
                "candidate_id": "reply_text",
                "selected": False,
                "sticker_id": "",
                "pack_id": "",
                "meaning": "",
                "media_ref": "",
                "media_source": "",
                "local_path": "",
                "reasons": [],
                "blocked_reasons": ["use_frequency_zero"],
                "reply_preview": "我看到了，先按上下文处理。",
            },
        ],
    }
    assert report["summary"]["sticker_review_candidate_count"] == 2
    assert report["summary"]["sticker_blocked_candidate_count"] == 1


def test_social_runner_qq_beta_closeout_includes_sticker_review_checklist(
    tmp_path: Path,
    capsys,
) -> None:
    beta_day_report = _write_json(
        tmp_path / "beta-day-report.json",
        {
            "kind": "qq_beta_day_report",
            "ready_for_send": False,
            "summary": {
                "failure_count": 0,
                "open_failure_count": 0,
                "warning_count": 1,
                "decision_count": 2,
                "sticker_review_candidate_count": 2,
                "sticker_blocked_candidate_count": 1,
            },
            "review_warnings": ["dry_run_candidates_not_selected"],
            "sticker_review": {
                "candidate_count": 2,
                "selected_candidate_count": 1,
                "blocked_candidate_count": 1,
                "sticker_ids": ["ship-it"],
                "blocked_reason_counts": {"use_frequency_zero": 1},
                "candidates": [],
            },
            "failures": [],
            "next_actions": ["review_dry_run_warnings", "keep_send_guarded"],
        },
    )
    regression_intake = _write_json(
        tmp_path / "regression-intake.json",
        {"kind": "qq_regression_intake", "draft_count": 0, "drafts": []},
    )
    output = tmp_path / "beta-closeout.json"

    assert main(
        [
            "qq",
            "beta-closeout",
            "--beta-day-report",
            str(beta_day_report),
            "--regression-intake",
            str(regression_intake),
            "--output",
            str(output),
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["sticker_review"]["blocked_reason_counts"] == {
        "use_frequency_zero": 1
    }
    report = _read_json(output)
    assert report["sticker_review"]["candidate_count"] == 2
    assert {
        "name": "sticker_review",
        "status": "needs_review",
        "candidate_count": 2,
        "blocked_candidate_count": 1,
        "blocked_reason_counts": {"use_frequency_zero": 1},
    } in report["checklist"]


def _dry_run_review_payload() -> dict:
    return {
        "kind": "qq_dry_run_review",
        "group_id": "99999",
        "ready_for_send": False,
        "summary": {
            "decision_count": 2,
            "dry_run_decision_count": 2,
            "proposed_action_count": 2,
            "selected_action_count": 0,
            "rejected_action_count": 2,
            "sticker_candidate_count": 1,
            "send_feedback_count": 0,
        },
        "turns": [
            {
                "index": 1,
                "proposed": [
                    {
                        "candidate_id": "reply_sticker",
                        "reply_preview": "[sticker:ship-it]",
                        "sticker_selection": {
                            "selected": True,
                            "sticker_id": "ship-it",
                            "pack_id": "engineering",
                            "media_ref": "qq-image://ship-it",
                            "media_source": "local_pack",
                            "local_path": "stickers/ship.png",
                            "meaning": "通过时使用",
                            "tags": ["ship", "review"],
                            "reasons": ["scene_tag:review"],
                            "blocked_reasons": [],
                            "recent_sticker_ids": [],
                            "emotion": "",
                            "scene_tags": [],
                            "candidate_count": 1,
                            "allow_sticker_only": True,
                        },
                    }
                ],
                "rejected": {"reply_sticker": "dry_run:not selected for sending"},
            },
            {
                "index": 2,
                "proposed": [
                    {
                        "candidate_id": "reply_text",
                        "reply_preview": "我看到了，先按上下文处理。",
                        "sticker_selection": {
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
                        },
                    }
                ],
                "rejected": {"reply_text": "dry_run:not selected for sending"},
            },
        ],
        "warnings": ["dry_run_candidates_not_selected"],
    }
