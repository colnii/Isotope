# QQ Group Chatbot Phase 3 Lorebook Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add group lorebook entries and a social context builder so role cards can be enriched by group rules, recurring references, message-part triggers, and memory previews.

**Architecture:** Keep lorebook selection platform-neutral by matching against `SocialMessage`. The context builder returns an inspectable dictionary containing the group-specific character card, triggered lorebook entries with reasons, recent messages, and memory previews.

**Tech Stack:** Python 3.13, pytest, dataclasses, stdlib `re` and `datetime`.

---

## File Structure

- Create `src/isotope/features/social/lorebook.py`: lorebook entry models and trigger selection.
- Create `src/isotope/features/social/context_builder.py`: context payload builder.
- Modify `src/isotope/features/social/__init__.py`: export Phase 3 names.
- Create `tests/unit/features/social/test_lorebook.py`: trigger and expiration tests.
- Create `tests/unit/features/social/test_social_context_builder.py`: context builder tests.
- Create `tests/fixtures/social/lorebooks/engineering_group.json`: valid lorebook fixture.

## Task 1: Lorebook Entry Selection

**Files:**
- Create: `src/isotope/features/social/lorebook.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_lorebook.py`

- [ ] **Step 1: Write failing lorebook tests**

Create `tests/unit/features/social/test_lorebook.py` with tests for:

```python
from __future__ import annotations

from isotope.features.social import Lorebook, LorebookEntry, SocialMessage, SocialMessagePart, SocialSender


def _message(*, text: str, sender_id: str = "10001", parts=None) -> SocialMessage:
    return SocialMessage(
        message_id="qq_msg_lore",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(user_id=sender_id, display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text=text,
        parts=tuple(parts or (SocialMessagePart(kind="text", text=text),)),
    )


def test_lorebook_selects_keyword_regex_user_and_part_kind_triggers() -> None:
    lorebook = Lorebook(
        entries=(
            LorebookEntry(
                entry_id="rule_tests",
                title="测试规则",
                content="聊测试时要问清楚验证命令。",
                keywords=("测试",),
                priority=20,
            ),
            LorebookEntry(
                entry_id="regex_pr",
                title="PR 规则",
                content="提到 PR 编号时要检查链接。",
                regex=(r"PR #\\d+",),
                priority=30,
            ),
            LorebookEntry(
                entry_id="user_lumber",
                title="用户偏好",
                content="这个用户讨厌空泛安全话术。",
                users=("10001",),
                priority=10,
            ),
            LorebookEntry(
                entry_id="sticker_norm",
                title="表情包规则",
                content="表情包消息可以用短文字回应。",
                message_part_kinds=("sticker",),
                priority=40,
            ),
        )
    )

    selected = lorebook.select_for_message(
        _message(
            text="PR #12 的测试咋样",
            parts=(SocialMessagePart(kind="sticker", media_ref="qq-image://ok"),),
        )
    )

    assert [item.entry.entry_id for item in selected] == [
        "sticker_norm",
        "regex_pr",
        "rule_tests",
        "user_lumber",
    ]
    assert "message_part_kind:sticker" in selected[0].reasons
    assert "regex:PR #\\\\d+" in selected[1].reasons


def test_lorebook_skips_expired_entries() -> None:
    lorebook = Lorebook(
        entries=(
            LorebookEntry(
                entry_id="old",
                title="旧规则",
                content="过期规则不进入上下文。",
                keywords=("测试",),
                expires_at="2026-06-03T00:00:00Z",
            ),
        )
    )

    assert lorebook.select_for_message(_message(text="测试"), now="2026-06-04T00:00:00Z") == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_lorebook.py -q
```

Expected: FAIL because `Lorebook` and `LorebookEntry` do not exist.

- [ ] **Step 3: Implement lorebook selection**

Create `src/isotope/features/social/lorebook.py` with:

- `LorebookEntry`
- `SelectedLorebookEntry`
- `Lorebook`
- keyword, regex, user, and message-part-kind matching
- priority sorting from high to low, then `entry_id`
- ISO timestamp expiration using `datetime.fromisoformat`
- `to_public_dict()` on selected entries with reasons

Export these names from `src/isotope/features/social/__init__.py`.

- [ ] **Step 4: Run lorebook tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_lorebook.py -q
```

Expected: PASS.

## Task 2: Social Context Builder

**Files:**
- Create: `src/isotope/features/social/context_builder.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_social_context_builder.py`
- Create: `tests/fixtures/social/lorebooks/engineering_group.json`

- [ ] **Step 1: Write failing context builder tests**

Create `tests/unit/features/social/test_social_context_builder.py` with tests for:

```python
from __future__ import annotations

from isotope.features.social import (
    CharacterCard,
    Lorebook,
    LorebookEntry,
    SocialContextBuilder,
    SocialMessage,
    SocialMessagePart,
    SocialSender,
)
from tests.unit.features.social.test_character_card import _card_dict


def test_social_context_builder_combines_card_lorebook_recent_messages_and_memory() -> None:
    card = CharacterCard.from_dict(_card_dict())
    lorebook = Lorebook(
        entries=(
            LorebookEntry(
                entry_id="rule_tests",
                title="测试规则",
                content="聊测试时要问清楚验证命令。",
                keywords=("测试",),
                priority=20,
            ),
        )
    )
    message = SocialMessage(
        message_id="qq_msg_context",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text="测试咋跑",
        parts=(SocialMessagePart(kind="text", text="测试咋跑"),),
    )

    payload = SocialContextBuilder(
        character_card=card,
        lorebook=lorebook,
    ).build(
        group_id="12345",
        message=message,
        recent_messages=(
            {"message_id": "prev", "preview": "前文"},
        ),
        memory_previews=(
            {"memory_id": "mem_1", "summary": "用户偏好直接答案"},
        ),
    )

    assert payload["character_card"]["social_behavior"]["talkativeness"] == 0.2
    assert payload["lorebook_entries"][0]["entry_id"] == "rule_tests"
    assert payload["lorebook_entries"][0]["reasons"] == ["keyword:测试"]
    assert payload["recent_messages"][0]["message_id"] == "prev"
    assert payload["memory_previews"][0]["memory_id"] == "mem_1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_context_builder.py -q
```

Expected: FAIL because `SocialContextBuilder` does not exist.

- [ ] **Step 3: Implement context builder**

Create `src/isotope/features/social/context_builder.py` with:

- `SocialContextBuilder(character_card: CharacterCard, lorebook: Lorebook | None = None)`
- `build(group_id, message, recent_messages=(), memory_previews=(), now=None)`
- output keys: `kind`, `group_id`, `message`, `character_card`, `lorebook_entries`, `recent_messages`, `memory_previews`
- defensive copies for recent messages and memory previews

Export `SocialContextBuilder`.

- [ ] **Step 4: Run context builder tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_context_builder.py -q
```

Expected: PASS.

## Task 3: Phase Verification

- [ ] **Step 1: Run social tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run baseline tests**

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

- [ ] **Step 4: Commit**

Run:

```bash
git add src/isotope/features/social tests/unit/features/social tests/fixtures/social/lorebooks docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-3-lorebook-context.md
git commit -m "feat(social): add lorebook context builder"
```
