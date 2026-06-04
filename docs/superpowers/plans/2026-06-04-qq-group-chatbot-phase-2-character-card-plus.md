# QQ Group Chatbot Phase 2 Character Card Plus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add role-card driven personality configuration for the social agent, including identity, voice, social behavior, sticker preferences, tools, memory policy, and group-specific overrides.

**Architecture:** Store Phase 2 role cards as JSON to avoid adding a YAML dependency. Implement a focused `character_card.py` model and a small `character_loader.py` file loader. Group overrides merge nested section dictionaries over the base card and return a new immutable card.

**Tech Stack:** Python 3.13, pytest, dataclasses, stdlib `json`, existing Isotope validation style.

---

## File Structure

- Create `src/isotope/features/social/character_card.py`: role-card dataclasses, validation, dict conversion, and group override merging.
- Create `src/isotope/features/social/character_loader.py`: JSON file loading helper.
- Modify `src/isotope/features/social/__init__.py`: export Phase 2 names.
- Create `tests/unit/features/social/test_character_card.py`: character card and loader tests.
- Create `tests/fixtures/social/character_cards/qq_helper.json`: valid role-card fixture.

## Task 1: Character Card Dataclasses

**Files:**
- Create: `src/isotope/features/social/character_card.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_character_card.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/features/social/test_character_card.py` with:

```python
from __future__ import annotations

import pytest

from isotope.features.social import CharacterCard


def _card_dict() -> dict:
    return {
        "schema_version": "isotope.character_card_plus.v1",
        "identity": {
            "name": "群聊工程猫",
            "aliases": ["bot", "工程猫"],
            "avatar_ref": "asset://avatars/engineer-cat.png",
            "description": "一个长期待在群里的工程助手角色。",
        },
        "voice": {
            "speaking_style": "直接、简洁、带一点吐槽",
            "tone": "calm",
            "vocabulary": ["repo", "测试", "表情包"],
            "example_messages": ["我先看上下文，再决定要不要插话。"],
            "forbidden_style": "不要像客服机器人。",
        },
        "social_behavior": {
            "talkativeness": 0.45,
            "interruption_style": "only_when_useful",
            "mention_policy": "always_consider",
            "lurk_policy": "watch_and_wait",
            "disagreement_style": "explain_reason",
            "relationship_policy": "remember_stable_preferences",
        },
        "stickers": {
            "enabled": True,
            "favorite_packs": ["engineering"],
            "style_tags": ["dry", "helpful"],
            "emotion_map": {"ack": ["ok"], "confused": ["question"]},
            "use_frequency": 0.35,
            "allow_sticker_only_reply": True,
            "avoid_tags": ["spammy"],
        },
        "tools": {
            "allowed_capabilities": ["research.search", "supervisor.request_context"],
            "tool_use_style": "use_when_it_improves_answer",
            "after_tool_result_behavior": "answer_with_sources",
        },
        "memory": {
            "remember": ["group rules", "stable preferences"],
            "do_not_remember": ["one-off jokes"],
            "review_policy": "operator_review_for_reviewable_social_facts",
        },
        "groups": {
            "overrides": {
                "12345": {
                    "social_behavior": {"talkativeness": 0.2},
                    "stickers": {"enabled": False},
                }
            }
        },
    }


def test_character_card_loads_complete_role_card() -> None:
    card = CharacterCard.from_dict(_card_dict())

    assert card.identity.name == "群聊工程猫"
    assert card.voice.speaking_style == "直接、简洁、带一点吐槽"
    assert card.social_behavior.talkativeness == 0.45
    assert card.stickers.enabled is True
    assert card.stickers.favorite_packs == ("engineering",)
    assert card.tools.allowed_capabilities == (
        "research.search",
        "supervisor.request_context",
    )
    assert card.to_dict()["schema_version"] == "isotope.character_card_plus.v1"


def test_character_card_applies_group_override_without_mutating_base() -> None:
    card = CharacterCard.from_dict(_card_dict())
    group_card = card.for_group("12345")

    assert group_card.social_behavior.talkativeness == 0.2
    assert group_card.stickers.enabled is False
    assert card.social_behavior.talkativeness == 0.45
    assert card.stickers.enabled is True


def test_character_card_rejects_missing_identity_name() -> None:
    data = _card_dict()
    data["identity"]["name"] = " "

    with pytest.raises(ValueError, match="identity.name must be a non-empty string"):
        CharacterCard.from_dict(data)


def test_character_card_rejects_invalid_sticker_frequency() -> None:
    data = _card_dict()
    data["stickers"]["use_frequency"] = 1.2

    with pytest.raises(ValueError, match="stickers.use_frequency must be between 0 and 1"):
        CharacterCard.from_dict(data)


def test_character_card_rejects_unknown_schema_version() -> None:
    data = _card_dict()
    data["schema_version"] = "unknown"

    with pytest.raises(ValueError, match="schema_version is not supported"):
        CharacterCard.from_dict(data)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_character_card.py -q
```

Expected: FAIL because `CharacterCard` does not exist.

- [ ] **Step 3: Implement character card dataclasses**

Create `src/isotope/features/social/character_card.py` with:

- `CHARACTER_CARD_SCHEMA_VERSION`
- `CharacterIdentity`
- `CharacterVoice`
- `SocialBehavior`
- `StickerPreferences`
- `ToolPolicy`
- `MemoryPolicy`
- `CharacterCard`
- `CharacterCard.from_dict(...)`
- `CharacterCard.to_dict()`
- `CharacterCard.for_group(group_id)`

Validation requirements:

- required strings must be non-empty;
- list-like fields become tuples of non-empty strings;
- `talkativeness` and `use_frequency` must be between 0 and 1;
- `enabled` and `allow_sticker_only_reply` must be bools;
- unknown schema versions fail.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_character_card.py -q
```

Expected: PASS.

## Task 2: Character Card File Loader

**Files:**
- Create: `src/isotope/features/social/character_loader.py`
- Modify: `src/isotope/features/social/__init__.py`
- Create: `tests/fixtures/social/character_cards/qq_helper.json`
- Modify: `tests/unit/features/social/test_character_card.py`

- [ ] **Step 1: Write the failing loader test**

Append to `tests/unit/features/social/test_character_card.py`:

```python
from pathlib import Path

from isotope.features.social import load_character_card


def test_load_character_card_reads_json_fixture() -> None:
    fixture = (
        Path(__file__).parents[3]
        / "fixtures"
        / "social"
        / "character_cards"
        / "qq_helper.json"
    )

    card = load_character_card(fixture)

    assert card.identity.name == "群聊工程猫"
    assert card.stickers.enabled is True
```

Create `tests/fixtures/social/character_cards/qq_helper.json` with a valid card
matching the `_card_dict()` shape from Task 1.

- [ ] **Step 2: Run loader test to verify it fails**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_character_card.py::test_load_character_card_reads_json_fixture -q
```

Expected: FAIL because `load_character_card` does not exist.

- [ ] **Step 3: Implement loader**

Create `src/isotope/features/social/character_loader.py` with:

- `load_character_card(path: Path | str) -> CharacterCard`
- JSON parsing through `json.loads`
- file must contain a JSON object
- malformed JSON reports `character card JSON is invalid`

Export `load_character_card` from `src/isotope/features/social/__init__.py`.

- [ ] **Step 4: Run full character card tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_character_card.py -q
```

Expected: PASS.

## Task 3: Phase Verification

**Files:**
- All Phase 2 files.

- [ ] **Step 1: Run focused social tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run Phase 0 baseline tests**

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
git add src/isotope/features/social tests/unit/features/social tests/fixtures/social/character_cards docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-2-character-card-plus.md
git commit -m "feat(social): add character card model"
```
