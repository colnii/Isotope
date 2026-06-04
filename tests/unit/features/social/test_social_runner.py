from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tomllib

from isotope.features.social import (
    CharacterCard,
    StickerLibrary,
    qq_runtime_commands,
    startup_gate,
)
from isotope.features.social.runner import main
from isotope.llm.provider import LLMProviderResolution
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


def _prepare_profiled_replay_pack(tmp_path: Path, capsys) -> tuple[Path, Path]:
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
    assert main(
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
    ) == 0
    capsys.readouterr()
    return beta_dir, report_path


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


class FakeQQReplyChatProvider:
    provider = "unit-chat"
    model = "unit-model"

    def generate(self, messages, *, max_tokens=512):
        return type(
            "Response",
            (),
            {
                "provider": self.provider,
                "model": self.model,
                "content": json.dumps({"text": "小林，我按群聊上下文看完了。"}),
                "usage": {"total_tokens": 9},
            },
        )()


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
    assert payload["turn"]["context"]["persona_instructions"]["role_name"] == "群聊工程猫"
    assert (
        payload["turn"]["context"]["persona_instructions"]["voice"]["speaking_style"]
        == "直接、简洁、带一点吐槽"
    )
    assert payload["turn"]["context"]["chat_context"]["current_message"]["text"] == "看看这个 PR"
    assert payload["turn"]["context"]["chat_context"]["current_message"]["sender"]["display_name"] == "小林"
    assert payload["sent_group_messages"] == []
    state = _read_json(tmp_path / "state" / "social-qq-state.json")
    assert [entry["kind"] for entry in state["audit_entries"]] == ["decision"]


def test_social_runner_qq_dry_run_can_use_llm_reply_provider(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    config_payload = _config()
    config_payload["runtime"] = {"reply_provider": "llm"}
    config = _write_json(tmp_path / "config.json", config_payload)
    event = _write_json(tmp_path / "event.json", _event())

    monkeypatch.setattr(
        qq_runtime_commands,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="configured",
            reason_code="llm_provider_configured",
            provider_name="unit-chat",
            provider=FakeQQReplyChatProvider(),
        ),
        raising=False,
    )

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
    candidate = payload["turn"]["decision"]["proposed"][0]
    assert candidate["reply_action"]["parts"][0]["text"] == "小林，我按群聊上下文看完了。"
    assert candidate["metadata"]["reply_provider"]["provider"] == "unit-chat"
    assert candidate["metadata"]["reply_provider"]["model"] == "unit-model"


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
    monkeypatch.setattr(
        qq_runtime_commands,
        "OneBotWebSocketClient",
        FakeLiveOneBotClient,
        raising=False,
    )
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


def test_social_runner_qq_review_dry_run_writes_operator_report(
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
    config_payload["runtime"] = {
        "sticker_emotion": "positive",
        "sticker_scene_tags": ["review"],
        "allow_sticker_only": True,
    }
    config = _write_json(tmp_path / "config.json", config_payload)
    state_root = tmp_path / "state"
    report_path = tmp_path / "dry-run-review.json"

    assert main(
        [
            "qq",
            "live-run",
            "--config-json",
            str(config),
            "--state-root",
            str(state_root),
            "--websocket-url",
            "ws://127.0.0.1:3001",
            "--max-events",
            "1",
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    code = main(
        [
            "qq",
            "review-dry-run",
            "--state-root",
            str(state_root),
            "--group",
            "99999",
            "--output",
            str(report_path),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "review-dry-run"
    assert payload["output"] == str(report_path)
    assert payload["ready_for_send"] is False
    assert payload["summary"] == {
        "decision_count": 1,
        "dry_run_decision_count": 1,
        "proposed_action_count": 1,
        "selected_action_count": 0,
        "rejected_action_count": 1,
        "sticker_candidate_count": 1,
        "send_feedback_count": 0,
    }

    report = _read_json(report_path)
    assert report["kind"] == "qq_dry_run_review"
    assert report["ready_for_send"] is False
    assert report["turns"][0]["wake_reason"] == "mention:bot_qq"
    assert report["turns"][0]["proposed"][0]["candidate_id"] == "reply_sticker"
    assert report["turns"][0]["proposed"][0]["sticker"]["sticker_id"] == "ship-it"
    assert report["turns"][0]["rejected"]["reply_sticker"] == (
        "dry_run:not selected for sending"
    )
    assert "dry_run_candidates_not_selected" in report["warnings"]


def test_social_runner_qq_beta_day_report_combines_review_log_and_failures(
    tmp_path: Path,
    capsys,
) -> None:
    dry_run_review = _write_json(
        tmp_path / "dry-run-review.json",
        {
            "kind": "qq_dry_run_review",
            "group_id": "99999",
            "ready_for_send": False,
            "summary": {
                "decision_count": 5,
                "dry_run_decision_count": 5,
                "proposed_action_count": 4,
                "selected_action_count": 0,
                "rejected_action_count": 4,
                "sticker_candidate_count": 2,
                "send_feedback_count": 0,
            },
            "warnings": ["dry_run_candidates_not_selected"],
        },
    )
    export_log = _write_json(
        tmp_path / "qq-99999.json",
        {
            "entries": [
                {"kind": "decision", "group_id": "99999", "payload": {}},
                {"kind": "decision", "group_id": "99999", "payload": {}},
                {"kind": "send", "group_id": "99999", "payload": {"status": "failed"}},
            ]
        },
    )
    failures = _write_json(
        tmp_path / "failures.json",
        {
            "failures": [
                {
                    "status": "open",
                    "symptom": "表情包语气太像公告",
                    "root_cause": "role-card sticker meaning too broad",
                    "regression_test": "tests/integration/social/test_social_fake_platform_flow.py",
                }
            ]
        },
    )
    output = tmp_path / "beta-day-report.json"

    code = main(
        [
            "qq",
            "beta-day-report",
            "--date",
            "2026-06-04",
            "--group",
            "99999",
            "--dry-run-review",
            str(dry_run_review),
            "--export-log",
            str(export_log),
            "--failures-json",
            str(failures),
            "--output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "beta-day-report"
    assert payload["output"] == str(output)
    assert payload["ready_for_send"] is False
    assert payload["open_failure_count"] == 1
    assert payload["summary"]["audit_entry_count"] == 3
    assert payload["summary"]["decision_count"] == 5
    assert "resolve_open_failures" in payload["next_actions"]

    report = _read_json(output)
    assert report["kind"] == "qq_beta_day_report"
    assert report["date"] == "2026-06-04"
    assert report["group_id"] == "99999"
    assert report["review_warnings"] == ["dry_run_candidates_not_selected"]
    assert report["failures"][0]["symptom"] == "表情包语气太像公告"


def test_social_runner_qq_regression_intake_writes_replay_drafts(
    tmp_path: Path,
    capsys,
) -> None:
    failures = _write_json(
        tmp_path / "failures.json",
        {
            "failures": [
                {
                    "id": "qq-beta-1",
                    "date": "2026-06-04",
                    "group": "99999",
                    "status": "open",
                    "symptom": "表情包语气太像公告",
                    "observed_input": "bot 这个能不能别像公告？",
                    "root_cause": "role-card sticker meaning too broad",
                    "regression_test": "tests/integration/social/test_social_fake_platform_flow.py",
                },
                {
                    "id": "qq-beta-closed",
                    "group": "99999",
                    "status": "closed",
                    "symptom": "已修复问题",
                    "observed_input": "bot 已经好了",
                },
            ]
        },
    )
    output_dir = tmp_path / "regressions"
    index_output = tmp_path / "regression-intake.json"

    code = main(
        [
            "qq",
            "regression-intake",
            "--group",
            "99999",
            "--bot-user-id",
            "bot_qq",
            "--failures-json",
            str(failures),
            "--output-dir",
            str(output_dir),
            "--index-output",
            str(index_output),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "regression-intake"
    assert payload["draft_count"] == 1
    assert payload["open_failure_count"] == 1
    assert payload["index_output"] == str(index_output)

    index = _read_json(index_output)
    assert index["kind"] == "qq_regression_intake"
    assert index["group_id"] == "99999"
    assert index["drafts"][0]["failure_id"] == "qq-beta-1"
    draft_path = Path(index["drafts"][0]["replay_json"])
    assert payload["drafts"] == [str(draft_path)]

    replay = _read_json(draft_path)
    assert replay["schema_version"] == "isotope.qq_replay.v1"
    assert replay["name"] == "QQ regression draft: qq-beta-1"
    assert replay["metadata"]["failure_id"] == "qq-beta-1"
    assert replay["metadata"]["symptom"] == "表情包语气太像公告"
    assert replay["expectations"]["require_processed_events"] == 1
    assert replay["expectations"]["max_send_feedback"] == 0
    assert len(replay["events"]) == 1
    event = replay["events"][0]
    assert event["group_id"] == 99999
    assert event["message"][0] == {"type": "at", "data": {"qq": "bot_qq"}}
    assert event["message"][1]["data"]["text"] == " bot 这个能不能别像公告？"
    assert event["raw_message"] == "[CQ:at,qq=bot_qq] bot 这个能不能别像公告？"


def test_social_runner_qq_live_run_send_records_feedback(
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
    monkeypatch.setattr(
        qq_runtime_commands,
        "OneBotWebSocketClient",
        FakeLiveOneBotClient,
        raising=False,
    )
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

    monkeypatch.setattr(
        qq_runtime_commands,
        "OneBotWebSocketClient",
        MissingDependencyClient,
        raising=False,
    )
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
        "beta-day-report.sh",
        "dry-run.sh",
        "export-log.sh",
        "health.sh",
        "pause.sh",
        "regression-intake.sh",
        "resume.sh",
        "review-dry-run.sh",
        "send-run.sh",
        "startup-check.sh",
    ]

    config = _read_json(output_dir / "config.json")
    assert config["bot_user_id"] == "bot_qq"
    assert config["group_policy"]["allowed_groups"] == ["99999"]
    assert config["group_policy"]["operator_user_ids"] == ["op"]
    assert config["dry_run"] is True
    assert config["runtime"]["reply_provider"] == "deterministic"
    assert (output_dir / "state").is_dir()
    assert (output_dir / "logs").is_dir()
    assert (output_dir / "regressions").is_dir()
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "First run order" in readme
    assert 'runtime.reply_provider = "llm"' in readme

    health = (output_dir / "health.sh").read_text(encoding="utf-8")
    assert "live-run" in health
    assert "--max-events 0" in health
    assert "--send" not in health

    dry_run = (output_dir / "dry-run.sh").read_text(encoding="utf-8")
    assert "--max-events 7" in dry_run
    assert "--send" not in dry_run
    assert "./startup-check.sh" in dry_run

    review = (output_dir / "review-dry-run.sh").read_text(encoding="utf-8")
    assert " qq review-dry-run " in review
    assert "--state-root state" in review
    assert "--group 99999" in review
    assert "--output logs/dry-run-review.json" in review

    beta_day = (output_dir / "beta-day-report.sh").read_text(encoding="utf-8")
    assert " qq beta-day-report " in beta_day
    assert 'ISOTOPE_QQ_BETA_DATE:-$(date +%F)' in beta_day
    assert "--dry-run-review logs/dry-run-review.json" in beta_day
    assert "--export-log logs/qq-99999.json" in beta_day
    assert "--failures-json logs/failures.json" in beta_day
    assert "--output logs/beta-day-report.json" in beta_day
    assert _read_json(output_dir / "logs" / "failures.json") == {"failures": []}

    regression_intake = (output_dir / "regression-intake.sh").read_text(encoding="utf-8")
    assert " qq regression-intake " in regression_intake
    assert "--group 99999" in regression_intake
    assert "--bot-user-id bot_qq" in regression_intake
    assert "--failures-json logs/failures.json" in regression_intake
    assert "--output-dir regressions" in regression_intake
    assert "--index-output logs/regression-intake.json" in regression_intake

    send_run = (output_dir / "send-run.sh").read_text(encoding="utf-8")
    assert "ISOTOPE_QQ_ENABLE_SEND" in send_run
    assert "--send" in send_run
    assert send_run.index("ISOTOPE_QQ_ENABLE_SEND") < send_run.index("./startup-check.sh")

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
    (output_dir / "logs").mkdir()
    existing_failures = _write_json(
        output_dir / "logs" / "failures.json",
        {"failures": [{"status": "open", "symptom": "existing issue"}]},
    )

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
    assert _read_json(existing_failures)["failures"][0]["symptom"] == "existing issue"


def test_social_runner_qq_beta_check_exercises_operator_pack(
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

    code = main(["qq", "beta-check", "--pack-dir", str(output_dir), "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "beta-check"
    assert payload["pack_dir"] == str(output_dir)
    assert payload["ok"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "required_files",
        "config_json",
        "shell_syntax",
        "operator_scripts",
        "send_guard",
    ]
    assert all(check["ok"] for check in payload["checks"])
    assert payload["export_log_path"] == str(output_dir / "logs" / "qq-99999.json")
    state = _read_json(output_dir / "state" / "social-qq-state.json")
    assert state["paused_groups"] == []
    assert _read_json(output_dir / "logs" / "qq-99999.json") == {"entries": []}


def test_social_runner_qq_init_profile_writes_editable_role_and_stickers(
    tmp_path: Path,
    capsys,
) -> None:
    profile_dir = tmp_path / "qq-profile"

    code = main(
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
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "init-profile"
    assert payload["output_dir"] == str(profile_dir)
    assert payload["role_card_path"] == str(profile_dir / "role-card.json")
    assert payload["sticker_library_path"] == str(profile_dir / "sticker-library.json")
    assert payload["readme_path"] == str(profile_dir / "README.md")

    role_payload = _read_json(profile_dir / "role-card.json")
    role = CharacterCard.from_dict(role_payload)
    assert role.identity.name == "群聊工程猫"
    assert role.stickers.enabled is True
    assert role.stickers.allow_sticker_only_reply is True
    assert role.group_overrides["99999"]["social_behavior"]["talkativeness"] == 0.4

    stickers = StickerLibrary.from_dict(_read_json(profile_dir / "sticker-library.json"))
    assert [entry.sticker_id for entry in stickers.entries] == [
        "ack-ok",
        "ship-it",
        "need-context",
        "calm-down",
    ]
    assert stickers.entries[0].allowed_groups == ("99999",)
    profile_readme = (profile_dir / "README.md").read_text(encoding="utf-8")
    assert "apply-profile" in profile_readme
    assert 'runtime.reply_provider = "llm"' in profile_readme


def test_social_runner_qq_apply_profile_updates_beta_config_and_beta_check(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir = tmp_path / "qq-beta"
    profile_dir = tmp_path / "qq-profile"

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

    code = main(
        [
            "qq",
            "apply-profile",
            "--pack-dir",
            str(beta_dir),
            "--profile-dir",
            str(profile_dir),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "apply-profile"
    assert payload["config_path"] == str(beta_dir / "config.json")
    assert payload["backup_path"] == str(beta_dir / "config.before-profile.json")
    assert payload["role_card_path"] == str(profile_dir / "role-card.json")
    assert payload["sticker_library_path"] == str(profile_dir / "sticker-library.json")

    config = _read_json(beta_dir / "config.json")
    assert config["role_card_path"] == "../qq-profile/role-card.json"
    assert config["sticker_library_path"] == "../qq-profile/sticker-library.json"
    assert config["runtime"]["reply_provider"] == "deterministic"
    assert "role_card" not in config
    assert "sticker_library" not in config
    assert (beta_dir / "config.before-profile.json").exists()

    assert main(
        ["qq", "inspect", "role", "--config-json", str(beta_dir / "config.json"), "--json"]
    ) == 0
    role_payload = json.loads(capsys.readouterr().out)
    assert role_payload["role"]["identity"]["name"] == "群聊工程猫"
    assert main(
        [
            "qq",
            "inspect",
            "stickers",
            "--config-json",
            str(beta_dir / "config.json"),
            "--json",
        ]
    ) == 0
    sticker_payload = json.loads(capsys.readouterr().out)
    assert sticker_payload["stickers"]["entries"][0]["sticker_id"] == "ack-ok"

    assert main(["qq", "beta-check", "--pack-dir", str(beta_dir), "--json"]) == 0
    check_payload = json.loads(capsys.readouterr().out)
    assert check_payload["ok"] is True


def test_social_runner_qq_startup_check_passes_after_profile_and_replay(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir, report_path = _prepare_profiled_replay_pack(tmp_path, capsys)

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(report_path),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "startup-check"
    assert payload["ready"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "beta_pack",
        "profile_assets",
        "sticker_assets",
        "llm_reply_provider",
        "replay_report",
    ]
    assert all(check["ok"] for check in payload["checks"])


def test_social_runner_qq_startup_check_blocks_llm_reply_without_provider(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    beta_dir, report_path = _prepare_profiled_replay_pack(tmp_path, capsys)
    config_path = beta_dir / "config.json"
    config = _read_json(config_path)
    config["runtime"]["reply_provider"] = "llm"
    _write_json(config_path, config)
    monkeypatch.setattr(
        startup_gate,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_not_configured",
            provider_name="auto",
        ),
    )

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(report_path),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    failed = [check for check in payload["checks"] if not check["ok"]]
    assert [check["name"] for check in failed] == ["llm_reply_provider"]
    assert failed[0]["reason_code"] == "llm_provider_not_configured"


def test_social_runner_qq_startup_check_blocks_missing_profile_and_replay(
    tmp_path: Path,
    capsys,
) -> None:
    beta_dir = tmp_path / "qq-beta"
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

    code = main(
        [
            "qq",
            "startup-check",
            "--pack-dir",
            str(beta_dir),
            "--replay-report",
            str(beta_dir / "logs" / "replay-report.json"),
            "--json",
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["command"] == "startup-check"
    assert payload["ready"] is False
    failed = [check["name"] for check in payload["checks"] if not check["ok"]]
    assert failed == ["profile_assets", "sticker_assets", "replay_report"]


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
        "max_send_feedback",
        "max_sent_group_messages",
        "require_all_dry_run",
    ]
    assert all(item["ok"] for item in report["expectations"])
    assert report["summary"]["event_count"] == 2
    assert report["summary"]["processed_events"] == 2
    assert report["summary"]["proposed_action_count"] >= 1
    assert report["summary"]["sticker_candidate_count"] >= 1
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
    ]
    assert failed[0]["expected"] == 2
    assert failed[0]["actual"] == 1


def test_social_runner_entry_point_is_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["isotope-social"] == (
        "isotope.features.social.runner:main"
    )
