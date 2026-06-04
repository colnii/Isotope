# QQ Group Chatbot Phase 1 Social Message Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add platform-neutral social message, reply action, and send feedback objects that can represent real QQ group messages without importing QQ SDK objects into the agent core.

**Architecture:** Create a new `isotope.features.social` package with small dataclasses and validation helpers. The objects keep platform-specific details behind structured `platform_data` / `raw_event_ref` fields while exposing common message parts such as text, mention, reply, QQ face, sticker, image, file, voice, video, and link.

**Tech Stack:** Python 3.13, pytest, dataclasses, existing Isotope validation style.

---

## File Structure

- Create `src/isotope/features/social/__init__.py`: public exports for Phase 1 dataclasses.
- Create `src/isotope/features/social/messages.py`: incoming message objects and message parts.
- Create `src/isotope/features/social/replies.py`: outgoing reply action objects and send policy.
- Create `src/isotope/features/social/send_feedback.py`: platform send result and chunk records.
- Create `tests/unit/features/social/test_social_messages.py`: incoming message tests.
- Create `tests/unit/features/social/test_social_replies.py`: reply action and feedback tests.

## Task 1: Incoming Social Message Objects

**Files:**
- Create: `src/isotope/features/social/__init__.py`
- Create: `src/isotope/features/social/messages.py`
- Test: `tests/unit/features/social/test_social_messages.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/features/social/test_social_messages.py` with tests for:

```python
from __future__ import annotations

import pytest

from isotope.features.social import (
    SocialMessage,
    SocialMessagePart,
    SocialReplyRef,
    SocialSender,
)


def test_social_message_accepts_sticker_only_group_message() -> None:
    message = SocialMessage(
        message_id="qq_msg_1",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(
            user_id="10001",
            display_name="小林",
            roles=("member",),
            is_bot=False,
        ),
        timestamp="2026-06-04T08:00:00Z",
        text="",
        parts=(
            SocialMessagePart(
                kind="sticker",
                media_ref="qq-image://abc",
                platform_data={"file_id": "abc"},
            ),
        ),
        raw_event_ref="event://qq/qq_msg_1",
    )

    assert message.has_content is True
    assert message.text_content == ""
    assert message.part_kinds == ("sticker",)
    assert message.to_public_dict()["parts"][0]["kind"] == "sticker"


def test_social_message_keeps_text_part_for_plain_text() -> None:
    message = SocialMessage(
        message_id="qq_msg_2",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text="你好",
        parts=(SocialMessagePart(kind="text", text="你好"),),
    )

    assert message.has_content is True
    assert message.text_content == "你好"
    assert message.to_public_dict()["parts"] == [{"kind": "text", "text": "你好"}]


def test_social_message_supports_mentions_and_reply_reference() -> None:
    message = SocialMessage(
        message_id="qq_msg_3",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text="@bot 看看这个",
        mentions=("bot_qq",),
        reply_to=SocialReplyRef(
            message_id="qq_msg_parent",
            sender_id="10002",
            text_preview="上一条内容",
        ),
        parts=(
            SocialMessagePart(kind="mention", user_id="bot_qq", text="@bot"),
            SocialMessagePart(kind="text", text=" 看看这个"),
        ),
    )

    payload = message.to_public_dict()
    assert payload["mentions"] == ["bot_qq"]
    assert payload["reply_to"]["message_id"] == "qq_msg_parent"
    assert payload["parts"][0]["kind"] == "mention"


def test_social_message_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="message_id must be a non-empty string"):
        SocialMessage(
            message_id=" ",
            platform="qq",
            adapter="napcat_onebot",
            chat_type="group",
            group_id="12345",
            sender=SocialSender(user_id="10001", display_name="小林"),
            timestamp="2026-06-04T08:00:00Z",
            text="hello",
            parts=(SocialMessagePart(kind="text", text="hello"),),
        )


def test_social_message_rejects_unknown_part_kind() -> None:
    with pytest.raises(ValueError, match="message part kind is not supported"):
        SocialMessagePart(kind="unknown", text="hello")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_messages.py -q
```

Expected: FAIL because `isotope.features.social` does not exist.

- [ ] **Step 3: Implement incoming message dataclasses**

Create `src/isotope/features/social/messages.py` with:

- `SUPPORTED_MESSAGE_PART_KINDS`
- `SocialSender`
- `SocialReplyRef`
- `SocialMessagePart`
- `SocialMessage`
- validation helpers for required strings, optional strings, tuples, and dicts
- `to_public_dict()` methods that omit empty fields
- `has_content`, `text_content`, and `part_kinds` properties

Create `src/isotope/features/social/__init__.py` exporting those names.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_messages.py -q
```

Expected: PASS.

## Task 2: Reply Action And Send Feedback Objects

**Files:**
- Create: `src/isotope/features/social/replies.py`
- Create: `src/isotope/features/social/send_feedback.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_social_replies.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/features/social/test_social_replies.py` with tests for:

```python
from __future__ import annotations

import pytest

from isotope.features.social import (
    SocialMessagePart,
    SocialReplyAction,
    SocialSendChunk,
    SocialSendFeedback,
    SocialSendPolicy,
    SocialTarget,
)


def test_reply_action_supports_text_and_sticker_parts() -> None:
    action = SocialReplyAction(
        action_id="reply_1",
        target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
        reply_to_message_id="qq_msg_1",
        parts=(
            SocialMessagePart(kind="text", text="收到"),
            SocialMessagePart(kind="sticker", media_ref="qq-image://ok"),
        ),
        send_policy=SocialSendPolicy(
            urgency="normal",
            allow_split=True,
            max_chunks=2,
            min_delay_ms=800,
            reason="text plus sticker reply",
        ),
    )

    payload = action.to_public_dict()
    assert payload["target"]["group_id"] == "12345"
    assert [part["kind"] for part in payload["parts"]] == ["text", "sticker"]
    assert payload["send_policy"]["max_chunks"] == 2


def test_reply_action_rejects_empty_parts() -> None:
    with pytest.raises(ValueError, match="reply action parts must not be empty"):
        SocialReplyAction(
            action_id="reply_empty",
            target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
            parts=(),
        )


def test_send_feedback_records_chunks_and_recent_messages() -> None:
    feedback = SocialSendFeedback(
        status="sent",
        sent_message_ids=("qq_sent_1", "qq_sent_2"),
        chunks=(
            SocialSendChunk(
                message_id="qq_sent_1",
                parts=(SocialMessagePart(kind="text", text="第一段"),),
                rendered_preview="第一段",
            ),
            SocialSendChunk(
                message_id="qq_sent_2",
                parts=(SocialMessagePart(kind="sticker", media_ref="qq-image://ok"),),
                rendered_preview="[sticker: qq-image://ok]",
            ),
        ),
        recent_messages_after_send=(
            {"message_id": "qq_sent_2", "sender": "bot", "preview": "[sticker]"},
        ),
    )

    payload = feedback.to_public_dict()
    assert payload["status"] == "sent"
    assert payload["sent_message_ids"] == ["qq_sent_1", "qq_sent_2"]
    assert payload["chunks"][1]["parts"][0]["kind"] == "sticker"
    assert payload["recent_messages_after_send"][0]["sender"] == "bot"


def test_send_feedback_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="send feedback status is not supported"):
        SocialSendFeedback(status="maybe")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_replies.py -q
```

Expected: FAIL because reply and feedback dataclasses do not exist.

- [ ] **Step 3: Implement reply and feedback dataclasses**

Create `src/isotope/features/social/replies.py` with:

- `SUPPORTED_CHAT_TYPES`
- `SUPPORTED_SEND_URGENCIES`
- `SocialTarget`
- `SocialSendPolicy`
- `SocialReplyAction`

Create `src/isotope/features/social/send_feedback.py` with:

- `SUPPORTED_SEND_STATUSES`
- `SocialSendChunk`
- `SocialSendFeedback`

Update `src/isotope/features/social/__init__.py` to export all Phase 1 names.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_messages.py tests/unit/features/social/test_social_replies.py -q
```

Expected: PASS.

## Task 3: Phase Verification

**Files:**
- All Phase 1 files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_messages.py tests/unit/features/social/test_social_replies.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run baseline supervisor conversation tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Inspect changed files**

Run:

```bash
git diff --stat
git diff -- src/isotope/features/social tests/unit/features/social docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-1-social-message-model.md
```

Expected: changes are limited to Phase 1 social model files, tests, and this plan.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/isotope/features/social tests/unit/features/social docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-1-social-message-model.md
git commit -m "feat(social): add platform-neutral message model"
```
