from __future__ import annotations

import json
from pathlib import Path

from isotope.features.social import qq_runtime_commands
from isotope.features.social.runner import main
from isotope.llm.provider import LLMProviderResolution
from tests.unit.features.social.test_social_runner import _config, _write_json


class FakeParticipationChatProvider:
    provider = "unit-chat"
    model = "unit-model"

    def generate(self, messages: list[dict], *, max_tokens: int = 512):
        return type(
            "Response",
            (),
            {
                "provider": self.provider,
                "model": self.model,
                "content": json.dumps(
                    {
                        "action": "respond",
                        "reason": "topic fit",
                        "confidence": 0.81,
                        "text": "这个 PR 今天合可以，先确认测试结果。",
                    },
                    ensure_ascii=False,
                ),
                "usage": {"total_tokens": 18},
            },
        )()


def _ordinary_event() -> dict:
    return {
        "message_id": 456,
        "message_type": "group",
        "group_id": 99999,
        "user_id": 10001,
        "sender": {"nickname": "小林", "role": "member"},
        "time": 1780560000,
        "message": [
            {"type": "text", "data": {"text": "这个 PR 今天能合吗"}},
        ],
        "raw_message": "这个 PR 今天能合吗",
    }


def test_social_runner_qq_dry_run_can_use_llm_participation_provider(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    config_payload = _config()
    config_payload["runtime"] = {"participation_provider": "llm"}
    config = _write_json(tmp_path / "config.json", config_payload)
    event = _write_json(tmp_path / "event.json", _ordinary_event())

    monkeypatch.setattr(
        qq_runtime_commands,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="configured",
            reason_code="llm_provider_configured",
            provider_name="unit-chat",
            provider=FakeParticipationChatProvider(),
        ),
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
    assert candidate["kind"] == "respond"
    assert candidate["reason"] == "topic fit"
    assert candidate["reply_action"]["parts"][0]["text"] == (
        "这个 PR 今天合可以，先确认测试结果。"
    )
    assert candidate["metadata"]["participation_provider"]["provider"] == "unit-chat"
    assert payload["turn"]["decision"]["selected"] == []
    assert payload["sent_group_messages"] == []
