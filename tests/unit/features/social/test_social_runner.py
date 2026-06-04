from __future__ import annotations

import json
from pathlib import Path
import tomllib

from isotope.features.social.runner import main
from tests.unit.features.social.test_character_card import _card_dict


def _event(message_id: int = 123) -> dict:
    return {
        "message_id": message_id,
        "message_type": "group",
        "group_id": 99999,
        "user_id": 10001,
        "sender": {"nickname": "小林", "role": "member"},
        "time": 1780560000,
        "message": [
            {"type": "at", "data": {"qq": "bot_qq"}},
            {"type": "text", "data": {"text": " 看看这个 PR"}},
        ],
        "raw_message": "[CQ:at,qq=bot_qq] 看看这个 PR",
    }


def _config() -> dict:
    return {
        "bot_user_id": "bot_qq",
        "dry_run": True,
        "group_policy": {
            "allowed_groups": ["99999"],
            "blocked_groups": ["300"],
            "operator_user_ids": ["op"],
        },
        "role_card": _card_dict(),
        "sticker_library": {
            "entries": [
                {
                    "sticker_id": "ship-it",
                    "pack_id": "engineering",
                    "media": {
                        "media_ref": "qq-image://ship-it",
                        "kind": "sticker",
                        "source": "local_pack",
                    },
                    "tags": ["ship", "review"],
                    "meaning": "通过时使用",
                    "source": "engineering_pack",
                }
            ]
        },
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_social_runner_qq_dry_run_records_decision_without_sending(
    tmp_path: Path,
    capsys,
) -> None:
    config = _write_json(tmp_path / "config.json", _config())
    event = _write_json(tmp_path / "event.json", _event())

    code = main(
        [
            "qq",
            "dry-run",
            "--config-json",
            str(config),
            "--event-json",
            str(event),
            "--state-root",
            str(tmp_path / "state"),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["turn"]["decision"]["proposed"][0]["kind"] == "respond"
    assert payload["turn"]["decision"]["selected"] == []
    assert payload["sent_group_messages"] == []
    state = _read_json(tmp_path / "state" / "social-qq-state.json")
    assert [entry["kind"] for entry in state["audit_entries"]] == ["decision"]


def test_social_runner_qq_run_send_records_feedback(tmp_path: Path, capsys) -> None:
    config = _write_json(tmp_path / "config.json", _config())
    event = _write_json(tmp_path / "event.json", _event())

    code = main(
        [
            "qq",
            "run",
            "--config-json",
            str(config),
            "--event-json",
            str(event),
            "--state-root",
            str(tmp_path / "state"),
            "--send",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["turn"]["send_feedback"][0]["status"] == "sent"
    assert payload["sent_group_messages"][0]["group_id"] == "99999"
    state = _read_json(tmp_path / "state" / "social-qq-state.json")
    assert [entry["kind"] for entry in state["audit_entries"]] == ["decision", "send"]


def test_social_runner_qq_pause_and_resume_persist_state(tmp_path: Path, capsys) -> None:
    config = _write_json(tmp_path / "config.json", _config())
    event = _write_json(tmp_path / "event.json", _event())
    state_root = tmp_path / "state"

    assert main(
        [
            "qq",
            "pause",
            "--config-json",
            str(config),
            "--state-root",
            str(state_root),
            "--group",
            "99999",
            "--operator",
            "op",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert main(
        [
            "qq",
            "run",
            "--config-json",
            str(config),
            "--event-json",
            str(event),
            "--state-root",
            str(state_root),
            "--send",
            "--json",
        ]
    ) == 0
    paused_payload = json.loads(capsys.readouterr().out)
    assert paused_payload["turn"]["policy"]["reason"] == "group_paused:99999"
    assert paused_payload["sent_group_messages"] == []

    assert main(
        [
            "qq",
            "resume",
            "--config-json",
            str(config),
            "--state-root",
            str(state_root),
            "--group",
            "99999",
            "--operator",
            "op",
            "--json",
        ]
    ) == 0
    resumed_payload = json.loads(capsys.readouterr().out)
    assert resumed_payload["result"] == {"ok": True, "reason": "group_resumed:99999"}


def test_social_runner_qq_inspect_role_and_stickers(tmp_path: Path, capsys) -> None:
    config = _write_json(tmp_path / "config.json", _config())

    assert main(["qq", "inspect", "role", "--config-json", str(config), "--json"]) == 0
    role_payload = json.loads(capsys.readouterr().out)
    assert role_payload["role"]["identity"]["name"] == "群聊工程猫"

    assert main(["qq", "inspect", "stickers", "--config-json", str(config), "--json"]) == 0
    stickers_payload = json.loads(capsys.readouterr().out)
    assert stickers_payload["stickers"]["entries"][0]["sticker_id"] == "ship-it"


def test_social_runner_qq_health_and_export_log(tmp_path: Path, capsys) -> None:
    config = _write_json(tmp_path / "config.json", _config())
    event = _write_json(tmp_path / "event.json", _event())
    state_root = tmp_path / "state"
    output = tmp_path / "logs.json"

    assert main(
        [
            "qq",
            "run",
            "--config-json",
            str(config),
            "--event-json",
            str(event),
            "--state-root",
            str(state_root),
            "--send",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert main(
        [
            "qq",
            "health",
            "--config-json",
            str(config),
            "--state-root",
            str(state_root),
            "--json",
        ]
    ) == 0
    health_payload = json.loads(capsys.readouterr().out)
    assert health_payload["health"]["audit_counts"] == {"decision": 1, "send": 1}

    assert main(
        [
            "qq",
            "export-log",
            "--state-root",
            str(state_root),
            "--group",
            "99999",
            "--output",
            str(output),
            "--json",
        ]
    ) == 0
    export_payload = json.loads(capsys.readouterr().out)
    assert export_payload["output"] == str(output)
    assert [entry["kind"] for entry in _read_json(output)["entries"]] == ["decision", "send"]


def test_social_runner_entry_point_is_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["isotope-social"] == (
        "isotope.features.social.runner:main"
    )
