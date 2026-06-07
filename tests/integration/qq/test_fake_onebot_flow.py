from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib

import pytest

from isotope.features.social import qq_runtime_commands
from isotope.features.social import runner as social_runner
from isotope.features.social import SocialMessagePart, SocialReplyAction, SocialTarget
from isotope.integrations.qq import FakeOneBotClient, OneBotAdapter


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
            {"type": "text", "data": {"text": " 这 PR 过了"}},
            {
                "type": "image",
                "data": {
                    "file": "ship-it.png",
                    "url": "qq-image://ship-it",
                    "sub_type": "sticker",
                },
            },
        ],
        "raw_message": "[CQ:at,qq=bot_qq] 这 PR 过了",
    }


def test_fake_onebot_client_queued_event_normalizes_to_social_message() -> None:
    client = FakeOneBotClient()
    client.queue_event(_event())
    adapter = OneBotAdapter(client=client)

    message = adapter.receive_next()

    assert message is not None
    assert message.group_id == "99999"
    assert message.parts[2].kind == "sticker"
    assert message.parts[2].media_ref == "qq-image://ship-it"
    assert adapter.connection_state().pending_events == 0
    assert adapter.connection_state().seen_message_count == 1


def test_fake_onebot_flow_sends_sticker_capable_reply() -> None:
    client = FakeOneBotClient()
    adapter = OneBotAdapter(client=client)
    action = SocialReplyAction(
        action_id="reply_sticker",
        target=SocialTarget(platform="qq", chat_type="group", group_id="99999"),
        parts=(SocialMessagePart(kind="sticker", media_ref="qq-image://ship-it"),),
    )

    feedback = adapter.send_action(action)

    assert feedback.status == "sent"
    assert feedback.sent_message_ids == ("onebot_group_1",)
    assert client.sent_group_messages[0]["message"] == [
        {"type": "image", "data": {"file": "qq-image://ship-it", "sub_type": "sticker"}}
    ]


def test_onebot_history_backfill_skips_duplicate_events() -> None:
    adapter = OneBotAdapter(client=FakeOneBotClient())

    messages = adapter.normalize_history((_event(123), _event(124), _event(123)))

    assert [message.message_id for message in messages] == ["123", "124"]


DEFAULT_REAL_SMOKE_CONFIG = Path(".isotope/dev/qq-real-smoke.toml")


def _real_smoke_enabled() -> bool:
    if os.environ.get("ISOTOPE_QQ_REAL_SMOKE") == "1":
        return True
    return _real_smoke_toml_config().get("enabled") is True


def _real_smoke_toml_config() -> dict[str, object]:
    path = _real_smoke_toml_path()
    if not path.is_file():
        return {}
    with path.open("rb") as file:
        payload = tomllib.load(file)
    qq = payload.get("qq", {})
    if not isinstance(qq, dict):
        return {}
    config = qq.get("real_smoke", {})
    return config if isinstance(config, dict) else {}


def _real_smoke_toml_path() -> Path:
    configured = os.environ.get("ISOTOPE_QQ_REAL_SMOKE_CONFIG")
    return Path(configured) if configured else DEFAULT_REAL_SMOKE_CONFIG


def _write_real_smoke_toml(
    path: Path,
    *,
    access_token: str = "napcat-token",
    mode: str = "dry-run",
    timeout: int = 7,
) -> None:
    path.write_text(
        "\n".join(
            [
                "[qq.real_smoke]",
                "enabled = true",
                'onebot_url = "ws://127.0.0.1:3001"',
                'test_group = "99999"',
                'bot_user_id = "bot_qq"',
                f'access_token = "{access_token}"',
                f'mode = "{mode}"',
                f"timeout = {timeout}",
            ]
        ),
        encoding="utf-8",
    )


def test_real_qq_smoke_env_requires_websocket_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE", "1")
    monkeypatch.delenv("ISOTOPE_QQ_ONEBOT_URL", raising=False)
    monkeypatch.setenv("ISOTOPE_QQ_TEST_GROUP", "99999")

    with pytest.raises(AssertionError, match="ISOTOPE_QQ_ONEBOT_URL is required"):
        _real_smoke_env()


def test_real_qq_smoke_env_loads_dev_toml_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / "qq-real-smoke.toml"
    _write_real_smoke_toml(config)
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE_CONFIG", str(config))
    monkeypatch.delenv("ISOTOPE_QQ_ONEBOT_URL", raising=False)
    monkeypatch.delenv("ISOTOPE_QQ_TEST_GROUP", raising=False)
    monkeypatch.delenv("ISOTOPE_QQ_BOT_USER_ID", raising=False)
    monkeypatch.delenv("ISOTOPE_QQ_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ISOTOPE_QQ_REAL_SMOKE_MODE", raising=False)
    monkeypatch.delenv("ISOTOPE_QQ_REAL_SMOKE_TIMEOUT", raising=False)

    env = _real_smoke_env()

    assert env == {
        "onebot_url": "ws://127.0.0.1:3001",
        "group_id": "99999",
        "bot_user_id": "bot_qq",
        "access_token": "napcat-token",
        "mode": "dry-run",
        "timeout": "7",
    }


def test_real_qq_smoke_env_vars_override_dev_toml_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / "qq-real-smoke.toml"
    _write_real_smoke_toml(config, access_token="file-token", mode="health", timeout=3)
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE_CONFIG", str(config))
    monkeypatch.setenv("ISOTOPE_QQ_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE_MODE", "dry-run")

    env = _real_smoke_env()

    assert env["access_token"] == "env-token"
    assert env["mode"] == "dry-run"


def test_real_qq_smoke_collection_gate_reads_enabled_toml(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / "qq-real-smoke.toml"
    _write_real_smoke_toml(config)
    monkeypatch.delenv("ISOTOPE_QQ_REAL_SMOKE", raising=False)
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE_CONFIG", str(config))

    assert _real_smoke_enabled()


def test_real_qq_smoke_harness_health_mode_uses_live_run(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    FakeLiveOneBotClient.instances = []
    monkeypatch.setattr(
        qq_runtime_commands,
        "OneBotWebSocketClient",
        FakeLiveOneBotClient,
    )
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE", "1")
    monkeypatch.setenv("ISOTOPE_QQ_ONEBOT_URL", "ws://127.0.0.1:3001")
    monkeypatch.setenv("ISOTOPE_QQ_TEST_GROUP", "99999")
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE_MODE", "health")

    payload = _run_real_qq_smoke(tmp_path=tmp_path, capsys=capsys)

    assert payload["status"] == "ok"
    assert payload["command"] == "live-run"
    assert payload["processed_events"] == 0
    assert payload["turns"] == []
    assert payload["dry_run"] is True
    assert FakeLiveOneBotClient.instances[0].events
    assert FakeLiveOneBotClient.instances[0].sent_group_messages == []


def test_real_qq_smoke_harness_dry_run_consumes_one_event_without_sending(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    FakeLiveOneBotClient.instances = []
    monkeypatch.setattr(
        qq_runtime_commands,
        "OneBotWebSocketClient",
        FakeLiveOneBotClient,
    )
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE", "1")
    monkeypatch.setenv("ISOTOPE_QQ_ONEBOT_URL", "ws://127.0.0.1:3001")
    monkeypatch.setenv("ISOTOPE_QQ_TEST_GROUP", "99999")
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE_MODE", "dry-run")

    payload = _run_real_qq_smoke(tmp_path=tmp_path, capsys=capsys)

    assert payload["status"] == "ok"
    assert payload["processed_events"] == 1
    assert payload["turns"][0]["decision"]["dry_run"] is True
    assert payload["turns"][0]["send_feedback"] == []
    assert FakeLiveOneBotClient.instances[0].events == []
    assert FakeLiveOneBotClient.instances[0].sent_group_messages == []


def test_real_qq_smoke_test_body_runs_with_fake_live_client(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    FakeLiveOneBotClient.instances = []
    monkeypatch.setattr(
        qq_runtime_commands,
        "OneBotWebSocketClient",
        FakeLiveOneBotClient,
    )
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE", "1")
    monkeypatch.setenv("ISOTOPE_QQ_ONEBOT_URL", "ws://127.0.0.1:3001")
    monkeypatch.setenv("ISOTOPE_QQ_TEST_GROUP", "99999")
    monkeypatch.setenv("ISOTOPE_QQ_REAL_SMOKE_MODE", "health")

    test_real_qq_smoke_is_explicitly_opt_in(tmp_path, capsys)


@pytest.mark.skipif(not _real_smoke_enabled(), reason="real QQ smoke is disabled")
def test_real_qq_smoke_is_explicitly_opt_in(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _run_real_qq_smoke(tmp_path=tmp_path, capsys=capsys)
    state_root = tmp_path / "state"
    assert payload["status"] == "ok"
    assert payload["command"] == "live-run"
    assert payload["state_file"] == str(state_root / "social-qq-state.json")
    assert payload["dry_run"] is True
    mode = os.environ.get("ISOTOPE_QQ_REAL_SMOKE_MODE", "health")
    if mode == "health":
        assert payload["processed_events"] == 0
    else:
        assert payload["processed_events"] <= 1


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
        return {"status": "ok", "message_id": "real-smoke-1"}

    def send_private_msg(self, *, user_id: str, message: list[dict]) -> dict:
        self.sent_private_messages.append({"user_id": user_id, "message": message})
        return {"status": "ok", "message_id": "real-smoke-private-1"}

    def connection_state(self) -> dict:
        return {
            "connected": self.connected,
            "pending_events": len(self.events),
            "seen_message_count": 0,
            "api_sequence": len(self.sent_group_messages) + len(self.sent_private_messages),
        }

    def close(self) -> None:
        self.connected = False


def _run_real_qq_smoke(
    *,
    tmp_path: Path,
    capsys,
) -> dict:
    env = _real_smoke_env()
    config = _write_json(tmp_path / "config.json", _real_smoke_config(env))
    state_root = tmp_path / "state"
    code = social_runner.main(_real_smoke_args(env, config=config, state_root=state_root))
    assert code == 0
    return json.loads(capsys.readouterr().out)


def _real_smoke_env() -> dict[str, str]:
    config = _real_smoke_toml_config()
    onebot_url = _env_or_config("ISOTOPE_QQ_ONEBOT_URL", config, "onebot_url")
    assert onebot_url, "ISOTOPE_QQ_ONEBOT_URL is required for real QQ smoke"
    group_id = _env_or_config("ISOTOPE_QQ_TEST_GROUP", config, "test_group")
    assert group_id, "ISOTOPE_QQ_TEST_GROUP is required for real QQ smoke"
    mode = _env_or_config("ISOTOPE_QQ_REAL_SMOKE_MODE", config, "mode", default="health")
    assert mode in {"health", "dry-run"}, (
        "ISOTOPE_QQ_REAL_SMOKE_MODE must be health or dry-run; automated smoke "
        "never sends real messages"
    )
    return {
        "onebot_url": onebot_url,
        "group_id": group_id,
        "bot_user_id": _env_or_config(
            "ISOTOPE_QQ_BOT_USER_ID",
            config,
            "bot_user_id",
            default="bot_qq",
        ),
        "access_token": _env_or_config(
            "ISOTOPE_QQ_ACCESS_TOKEN",
            config,
            "access_token",
            default="",
        ),
        "mode": mode,
        "timeout": _env_or_config(
            "ISOTOPE_QQ_REAL_SMOKE_TIMEOUT",
            config,
            "timeout",
            default="3",
        ),
    }


def _env_or_config(
    env_key: str,
    config: dict[str, object],
    config_key: str,
    *,
    default: str | None = None,
) -> str:
    env_value = os.environ.get(env_key)
    if env_value is not None:
        return env_value
    value = config.get(config_key)
    if value is None:
        return "" if default is None else default
    return str(value)


def _real_smoke_args(
    env: dict[str, str],
    *,
    config: Path,
    state_root: Path,
) -> list[str]:
    max_events = "0" if env["mode"] == "health" else "1"
    args = [
        "qq",
        "live-run",
        "--config-json",
        str(config),
        "--state-root",
        str(state_root),
        "--websocket-url",
        env["onebot_url"],
        "--max-events",
        max_events,
        "--receive-timeout-seconds",
        env["timeout"],
        "--json",
    ]
    if env["access_token"]:
        args.extend(["--access-token", env["access_token"]])
    return args


def _real_smoke_config(env: dict[str, str]) -> dict:
    return {
        "bot_user_id": env["bot_user_id"],
        "dry_run": True,
        "group_policy": {
            "allowed_groups": [env["group_id"]],
            "blocked_groups": [],
            "operator_user_ids": [],
            "paused_groups": [],
            "default_dry_run": True,
        },
        "role_card": {
            "schema_version": "isotope.character_card_plus.v1",
            "identity": {
                "name": "QQ Smoke Bot",
                "description": "受控群 smoke 验证角色",
            },
            "voice": {
                "speaking_style": "简洁",
                "tone": "calm",
                "vocabulary": ["smoke"],
                "example_messages": ["收到，我只做受控验证。"],
                "forbidden_style": "不要主动闲聊。",
            },
            "social_behavior": {
                "talkativeness": 0.5,
                "interruption_style": "only_when_mentioned",
                "mention_policy": "always_consider",
                "lurk_policy": "watch_and_wait",
                "disagreement_style": "explain_reason",
                "relationship_policy": "do_not_remember",
            },
            "stickers": {
                "enabled": False,
                "favorite_packs": [],
                "style_tags": [],
                "emotion_map": {},
                "use_frequency": 0.0,
                "allow_sticker_only_reply": False,
                "avoid_tags": [],
            },
            "tools": {
                "allowed_capabilities": [],
                "tool_use_style": "disabled_for_smoke",
                "after_tool_result_behavior": "answer_briefly",
            },
            "memory": {
                "remember": [],
                "do_not_remember": ["smoke messages"],
                "review_policy": "no_memory_writes_in_smoke",
            },
            "groups": {"overrides": {}},
        },
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path
