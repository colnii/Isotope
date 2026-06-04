from __future__ import annotations

import json
from typing import Any

import pytest

from isotope.features.social import (
    CharacterCard,
    LLMSocialReplyProvider,
    SocialContextBuilder,
    SocialDecisionRequest,
    SocialMessage,
    SocialMessagePart,
    SocialSender,
    SocialTarget,
)
from tests.unit.features.social.test_character_card import _card_dict


class RecordingChatProvider:
    provider = "unit-chat"
    model = "unit-model"

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages: list[dict[str, str]], *, max_tokens: int = 512) -> Any:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return type(
            "Response",
            (),
            {
                "provider": self.provider,
                "model": self.model,
                "content": self.content,
                "usage": {"total_tokens": 12},
            },
        )()


def _request() -> SocialDecisionRequest:
    card = CharacterCard.from_dict(_card_dict())
    message = SocialMessage(
        message_id="qq_reply_msg",
        platform="qq",
        adapter="onebot",
        chat_type="group",
        group_id="99999",
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text="这个 PR 怎么看？",
        mentions=("bot_qq",),
        parts=(
            SocialMessagePart(kind="text", text="这个 PR 怎么看？"),
            SocialMessagePart(kind="mention", text="@bot_qq", user_id="bot_qq"),
        ),
    )
    return SocialDecisionRequest(
        context=SocialContextBuilder(character_card=card).build(
            group_id="99999",
            message=message,
        ),
        target=SocialTarget(platform="qq", chat_type="group", group_id="99999"),
        bot_user_id="bot_qq",
    )


def test_llm_social_reply_provider_builds_prompt_from_persona_and_chat_context() -> None:
    chat_provider = RecordingChatProvider(json.dumps({"text": "小林，这个 PR 我先看测试风险。"}))

    draft = LLMSocialReplyProvider(chat_provider=chat_provider).generate_reply(
        _request(),
        wake_reason="mention:bot_qq",
    )

    assert draft.text == "小林，这个 PR 我先看测试风险。"
    assert draft.metadata == {
        "provider": "unit-chat",
        "model": "unit-model",
        "usage": {"total_tokens": 12},
        "wake_reason": "mention:bot_qq",
    }
    assert chat_provider.calls[0]["max_tokens"] == 256
    messages = chat_provider.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "QQ group chatbot reply generator" in messages[0]["content"]
    prompt_payload = json.loads(messages[1]["content"])
    assert prompt_payload["wake_reason"] == "mention:bot_qq"
    assert prompt_payload["persona_instructions"]["role_name"] == "群聊工程猫"
    assert prompt_payload["chat_context"]["current_message"]["text"] == "这个 PR 怎么看？"
    assert prompt_payload["required_json_shape"] == {"text": "non-empty string"}


def test_llm_social_reply_provider_rejects_empty_or_malformed_model_output() -> None:
    chat_provider = RecordingChatProvider(json.dumps({"text": ""}))

    with pytest.raises(ValueError, match="reply text must be a non-empty string"):
        LLMSocialReplyProvider(chat_provider=chat_provider).generate_reply(
            _request(),
            wake_reason="mention:bot_qq",
        )
