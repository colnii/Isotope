from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tomllib

from isotope.features.social import runner
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


class FakeLiveOneBotClient:
    instances: list["FakeLiveOneBotClient"] = []

    def __init__(
        self,
        url: str,
        *,
        access_token: str | None = None,
        request_timeout_seconds: float = 5.0,
        receive_timeout_seconds: float = 30.0,
    ):
        self.url = url
        self.access_token = access_token
        self.request_timeout_seconds = request_timeout_seconds
        self.receive_timeout_seconds = receive_timeout_seconds
        self.connected = False
        self.events = [_event()]
        self.sent_group_messages: list[dict] = []
        self.sent_private_messages: list[dict] = []
        FakeLiveOneBotClient.instances.append(self)

    def connect(self) -> None:
        self.connected = True

    def receive_event(self) -> dict | None:
        self.connected = True
        if not self.events:
            return None
        return self.events.pop(0)

    def send_group_msg(self, *, group_id: str, message: list[dict]) -> dict:
        self.sent_group_messages.append({"group_id": group_id, "message": message})
        return {"status": "ok", "message_id": "live-group-1"}

    def send_private_msg(self, *, user_id: str, message: list[dict]) -> dict:
        self.sent_private_messages.append({"user_id": user_id, "message": message})
        return {"status": "ok", "message_id": "live-private-1"}

    def connection_state(self) -> dict:
        return {
            "connected": self.connected,
            "pending_events": len(self.events),
            "seen_message_count": 0,
            "api_sequence": len(self.sent_group_messages) + len(self.sent_private_messages),
        }

    def close(self) -> None:
        self.connected = False


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


def test_social_runner_qq_live_run_defaults_to_dry_run(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    FakeLiveOneBotClient.instances = []
    monkeypatch.setattr(runner, "OneBotWebSocketClient", FakeLiveOneBotClient, raising=False)
    config = _write_json(tmp_path / "config.json", _config())

    code = main(
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
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "live-run"
    assert payload["processed_events"] == 1
    assert payload["turns"][0]["decision"]["dry_run"] is True
    assert payload["turns"][0]["send_feedback"] == []
    assert FakeLiveOneBotClient.instances[0].sent_group_messages == []


def test_social_runner_qq_live_run_send_records_feedback(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    FakeLiveOneBotClient.instances = []
    monkeypatch.setattr(runner, "OneBotWebSocketClient", FakeLiveOneBotClient, raising=False)
    config = _write_json(tmp_path / "config.json", _config())

    code = main(
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
            "--send",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["turns"][0]["send_feedback"][0]["status"] == "sent"
    assert FakeLiveOneBotClient.instances[0].sent_group_messages[0]["group_id"] == "99999"
    state = _read_json(tmp_path / "state" / "social-qq-state.json")
    assert [entry["kind"] for entry in state["audit_entries"]] == ["decision", "send"]


def test_social_runner_qq_live_run_health_only_connects_without_consuming_event(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    FakeLiveOneBotClient.instances = []
    monkeypatch.setattr(runner, "OneBotWebSocketClient", FakeLiveOneBotClient, raising=False)
    config = _write_json(tmp_path / "config.json", _config())

    code = main(
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
            "0",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed_events"] == 0
    assert payload["turns"] == []
    assert payload["health"]["adapter_states"][0]["connected"] is True
    assert payload["health"]["adapter_states"][0]["pending_events"] == 1


def test_social_runner_qq_live_run_reports_missing_websocket_dependency(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    class MissingDependencyClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("websockets is required for qq live-run")

    monkeypatch.setattr(runner, "OneBotWebSocketClient", MissingDependencyClient, raising=False)
    config = _write_json(tmp_path / "config.json", _config())

    code = main(
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
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "social_runner_error"
    assert "websockets is required" in payload["error"]["message"]


def test_social_runner_qq_init_beta_writes_operator_pack(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "qq-beta"

    code = main(
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
            "--max-events",
            "7",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "init-beta"
    assert payload["output_dir"] == str(output_dir)
    assert sorted(payload["scripts"]) == [
        "dry-run.sh",
        "export-log.sh",
        "health.sh",
        "pause.sh",
        "resume.sh",
        "send-run.sh",
    ]

    config = _read_json(output_dir / "config.json")
    assert config["bot_user_id"] == "bot_qq"
    assert config["group_policy"]["allowed_groups"] == ["99999"]
    assert config["group_policy"]["operator_user_ids"] == ["op"]
    assert config["dry_run"] is True
    assert (output_dir / "state").is_dir()
    assert (output_dir / "logs").is_dir()
    assert "First run order" in (output_dir / "README.md").read_text(encoding="utf-8")

    health = (output_dir / "health.sh").read_text(encoding="utf-8")
    assert "live-run" in health
    assert "--max-events 0" in health
    assert "--send" not in health

    dry_run = (output_dir / "dry-run.sh").read_text(encoding="utf-8")
    assert "--max-events 7" in dry_run
    assert "--send" not in dry_run

    send_run = (output_dir / "send-run.sh").read_text(encoding="utf-8")
    assert "ISOTOPE_QQ_ENABLE_SEND" in send_run
    assert "--send" in send_run

    pause = (output_dir / "pause.sh").read_text(encoding="utf-8")
    assert " qq pause " in pause
    assert "--operator op" in pause
    resume = (output_dir / "resume.sh").read_text(encoding="utf-8")
    assert " qq resume " in resume
    export_log = (output_dir / "export-log.sh").read_text(encoding="utf-8")
    assert " qq export-log " in export_log
    assert "logs/qq-99999.json" in export_log
    for script in payload["scripts"]:
        subprocess.run(
            ["bash", "-n", str(output_dir / script)],
            check=True,
        )


def test_social_runner_qq_init_beta_refuses_existing_pack_without_force(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "qq-beta"
    output_dir.mkdir()
    (output_dir / "config.json").write_text("{}", encoding="utf-8")

    code = main(
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
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "social_runner_error"
    assert "already exists" in payload["error"]["message"]


def test_social_runner_qq_init_beta_force_overwrites_pack(
    tmp_path: Path,
    capsys,
) -> None:
    output_dir = tmp_path / "qq-beta"
    output_dir.mkdir()
    (output_dir / "config.json").write_text("{}", encoding="utf-8")

    code = main(
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
            "--force",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert _read_json(output_dir / "config.json")["group_policy"]["allowed_groups"] == [
        "99999"
    ]


def test_social_runner_entry_point_is_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["isotope-social"] == (
        "isotope.features.social.runner:main"
    )
